#!/usr/bin/env python3
"""
Teragucci Server - Linux Remote Desktop Server v3

Full-featured remote desktop server with:
- H.264/H.265/AV1 video encoding with GPU acceleration (NVENC/VAAPI/AMF)
- YUV 4:4:4 chroma support
- JPEG fallback for low-resource environments
- Audio streaming via PulseAudio/PipeWire
- Pen/tablet pressure input injection via uinput
- Connection health monitoring
- TLS support
- Authentication
- Clipboard sync
- Multi-monitor support with hotplug detection
- Adaptive quality control
- QUIC transport (in addition to TCP+UDP)

Usage:
    python -m server.main [options]
    python -m server.main --add-user USERNAME  # Add/update a user
"""

import asyncio
import argparse
import json
import logging
import os
import pathlib
import signal
import ssl
import sys
import time
from dataclasses import asdict
from typing import Set, Optional

import websockets
from websockets.server import WebSocketServerProtocol

sys.path.insert(0, ".")
from common.messages import (
    MsgType, ServerHelloMsg, FrameType, QualitySettings,
    HealthPing, HealthPong, VideoCodec, ChromaSubsampling,
    VideoFrameFlags, AuthRequest, AuthResult, MonitorListMsg,
    ClipboardMsg, encode_video_header, encode_jpeg_header, encode_audio_header,
    AudioCodec, parse_message, generate_challenge,
)
from common.keymap import qt_key_to_linux_scancode
from server.screen_capture import ScreenCapture
from server.input_injector import InputInjector
from server.video_encoder import VideoEncoder, JpegFallbackEncoder, check_ffmpeg_available, detect_encoders
from server.audio_capture import AudioCapture, check_audio_available
from server.health import HealthMonitor
from server.auth import Authenticator
from server.clipboard import ClipboardSync
from common.udp_transport import UDPMediaServer, BandwidthEstimator, CHANNEL_VIDEO, CHANNEL_AUDIO
from common.hybrid_transport import HybridServerTransport, TransportMsg, TransportMode
from common.quic_transport import QUICTransportServer, quic_available

logger = logging.getLogger("teragucci.server")


class ClientSession:
    """Tracks per-client state."""

    def __init__(self, ws: WebSocketServerProtocol):
        self.ws = ws
        self.client_id = str(id(ws))
        self.authenticated = False
        self.challenge = ""
        self.quality = QualitySettings()
        self.monitor_id = 1  # Default to primary
        self.supports_h264 = True
        self.supports_h265 = False
        self.supports_yuv444 = True
        self.supports_audio = True
        self.send_queue: asyncio.Queue = asyncio.Queue(maxsize=30)
        self._send_task: Optional[asyncio.Task] = None

    def start_sender(self):
        self._send_task = asyncio.create_task(self._send_loop())

    async def _send_loop(self):
        """Drain send queue to avoid blocking the capture loop."""
        try:
            while True:
                data = await self.send_queue.get()
                if data is None:
                    break
                await self.ws.send(data)
        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception as e:
            logger.debug("Send error: %s", e)

    async def enqueue(self, data):
        """Non-blocking enqueue; drops frames if queue is full."""
        try:
            self.send_queue.put_nowait(data)
            return True
        except asyncio.QueueFull:
            return False

    def stop(self):
        if self._send_task:
            self.send_queue.put_nowait(None)


# --- Global state ---
clients: dict = {}  # ws -> ClientSession
capture: ScreenCapture = None
injector: InputInjector = None
encoder: Optional[VideoEncoder] = None
jpeg_encoder: Optional[JpegFallbackEncoder] = None
audio: Optional[AudioCapture] = None
health: HealthMonitor = None
auth: Authenticator = None
clipboard: Optional[ClipboardSync] = None
udp_server: Optional[UDPMediaServer] = None
hybrid_transport: Optional[HybridServerTransport] = None
bandwidth_estimator: Optional[BandwidthEstimator] = None
quic_server: Optional[QUICTransportServer] = None
quality_settings: QualitySettings = QualitySettings()
running = True
use_h264 = False
ffmpeg_caps: dict = {}
available_encoders: dict = {}
event_loop: Optional[asyncio.AbstractEventLoop] = None


async def handle_client(websocket: WebSocketServerProtocol):
    """Handle a single client connection lifecycle."""
    addr = websocket.remote_address
    session = ClientSession(websocket)
    logger.info("Client connected: %s", addr)

    try:
        # Authentication
        if auth.enabled:
            challenge = auth.create_challenge()
            session.challenge = challenge
            auth_req = AuthRequest(challenge=challenge)
            await websocket.send(auth_req.to_json())

            # Wait for auth response
            raw = await asyncio.wait_for(websocket.recv(), timeout=30)
            msg = parse_message(raw)
            if msg.get("type") != MsgType.AUTH_RESPONSE:
                await websocket.send(AuthResult(success=False, message="Expected auth response").to_json())
                return

            success = auth.verify(msg.get("username", ""), msg.get("credential", ""), challenge)
            await websocket.send(AuthResult(success=success,
                                           message="OK" if success else "Invalid credentials").to_json())
            if not success:
                return
            session.authenticated = True
        else:
            session.authenticated = True

        # Send server hello
        monitors = [asdict(m) for m in capture.list_monitors()]

        # Determine active encoder backend
        encoder_backend = ""
        if encoder:
            encoder_backend = encoder.active_backend

        hello = ServerHelloMsg(
            screen_width=capture.width,
            screen_height=capture.height,
            monitors=monitors,
            supports_h264=ffmpeg_caps.get("h264", False),
            supports_h265=ffmpeg_caps.get("h265", False),
            supports_av1=ffmpeg_caps.get("av1", False),
            supports_yuv444=ffmpeg_caps.get("h264_444", False),
            supports_audio=audio is not None and audio.available,
            supports_pen=True,
            requires_auth=auth.enabled,
            encoder_backend=encoder_backend,
            available_encoders=ffmpeg_caps.get("encoders", {}),
        )
        await websocket.send(hello.to_json())

        # Send monitor list
        mon_msg = MonitorListMsg(monitors=monitors)
        await websocket.send(mon_msg.to_json())

        # Register client and start sender
        clients[websocket] = session
        session.start_sender()
        health.clients_connected = len(clients)

        # Process incoming messages
        async for message in websocket:
            if isinstance(message, str):
                try:
                    msg = parse_message(message)
                    await _handle_control_message(session, msg)
                except json.JSONDecodeError:
                    logger.warning("Invalid JSON from %s", addr)
                except Exception as e:
                    logger.error("Error handling message from %s: %s", addr, e)

    except asyncio.TimeoutError:
        logger.warning("Client %s: auth timeout", addr)
    except websockets.exceptions.ConnectionClosed:
        logger.info("Client disconnected: %s", addr)
    except Exception as e:
        logger.error("Client error %s: %s", addr, e)
    finally:
        session.stop()
        if hybrid_transport:
            hybrid_transport.remove_client(session.client_id)
        clients.pop(websocket, None)
        health.clients_connected = len(clients)
        logger.info("Client removed: %s (total: %d)", addr, len(clients))


async def _handle_control_message(session: ClientSession, msg: dict):
    """Route control messages."""
    msg_type = msg.get("type")
    t0 = time.time()

    # --- UDP transport negotiation ---
    if msg_type in (TransportMsg.UDP_ANNOUNCE, TransportMsg.UDP_CONFIRMED,
                    TransportMsg.UDP_STATS):
        if hybrid_transport:
            # Fill in the client's IP from the WebSocket connection
            if msg_type == TransportMsg.UDP_ANNOUNCE:
                ws_addr = session.ws.remote_address
                if ws_addr:
                    msg["udp_addr"] = ws_addr[0]
            response = await hybrid_transport.handle_transport_message(
                session.client_id, msg, session.ws.send)
            if response:
                await session.ws.send(json.dumps(response))

            # Update bandwidth estimator from client stats
            if msg_type == TransportMsg.UDP_STATS and bandwidth_estimator:
                loss = msg.get("packet_loss_pct", 0.0)
                bandwidth_estimator.report_loss_rate(loss)
        return

    # --- Input events ---
    if msg_type == MsgType.KEY_EVENT:
        qt_key = msg.get("scan_code", 0)
        linux_code = qt_key_to_linux_scancode(qt_key)
        if linux_code == 0:
            return
        msg["scan_code"] = linux_code
        injector.handle_message(msg)

    elif msg_type in (MsgType.MOUSE_MOVE, MsgType.MOUSE_BUTTON,
                      MsgType.MOUSE_SCROLL, MsgType.PEN_EVENT):
        injector.handle_message(msg)

    elif msg_type == MsgType.REQUEST_FULL_FRAME:
        capture.invalidate()
        if encoder:
            encoder.request_keyframe()

    elif msg_type == MsgType.QUALITY_SETTINGS:
        _apply_quality_settings(session, msg)

    elif msg_type == MsgType.SELECT_MONITOR:
        mon_id = msg.get("monitor_id", 1)
        capture.switch_monitor(mon_id)
        session.monitor_id = mon_id
        # Restart encoder for new resolution
        _restart_encoder()

    elif msg_type == MsgType.HEALTH_PONG:
        health.record_pong(msg.get("sequence", 0), msg.get("ping_timestamp_ms", 0))

    elif msg_type == MsgType.CLIPBOARD_SEND:
        if clipboard:
            clipboard.set_clipboard(msg.get("data", ""))

    elif msg_type == MsgType.CLIENT_HELLO:
        session.supports_h264 = msg.get("supports_h264", True)
        session.supports_h265 = msg.get("supports_h265", False)
        session.supports_yuv444 = msg.get("supports_yuv444", True)
        session.supports_audio = msg.get("supports_audio", True)

    # Track input latency
    elapsed_ms = (time.time() - t0) * 1000
    health.record_input_latency(elapsed_ms)


def _apply_quality_settings(session: ClientSession, msg: dict):
    """Apply quality settings from client."""
    global quality_settings, use_h264
    session.quality = QualitySettings(**{k: v for k, v in msg.items()
                                        if k in QualitySettings.__dataclass_fields__})
    quality_settings = session.quality

    if quality_settings.codec in ("h264", "h265", "av1") and ffmpeg_caps.get(quality_settings.codec, False):
        if not use_h264:
            use_h264 = True
            _restart_encoder()
        elif encoder:
            encoder.update_settings(quality_settings)
    else:
        use_h264 = False

    # Update health monitor display
    health.current_codec = quality_settings.codec
    health.current_chroma = quality_settings.chroma
    health.target_fps = quality_settings.effective_fps()

    if audio:
        audio.update_bitrate(quality_settings.audio_bitrate_kbps)

    logger.info("Quality updated: bias=%.2f codec=%s chroma=%s fps=%d",
                quality_settings.quality_bias, quality_settings.codec,
                quality_settings.chroma, quality_settings.effective_fps())


def _restart_encoder():
    """Restart the video encoder for new settings/resolution."""
    global encoder
    if encoder:
        encoder.stop()
    encoder = VideoEncoder(capture.width, capture.height, quality_settings)
    encoder.start(_on_encoded_frame)
    health.current_resolution = f"{capture.width}x{capture.height}"


def _on_encoded_frame(frame_data: bytes, is_keyframe: bool):
    """Callback from encoder thread when a frame is ready."""
    timestamp = int(time.time() * 1000) & 0xFFFFFFFF

    # Send via QUIC to clients using QUIC transport
    if quic_server and quic_server.is_running and quic_server.client_count > 0:
        quic_server.send_video_to_all(frame_data, timestamp, is_keyframe)

    # Send via UDP to clients that support it
    if udp_server and hybrid_transport:
        has_udp_clients = any(
            hybrid_transport.should_use_udp(session.client_id)
            for session in clients.values()
            if session.authenticated
        )
        if has_udp_clients:
            udp_server.send_video_frame(frame_data, timestamp, is_keyframe)

    # Determine frame type and codec for TCP header
    codec_name = quality_settings.codec.lower()
    if codec_name == "av1":
        codec = VideoCodec.AV1
        frame_type = FrameType.VIDEO_AV1
    elif codec_name == "h265":
        codec = VideoCodec.H265
        frame_type = FrameType.VIDEO_H265
    else:
        codec = VideoCodec.H264
        frame_type = FrameType.VIDEO_H264

    chroma = quality_settings.effective_chroma()
    flags = VideoFrameFlags.KEYFRAME if is_keyframe else VideoFrameFlags.NONE

    header = encode_video_header(frame_type, codec, chroma, flags, timestamp)
    tcp_data = header + frame_data

    for ws, session in list(clients.items()):
        if session.authenticated:
            # Skip TCP send for clients already getting UDP or QUIC
            if hybrid_transport and hybrid_transport.should_use_udp(session.client_id):
                continue
            if event_loop:
                asyncio.run_coroutine_threadsafe(_enqueue_frame(session, tcp_data), event_loop)

    health.record_frame_sent(len(frame_data))


async def _enqueue_frame(session: ClientSession, data: bytes):
    """Enqueue a frame for a client, tracking drops."""
    if not await session.enqueue(data):
        health.record_frame_dropped()


def _on_audio_frame(audio_data: bytes, timestamp_ms: int):
    """Callback from audio capture thread."""
    ts = timestamp_ms & 0xFFFFFFFF

    # Send via QUIC
    if quic_server and quic_server.is_running and quic_server.client_count > 0:
        quic_server.send_audio_to_all(audio_data, ts)

    # Send via UDP where available
    if udp_server and hybrid_transport:
        has_udp_audio = any(
            hybrid_transport.should_use_udp(s.client_id) and s.supports_audio
            for s in clients.values() if s.authenticated
        )
        if has_udp_audio:
            udp_server.send_audio_frame(audio_data, ts)

    # TCP fallback for non-UDP clients
    header = encode_audio_header(AudioCodec.OPUS, ts)
    data = header + audio_data

    for ws, session in list(clients.items()):
        if session.authenticated and session.supports_audio:
            if hybrid_transport and hybrid_transport.should_use_udp(session.client_id):
                continue
            if event_loop:
                asyncio.run_coroutine_threadsafe(session.enqueue(data), event_loop)


def _on_clipboard_change(text: str):
    """Callback from clipboard monitor when content changes."""
    msg = ClipboardMsg(type=MsgType.CLIPBOARD_RECV, data=text)
    json_str = msg.to_json()

    loop = asyncio.get_event_loop() if asyncio.get_event_loop().is_running() else None
    for ws, session in list(clients.items()):
        if session.authenticated and loop:
            asyncio.run_coroutine_threadsafe(session.enqueue(json_str), loop)


async def stream_frames_jpeg(fps: int):
    """JPEG fallback: capture and stream dirty regions."""
    frame_interval = 1.0 / fps
    while running:
        start = time.time()
        if clients:
            try:
                capture_start = time.time()
                regions = capture.capture_dirty_regions()
                health.record_capture_time((time.time() - capture_start) * 1000)

                for x, y, w, h, jpeg_data in regions:
                    ft = FrameType.VIDEO_FULL if (x == 0 and y == 0 and
                         w == capture.width and h == capture.height) else FrameType.VIDEO_PARTIAL
                    header = encode_jpeg_header(ft, x, y, w, h)
                    data = header + jpeg_data
                    health.record_frame_sent(len(data))

                    for ws, session in list(clients.items()):
                        if session.authenticated:
                            if not await session.enqueue(data):
                                health.record_frame_dropped()
            except Exception as e:
                logger.error("JPEG frame capture error: %s", e)

        elapsed = time.time() - start
        sleep_time = frame_interval - elapsed
        if sleep_time > 0:
            await asyncio.sleep(sleep_time)
        else:
            await asyncio.sleep(0.001)


async def stream_frames_h264(fps: int):
    """H.264/H.265 mode: feed raw frames to FFmpeg encoder."""
    frame_interval = 1.0 / fps
    while running:
        start = time.time()
        if clients and encoder:
            try:
                capture_start = time.time()
                raw = capture.capture_raw_bgra()
                health.record_capture_time((time.time() - capture_start) * 1000)
                encoder.feed_frame(raw)
            except Exception as e:
                logger.error("H264 frame capture error: %s", e)

        elapsed = time.time() - start
        sleep_time = frame_interval - elapsed
        if sleep_time > 0:
            await asyncio.sleep(sleep_time)
        else:
            await asyncio.sleep(0.001)


async def health_ping_loop():
    """Periodically ping clients and broadcast health stats."""
    while running:
        await asyncio.sleep(2.0)
        if not clients:
            continue

        # Send pings
        seq = health.next_ping_sequence()
        ping = HealthPing(sequence=seq)
        ping_json = ping.to_json()

        # Send stats
        stats = health.get_stats()
        stats_json = stats.to_json()

        for ws, session in list(clients.items()):
            if session.authenticated:
                try:
                    await session.enqueue(ping_json)
                    await session.enqueue(stats_json)
                except Exception:
                    pass


async def monitor_hotplug_loop():
    """Periodically check for monitor configuration changes."""
    while running:
        await asyncio.sleep(5.0)
        if capture and capture.detect_hotplug():
            # Notify all clients of new monitor list
            monitors = [asdict(m) for m in capture.list_monitors()]
            msg = MonitorListMsg(monitors=monitors)
            msg_json = msg.to_json()
            for ws, session in list(clients.items()):
                if session.authenticated:
                    try:
                        await session.enqueue(msg_json)
                    except Exception:
                        pass
            # Restart encoder for potentially new resolution
            if encoder:
                _restart_encoder()


async def run_server(host: str, port: int, fps: int, tls_context: Optional[ssl.SSLContext],
                     udp_port: int = 0, quic_port: int = 0,
                     tls_cert: str = None, tls_key: str = None):
    """Start the WebSocket server and all subsystems."""
    global running, event_loop

    event_loop = asyncio.get_event_loop()
    logger.info("Starting Teragucci server on %s:%d (target %d fps)", host, port, fps)
    if tls_context:
        logger.info("TLS enabled")

    # Start UDP media server
    if udp_server:
        try:
            udp_server.start()
            logger.info("UDP media transport on %s:%d", host, udp_port or port)
        except Exception as e:
            logger.warning("UDP server failed to start: %s (TCP-only mode)", e)

    # Start QUIC transport
    if quic_server:
        try:
            started = await quic_server.start(cert_file=tls_cert, key_file=tls_key)
            if started:
                logger.info("QUIC transport on %s:%d", host, quic_port or port)
        except Exception as e:
            logger.warning("QUIC server failed to start: %s", e)

    # Start subsystems
    if use_h264 and encoder:
        stream_task = asyncio.create_task(stream_frames_h264(fps))
    else:
        stream_task = asyncio.create_task(stream_frames_jpeg(fps))

    health_task = asyncio.create_task(health_ping_loop())
    hotplug_task = asyncio.create_task(monitor_hotplug_loop())

    # Start audio if available
    if audio and audio.available and quality_settings.enable_audio:
        audio.start(_on_audio_frame)

    # Start clipboard sync
    if clipboard and clipboard.available:
        clipboard.start_monitoring(_on_clipboard_change)

    # Signal handling
    stop = asyncio.Future()

    def signal_handler():
        nonlocal running
        running = False
        if not stop.done():
            stop.set_result(None)

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)

    async with websockets.serve(
        handle_client, host, port,
        ssl=tls_context,
        max_size=50 * 1024 * 1024,
        ping_interval=20,
        ping_timeout=30,
    ):
        logger.info("Server ready. Waiting for connections...")
        await stop

    running = False
    stream_task.cancel()
    health_task.cancel()
    hotplug_task.cancel()
    for task in (stream_task, health_task, hotplug_task):
        try:
            await task
        except asyncio.CancelledError:
            pass


def create_tls_context(cert_file: str, key_file: str) -> ssl.SSLContext:
    """Create TLS context for secure WebSocket connections."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert_file, key_file)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    return ctx


def main():
    global capture, injector, encoder, jpeg_encoder, audio, health, auth
    global clipboard, quality_settings, use_h264, ffmpeg_caps, available_encoders
    global quic_server

    parser = argparse.ArgumentParser(description="Teragucci Remote Desktop Server")
    parser.add_argument("--host", default="0.0.0.0", help="Listen address")
    parser.add_argument("--port", type=int, default=443, help="Listen port (TCP WebSocket + UDP media)")
    parser.add_argument("--udp-port", type=int, default=0, help="UDP media port (default: same as --port)")
    parser.add_argument("--quic-port", type=int, default=0, help="QUIC transport port (default: same as --port)")
    parser.add_argument("--no-udp", action="store_true", help="Disable UDP transport")
    parser.add_argument("--no-quic", action="store_true", help="Disable QUIC transport")
    parser.add_argument("--fps", type=int, default=30, help="Target FPS")
    parser.add_argument("--quality", type=int, default=60, help="JPEG quality (fallback)")
    parser.add_argument("--monitor", type=int, default=1, help="Monitor index (0=all)")
    parser.add_argument("--codec", choices=["h264", "h265", "av1", "jpeg"], default="h264",
                        help="Video codec")
    parser.add_argument("--chroma", choices=["yuv420", "yuv422", "yuv444"], default="yuv444",
                        help="Chroma subsampling")
    parser.add_argument("--lossless", action="store_true", help="Lossless mode")
    parser.add_argument("--max-bandwidth", type=float, default=50.0, help="Max bandwidth (Mbps)")
    parser.add_argument("--tls-cert", help="TLS certificate file")
    parser.add_argument("--tls-key", help="TLS key file")
    parser.add_argument("--no-auth", action="store_true", help="Disable authentication")
    parser.add_argument("--no-audio", action="store_true", help="Disable audio")
    parser.add_argument("--no-clipboard", action="store_true", help="Disable clipboard sync")
    parser.add_argument("--sw-only", action="store_true", help="Force software encoding (no GPU)")
    parser.add_argument("--add-user", metavar="USERNAME", help="Add/update a user and exit")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Handle --add-user
    if args.add_user:
        import getpass
        auth = Authenticator(enabled=True)
        password = getpass.getpass(f"Password for '{args.add_user}': ")
        auth.add_user(args.add_user, password)
        print(f"User '{args.add_user}' added/updated.")
        return

    # Check capabilities
    ffmpeg_caps = check_ffmpeg_available()
    available_encoders = detect_encoders()
    logger.info("FFmpeg capabilities: %s", {k: v for k, v in ffmpeg_caps.items() if k != "encoders"})

    # Log detected hardware encoders
    hw_backends = ffmpeg_caps.get("hw_backends", [])
    if hw_backends:
        logger.info("GPU encoding available: %s", ", ".join(hw_backends))
    else:
        logger.info("No GPU encoding detected — using software encoders")

    for codec, encs in available_encoders.items():
        if encs:
            names = [e.name for e in encs]
            logger.info("  %s encoders: %s", codec.upper(), ", ".join(names))

    audio_available = not args.no_audio and check_audio_available()
    logger.info("Audio available: %s", audio_available)

    # Quality settings from CLI args
    quality_settings = QualitySettings(
        quality_bias=0.5,
        max_fps=args.fps,
        max_bandwidth_mbps=args.max_bandwidth,
        codec=args.codec,
        chroma=args.chroma,
        force_lossless=args.lossless,
        enable_audio=not args.no_audio,
    )

    # Initialize subsystems
    try:
        capture = ScreenCapture(monitor_index=args.monitor, jpeg_quality=args.quality)
        injector = InputInjector(screen_width=capture.width, screen_height=capture.height)
    except Exception as e:
        logger.error("Failed to initialize: %s", e)
        logger.error("Ensure access to /dev/uinput and a display. Run: sudo bash server/setup_uinput.sh")
        sys.exit(1)

    # Video encoder (with GPU acceleration auto-detection)
    use_h264 = args.codec in ("h264", "h265", "av1") and ffmpeg_caps.get(args.codec, False)
    if use_h264:
        # If --sw-only, filter out hardware encoders
        enc_list = available_encoders if not args.sw_only else None
        if args.sw_only:
            from server.video_encoder import HWEncoder
            enc_list = {}
            for codec, encs in available_encoders.items():
                enc_list[codec] = [e for e in encs if e.backend == "software"]

        encoder = VideoEncoder(capture.width, capture.height, quality_settings,
                               available_encoders=enc_list)
        encoder.start(_on_encoded_frame)
        logger.info("Using %s encoder (%s backend) with %s",
                     args.codec.upper(), encoder.active_backend, args.chroma.upper())
    else:
        jpeg_encoder = JpegFallbackEncoder(quality=args.quality)
        logger.info("Using JPEG fallback encoder")

    # UDP media transport
    actual_udp_port = args.udp_port or args.port
    if not args.no_udp:
        udp_server = UDPMediaServer(host=args.host, port=actual_udp_port)
        hybrid_transport = HybridServerTransport(udp_server)
        bandwidth_estimator = BandwidthEstimator(
            initial_mbps=quality_settings.max_bandwidth_mbps,
            max_mbps=quality_settings.max_bandwidth_mbps,
        )
        logger.info("UDP media transport configured on port %d", actual_udp_port)
    else:
        logger.info("UDP disabled")

    # QUIC transport
    actual_quic_port = args.quic_port or (args.port + 1)
    if not args.no_quic and quic_available():
        quic_server = QUICTransportServer(host=args.host, port=actual_quic_port)
        logger.info("QUIC transport configured on port %d", actual_quic_port)
    elif args.no_quic:
        logger.info("QUIC disabled")
    else:
        logger.info("QUIC unavailable (install aioquic)")

    # Health monitor
    health = HealthMonitor(target_fps=args.fps)
    health.current_codec = args.codec
    health.current_chroma = args.chroma
    health.current_resolution = f"{capture.width}x{capture.height}"

    # Auth
    auth = Authenticator(enabled=not args.no_auth)

    # Audio
    if audio_available:
        audio = AudioCapture(bitrate_kbps=quality_settings.audio_bitrate_kbps)

    # Clipboard
    if not args.no_clipboard:
        clipboard = ClipboardSync()

    # TLS
    tls_context = None
    if args.tls_cert and args.tls_key:
        tls_context = create_tls_context(args.tls_cert, args.tls_key)

    # Run
    try:
        asyncio.run(run_server(args.host, args.port, args.fps, tls_context,
                               udp_port=actual_udp_port,
                               quic_port=actual_quic_port,
                               tls_cert=args.tls_cert, tls_key=args.tls_key))
    except KeyboardInterrupt:
        logger.info("Interrupted")
    finally:
        if quic_server:
            quic_server.stop()
        if udp_server:
            udp_server.stop()
        if encoder:
            encoder.stop()
        if audio:
            audio.stop()
        if clipboard:
            clipboard.stop()
        if injector:
            injector.close()
        if capture:
            capture.close()


if __name__ == "__main__":
    main()
