"""
Client-side WebSocket protocol handler v2.

Manages the connection to the Teragucci server with:
- Hybrid TCP+UDP transport (UDP for video/audio, TCP for control)
- TLS support (wss:// on port 443)
- Authentication handshake
- Auto-reconnect
- Health ping/pong
- Jitter buffer for smooth UDP playback
- Automatic fallback to TCP-only when UDP is blocked
"""

import hashlib
import json
import logging
import socket
import threading
import asyncio
import time
from typing import Optional, Callable

import websockets

from common.messages import (
    MsgType, ClientHelloMsg, FrameType,
    decode_video_header, decode_jpeg_header, decode_audio_header,
    VIDEO_HEADER_SIZE, JPEG_HEADER_SIZE, AUDIO_HEADER_SIZE,
    HealthPing, HealthPong, QualitySettings,
    AuthResponse, parse_message,
)
from common.udp_transport import UDPMediaClient, CHANNEL_VIDEO, CHANNEL_AUDIO, FLAG_KEYFRAME
from common.hybrid_transport import HybridClientTransport, TransportMsg
from common.jitter_buffer import JitterBuffer

logger = logging.getLogger(__name__)


class ClientProtocol:
    """
    Hybrid TCP+UDP client with TLS, auth, auto-reconnect, jitter buffer.

    Control messages (input, health, clipboard) go over TCP WebSocket.
    Media (video, audio) comes over UDP when available, TCP as fallback.
    """

    def __init__(self):
        self._ws = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._connected = False
        self._closing = False
        self._auto_reconnect = True
        self._reconnect_delay = 1.0
        self._max_reconnect_delay = 30.0

        # Auth
        self._username = ""
        self._password = ""
        self._user_salt = ""

        # TLS
        self._use_tls = False

        # UDP transport
        self._udp_client: Optional[UDPMediaClient] = None
        self._hybrid: Optional[HybridClientTransport] = None
        self._jitter_buffer: Optional[JitterBuffer] = None
        self._udp_enabled = True
        self._udp_stats_interval = 5.0  # Report stats every 5s

        # Callbacks (thread-safe via Qt signals in main.py)
        self.on_server_hello: Optional[Callable] = None
        self.on_video_frame: Optional[Callable] = None      # (frame_type, codec, chroma, flags, ts, monitor, data)
        self.on_jpeg_frame: Optional[Callable] = None        # (frame_type, x, y, w, h, data)
        self.on_audio_frame: Optional[Callable] = None       # (codec, timestamp, data)
        self.on_connected: Optional[Callable] = None
        self.on_disconnected: Optional[Callable] = None
        self.on_error: Optional[Callable] = None
        self.on_auth_required: Optional[Callable] = None     # (challenge)
        self.on_auth_result: Optional[Callable] = None       # (success, message)
        self.on_health_ping: Optional[Callable] = None       # (sequence, timestamp)
        self.on_health_stats: Optional[Callable] = None      # (stats_dict)
        self.on_monitor_list: Optional[Callable] = None      # (monitors_list)
        self.on_clipboard: Optional[Callable] = None         # (text)

    @property
    def connected(self) -> bool:
        return self._connected

    def connect(self, host: str, port: int, username: str = "", password: str = "",
                use_tls: bool = False, auto_reconnect: bool = True):
        """Start connection (non-blocking)."""
        if self._thread and self._thread.is_alive():
            self.disconnect()

        self._closing = False
        self._username = username
        self._password = password
        self._use_tls = use_tls
        self._auto_reconnect = auto_reconnect
        self._reconnect_delay = 1.0
        self._host = host
        self._port = port

        self._thread = threading.Thread(
            target=self._run_loop,
            args=(host, port),
            daemon=True,
            name="teragucci-client-io",
        )
        self._thread.start()

    def disconnect(self):
        """Disconnect and stop auto-reconnect."""
        self._closing = True
        self._auto_reconnect = False
        # Stop UDP
        if self._hybrid:
            self._hybrid.stop()
            self._hybrid = None
        if self._jitter_buffer:
            self._jitter_buffer.stop()
            self._jitter_buffer = None
        self._udp_client = None
        # Stop TCP
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread:
            self._thread.join(timeout=3.0)
            self._thread = None
        self._connected = False

    def send_input(self, msg_dict: dict):
        """Send an input message (thread-safe)."""
        if not self._connected or not self._ws:
            return
        try:
            json_str = json.dumps(msg_dict)
            if self._loop and self._loop.is_running():
                asyncio.run_coroutine_threadsafe(self._ws.send(json_str), self._loop)
        except Exception as e:
            logger.debug("Send error: %s", e)

    def send_quality_settings(self, settings: QualitySettings):
        """Send quality settings to server."""
        self.send_input(json.loads(settings.to_json()))

    def request_full_frame(self):
        self.send_input({"type": MsgType.REQUEST_FULL_FRAME})

    def select_monitor(self, monitor_id: int):
        self.send_input({"type": MsgType.SELECT_MONITOR, "monitor_id": monitor_id})

    def send_clipboard(self, text: str):
        self.send_input({"type": MsgType.CLIPBOARD_SEND, "content_type": "text/plain", "data": text})

    def _run_loop(self, host: str, port: int):
        """Background thread main loop with auto-reconnect."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        try:
            while not self._closing:
                try:
                    self._loop.run_until_complete(self._connect_and_receive(host, port))
                except Exception as e:
                    if not self._closing:
                        logger.error("Connection error: %s", e)
                        if self.on_error:
                            self.on_error(str(e))

                self._connected = False
                if self.on_disconnected and not self._closing:
                    self.on_disconnected("Connection lost")

                if not self._auto_reconnect or self._closing:
                    break

                # Auto-reconnect with exponential backoff
                logger.info("Reconnecting in %.1fs...", self._reconnect_delay)
                time.sleep(self._reconnect_delay)
                self._reconnect_delay = min(self._reconnect_delay * 1.5, self._max_reconnect_delay)

        finally:
            self._connected = False
            self._loop.close()
            self._loop = None

    async def _connect_and_receive(self, host: str, port: int):
        """Connect, authenticate, and process messages."""
        scheme = "wss" if self._use_tls else "ws"
        uri = f"{scheme}://{host}:{port}"
        logger.info("Connecting to %s", uri)

        ssl_context = None
        if self._use_tls:
            import ssl
            ssl_context = ssl.create_default_context()

        async with websockets.connect(
            uri, max_size=50 * 1024 * 1024,
            ping_interval=20, ping_timeout=30,
            ssl=ssl_context,
        ) as ws:
            self._ws = ws
            logger.info("Connected to server")

            # Receive first message — either auth_request or server_hello
            first_msg = await ws.recv()
            if isinstance(first_msg, str):
                msg = parse_message(first_msg)

                if msg.get("type") == MsgType.AUTH_REQUEST:
                    # Handle authentication
                    challenge = msg.get("challenge", "")
                    if self.on_auth_required:
                        self.on_auth_required(challenge)

                    # Compute credential hash
                    # For now, simple password hash against challenge
                    if self._password:
                        pwd_hash = hashlib.sha256(
                            f"{self._password}:{challenge}".encode()
                        ).hexdigest()
                    else:
                        pwd_hash = ""

                    auth_resp = AuthResponse(
                        method="password",
                        username=self._username,
                        credential=pwd_hash,
                    )
                    await ws.send(auth_resp.to_json())

                    # Wait for auth result
                    result_raw = await ws.recv()
                    result = parse_message(result_raw)
                    if result.get("type") == MsgType.AUTH_RESULT:
                        if self.on_auth_result:
                            self.on_auth_result(result.get("success", False), result.get("message", ""))
                        if not result.get("success", False):
                            return

                    # Now receive server hello
                    hello_raw = await ws.recv()
                    hello = parse_message(hello_raw)
                    self._handle_server_hello(hello)

                elif msg.get("type") == MsgType.SERVER_HELLO:
                    self._handle_server_hello(msg)

            self._connected = True
            self._reconnect_delay = 1.0  # Reset on successful connect

            if self.on_connected:
                self.on_connected()

            # Send client hello
            hello = ClientHelloMsg()
            await ws.send(hello.to_json())

            # --- Start UDP media transport ---
            if self._udp_enabled:
                await self._negotiate_udp(ws, host)

            # Start periodic UDP stats reporting
            if self._hybrid and self._hybrid.state.udp_confirmed:
                asyncio.ensure_future(self._udp_stats_loop(ws))

            # Main receive loop (TCP control messages + fallback media)
            async for message in ws:
                if self._closing:
                    break
                if isinstance(message, str):
                    self._handle_json(message)
                elif isinstance(message, bytes):
                    self._handle_binary(message)

    async def _negotiate_udp(self, ws, server_host: str):
        """Set up UDP transport and negotiate with server."""
        try:
            self._udp_client = UDPMediaClient()
            self._hybrid = HybridClientTransport(self._udp_client)

            # Set up jitter buffer for smooth playback
            self._jitter_buffer = JitterBuffer(on_frame_ready=self._on_jitter_frame)
            self._jitter_buffer.start()

            # Wire UDP frames through jitter buffer
            self._udp_client.on_video_frame = self._on_udp_video
            self._udp_client.on_audio_frame = self._on_udp_audio

            # Start UDP receiver and get local port
            local_port = self._hybrid.start_udp()

            # Get our local IP as seen by the server
            # (connect a temp socket to server to find our outbound IP)
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.connect((server_host, 1))
                local_addr = s.getsockname()[0]
                s.close()
            except Exception:
                local_addr = ""

            # Announce our UDP port to the server
            announce = self._hybrid.get_announce_message(local_addr)
            await ws.send(json.dumps(announce))
            logger.info("UDP announced: port %d, addr %s", local_port, local_addr)

            # Wait briefly for probe confirmation
            await asyncio.sleep(1.0)
            if self._hybrid.check_probe_received():
                confirm = self._hybrid.get_confirm_message()
                await ws.send(json.dumps(confirm))
                logger.info("UDP confirmed — media will use UDP transport")
            else:
                logger.info("UDP probe not received — using TCP fallback for media")

        except Exception as e:
            logger.warning("UDP setup failed: %s — using TCP fallback", e)
            self._hybrid = None

    async def _udp_stats_loop(self, ws):
        """Periodically report UDP stats to server."""
        while self._connected and not self._closing and self._hybrid:
            await asyncio.sleep(self._udp_stats_interval)
            if self._hybrid and self._connected:
                try:
                    stats_msg = self._hybrid.get_stats_message()
                    await ws.send(json.dumps(stats_msg))
                except Exception:
                    break

    def _on_udp_video(self, flags: int, timestamp_ms: int, data: bytes):
        """Handle video frame from UDP — route through jitter buffer."""
        is_keyframe = bool(flags & FLAG_KEYFRAME)
        if self._jitter_buffer:
            self._jitter_buffer.push(
                CHANNEL_VIDEO, flags, timestamp_ms, data, is_keyframe)
        else:
            # No jitter buffer — deliver directly
            self._on_jitter_frame(CHANNEL_VIDEO, flags, timestamp_ms, data)

    def _on_udp_audio(self, timestamp_ms: int, data: bytes):
        """Handle audio frame from UDP — route through jitter buffer."""
        if self._jitter_buffer:
            self._jitter_buffer.push(CHANNEL_AUDIO, 0, timestamp_ms, data)
        elif self.on_audio_frame:
            self.on_audio_frame(0, timestamp_ms, data)

    def _on_jitter_frame(self, channel: int, flags: int,
                         timestamp_ms: int, data: bytes):
        """Callback from jitter buffer when a frame is ready for display."""
        if channel == CHANNEL_VIDEO:
            if self.on_video_frame:
                self.on_video_frame(0, 0, 0, flags, timestamp_ms, 0, data)
        elif channel == CHANNEL_AUDIO:
            if self.on_audio_frame:
                self.on_audio_frame(0, timestamp_ms, data)

    def _handle_server_hello(self, msg: dict):
        if msg.get("type") == MsgType.SERVER_HELLO and self.on_server_hello:
            self.on_server_hello(msg)

    def _handle_json(self, data: str):
        try:
            msg = json.loads(data)
            msg_type = msg.get("type")

            if msg_type == MsgType.SERVER_HELLO:
                if self.on_server_hello:
                    self.on_server_hello(msg)

            # Handle UDP transport messages
            elif msg_type == TransportMsg.UDP_ACTIVE:
                logger.info("Server confirmed UDP active (RTT: %.1f ms)",
                            msg.get("udp_rtt_ms", 0))
            elif msg_type == TransportMsg.UDP_FALLBACK:
                logger.warning("Server: UDP fallback - %s", msg.get("reason", ""))

            elif msg_type == MsgType.HEALTH_PING:
                # Respond with pong
                pong = HealthPong(
                    ping_timestamp_ms=msg.get("timestamp_ms", 0),
                    sequence=msg.get("sequence", 0),
                )
                self.send_input(json.loads(pong.to_json()))

            elif msg_type == MsgType.HEALTH_STATS:
                if self.on_health_stats:
                    self.on_health_stats(msg)

            elif msg_type == MsgType.MONITOR_LIST:
                if self.on_monitor_list:
                    self.on_monitor_list(msg.get("monitors", []))

            elif msg_type == MsgType.CLIPBOARD_RECV:
                if self.on_clipboard:
                    self.on_clipboard(msg.get("data", ""))

        except json.JSONDecodeError:
            pass

    def _handle_binary(self, data: bytes):
        if len(data) < 2:
            return

        frame_type = data[0]

        if frame_type in (FrameType.VIDEO_H264, FrameType.VIDEO_H265, FrameType.VIDEO_AV1):
            if len(data) >= VIDEO_HEADER_SIZE and self.on_video_frame:
                ft, codec, chroma, flags, ts, mon, payload = decode_video_header(data)
                self.on_video_frame(ft, codec, chroma, flags, ts, mon, payload)

        elif frame_type in (FrameType.VIDEO_FULL, FrameType.VIDEO_PARTIAL):
            if len(data) >= JPEG_HEADER_SIZE and self.on_jpeg_frame:
                ft, x, y, w, h, payload = decode_jpeg_header(data)
                self.on_jpeg_frame(ft, x, y, w, h, payload)

        elif frame_type == FrameType.AUDIO:
            if len(data) >= AUDIO_HEADER_SIZE and self.on_audio_frame:
                codec, ts, payload = decode_audio_header(data)
                self.on_audio_frame(codec, ts, payload)
