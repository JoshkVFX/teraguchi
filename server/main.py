#!/usr/bin/env python3
"""
Teragucci Server - Linux Remote Desktop Server v4

PCoIP / HP Anyware-like remote desktop with:
- PAM authentication (Linux system users, LDAP, FreeIPA)
- Per-user X sessions via Xvfb (sessions persist across disconnections)
- H.264/H.265/AV1 video encoding with GPU acceleration
- YUV 4:4:4 chroma support
- Wacom pen/tablet pressure injection via uinput
- Audio streaming via PulseAudio/PipeWire
- Multi-monitor support
- Adaptive quality control
- Hybrid TCP+UDP+QUIC transport

Auth modes:
  --auth-mode pam    Authenticate via PAM (PCoIP-like, per-user sessions)
  --auth-mode local  Legacy JSON user database, single shared display
  --auth-mode none   No authentication, single shared display

Usage:
    sudo python -m server.main --auth-mode pam
    python -m server.main --auth-mode none --verbose
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
import threading
import time
from dataclasses import asdict
from typing import Set, Optional, Dict

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
from server.xtest_injector import XTestInputInjector
from server.video_encoder import VideoEncoder, JpegFallbackEncoder, check_ffmpeg_available, detect_encoders
from server.audio_capture import AudioCapture, check_audio_available
from server.health import HealthMonitor
from server.auth import Authenticator
from server.clipboard import ClipboardSync
from common.udp_transport import UDPMediaServer, BandwidthEstimator, CHANNEL_VIDEO, CHANNEL_AUDIO
from common.hybrid_transport import HybridServerTransport, TransportMsg, TransportMode
from common.quic_transport import QUICTransportServer, quic_available

logger = logging.getLogger("teragucci.server")


# ═══════════════════════════════════════════════════════════════
# Per-User Session Runtime
# ═══════════════════════════════════════════════════════════════

class SessionRuntime:
    """
    Runtime state for one user's remote desktop session.

    In PAM mode, each authenticated user gets their own SessionRuntime
    with an isolated Xvfb display, capture pipeline, input injection,
    and video encoder. Multiple clients can share a session (reconnection).

    In legacy mode (local/none auth), there is one global SessionRuntime
    attached to the host's DISPLAY.
    """

    def __init__(self, display: str, username: str, quality: QualitySettings,
                 ffmpeg_caps: dict, available_encoders: dict,
                 no_audio: bool = False, no_clipboard: bool = False,
                 sw_only: bool = False, monitor_index: int = 1,
                 jpeg_quality: int = 60):
        self.display = display
        self.username = username
        self.quality = quality
        self.clients: Dict[WebSocketServerProtocol, "ClientSession"] = {}
        self._lock = threading.Lock()
        self._event_loop: Optional[asyncio.AbstractEventLoop] = None

        # Set DISPLAY for this session's subsystems
        old_display = os.environ.get("DISPLAY", "")
        os.environ["DISPLAY"] = display

        try:
            self.capture = ScreenCapture(monitor_index=monitor_index,
                                         jpeg_quality=jpeg_quality)
            # Use XTest for virtual displays (Xvfb), uinput for physical
            if display.startswith(":") and int(display[1:]) >= 10:
                try:
                    self.injector = XTestInputInjector(display,
                                                       screen_width=self.capture.width,
                                                       screen_height=self.capture.height)
                except Exception as xinj_err:
                    logger.warning("XTest unavailable: %s, using uinput", xinj_err)
                    self.injector = InputInjector(screen_width=self.capture.width,
                                                   screen_height=self.capture.height)
            else:
                self.injector = InputInjector(screen_width=self.capture.width,
                                              screen_height=self.capture.height)
        finally:
            if old_display:
                os.environ["DISPLAY"] = old_display
            else:
                os.environ.pop("DISPLAY", None)

        # Video encoder
        self.encoder: Optional[VideoEncoder] = None
        self.jpeg_encoder: Optional[JpegFallbackEncoder] = None
        self.use_h264 = False
        self.ffmpeg_caps = ffmpeg_caps
        self.available_encoders = available_encoders

        codec = quality.codec
        if codec in ("h264", "h265", "av1") and ffmpeg_caps.get(codec, False):
            self.use_h264 = True
            enc_list = available_encoders
            if sw_only:
                enc_list = {}
                for c, encs in available_encoders.items():
                    enc_list[c] = [e for e in encs if e.backend == "software"]
            self.encoder = VideoEncoder(self.capture.width, self.capture.height,
                                        quality, available_encoders=enc_list)
            self.encoder.start(self._on_encoded_frame)
            logger.info("[%s] Encoder: %s (%s) %s", username, codec.upper(),
                        self.encoder.active_backend, quality.chroma.upper())
        else:
            self.jpeg_encoder = JpegFallbackEncoder(quality=jpeg_quality)
            logger.info("[%s] Using JPEG fallback encoder", username)

        # Health monitor
        self.health = HealthMonitor(target_fps=quality.effective_fps())
        self.health.current_codec = quality.codec
        self.health.current_chroma = quality.chroma
        self.health.current_resolution = f"{self.capture.width}x{self.capture.height}"

        # Audio
        self.audio: Optional[AudioCapture] = None
        if not no_audio and check_audio_available():
            self.audio = AudioCapture(bitrate_kbps=quality.audio_bitrate_kbps)

        # Clipboard
        self.clipboard: Optional[ClipboardSync] = None
        if not no_clipboard:
            old_display2 = os.environ.get("DISPLAY", "")
            os.environ["DISPLAY"] = display
            try:
                self.clipboard = ClipboardSync()
            finally:
                if old_display2:
                    os.environ["DISPLAY"] = old_display2
                else:
                    os.environ.pop("DISPLAY", None)

        # Streaming state
        self._streaming = False
        self._stream_task: Optional[asyncio.Task] = None
        self._health_task: Optional[asyncio.Task] = None
        self._hotplug_task: Optional[asyncio.Task] = None
        self._running = True

        logger.info("[%s] Session runtime ready on %s (%dx%d)",
                    username, display, self.capture.width, self.capture.height)

    def set_event_loop(self, loop: asyncio.AbstractEventLoop):
        self._event_loop = loop

    # ── Client management ────────────────────────────────────

    def add_client(self, ws: WebSocketServerProtocol, session: "ClientSession"):
        with self._lock:
            self.clients[ws] = session
            self.health.clients_connected = len(self.clients)
        if not self._streaming:
            self._start_streaming()

    def remove_client(self, ws: WebSocketServerProtocol):
        with self._lock:
            self.clients.pop(ws, None)
            self.health.clients_connected = len(self.clients)
        # Session persists — don't stop streaming
        # (PCoIP behavior: session stays alive for reconnection)

    @property
    def client_count(self) -> int:
        return len(self.clients)

    # ── Streaming ────────────────────────────────────────────

    def _start_streaming(self):
        if self._streaming:
            return
        self._streaming = True
        fps = self.quality.effective_fps()

        if self.use_h264 and self.encoder:
            self._stream_task = asyncio.ensure_future(self._stream_h264(fps))
        else:
            self._stream_task = asyncio.ensure_future(self._stream_jpeg(fps))

        self._health_task = asyncio.ensure_future(self._health_ping_loop())
        self._hotplug_task = asyncio.ensure_future(self._monitor_hotplug_loop())

        if self.audio and self.audio.available and self.quality.enable_audio:
            self.audio.start(self._on_audio_frame)

        if self.clipboard and self.clipboard.available:
            self.clipboard.start_monitoring(self._on_clipboard_change)

        logger.info("[%s] Streaming started (%d fps)", self.username, fps)

    async def _stream_h264(self, fps: int):
        interval = 1.0 / fps
        while self._running:
            start = time.time()
            if self.clients and self.encoder:
                try:
                    t0 = time.time()
                    raw = self.capture.capture_raw_bgra()
                    self.health.record_capture_time((time.time() - t0) * 1000)
                    self.encoder.feed_frame(raw)
                except Exception as e:
                    logger.error("[%s] H264 capture error: %s", self.username, e)
            elapsed = time.time() - start
            await asyncio.sleep(max(interval - elapsed, 0.001))

    async def _stream_jpeg(self, fps: int):
        interval = 1.0 / fps
        while self._running:
            start = time.time()
            if self.clients:
                try:
                    t0 = time.time()
                    regions = self.capture.capture_dirty_regions()
                    self.health.record_capture_time((time.time() - t0) * 1000)
                    for x, y, w, h, jpeg_data in regions:
                        ft = (FrameType.VIDEO_FULL
                              if (x == 0 and y == 0 and
                                  w == self.capture.width and h == self.capture.height)
                              else FrameType.VIDEO_PARTIAL)
                        header = encode_jpeg_header(ft, x, y, w, h)
                        data = header + jpeg_data
                        self.health.record_frame_sent(len(data))
                        for ws, cs in list(self.clients.items()):
                            if cs.authenticated:
                                if not await cs.enqueue(data):
                                    self.health.record_frame_dropped()
                except Exception as e:
                    logger.error("[%s] JPEG capture error: %s", self.username, e)
            elapsed = time.time() - start
            await asyncio.sleep(max(interval - elapsed, 0.001))

    async def _health_ping_loop(self):
        while self._running:
            await asyncio.sleep(2.0)
            if not self.clients:
                continue
            seq = self.health.next_ping_sequence()
            ping_json = HealthPing(sequence=seq).to_json()
            stats_json = self.health.get_stats().to_json()
            for ws, cs in list(self.clients.items()):
                if cs.authenticated:
                    try:
                        await cs.enqueue(ping_json)
                        await cs.enqueue(stats_json)
                    except Exception:
                        pass

    async def _monitor_hotplug_loop(self):
        while self._running:
            await asyncio.sleep(5.0)
            if self.capture and self.capture.detect_hotplug():
                monitors = [asdict(m) for m in self.capture.list_monitors()]
                msg_json = MonitorListMsg(monitors=monitors).to_json()
                for ws, cs in list(self.clients.items()):
                    if cs.authenticated:
                        try:
                            await cs.enqueue(msg_json)
                        except Exception:
                            pass
                if self.encoder:
                    self._restart_encoder()

    # ── Encoder callbacks ────────────────────────────────────

    def _on_encoded_frame(self, frame_data: bytes, is_keyframe: bool):
        timestamp = int(time.time() * 1000) & 0xFFFFFFFF
        codec_name = self.quality.codec.lower()
        if codec_name == "av1":
            codec, frame_type = VideoCodec.AV1, FrameType.VIDEO_AV1
        elif codec_name == "h265":
            codec, frame_type = VideoCodec.H265, FrameType.VIDEO_H265
        else:
            codec, frame_type = VideoCodec.H264, FrameType.VIDEO_H264

        chroma = self.quality.effective_chroma()
        flags = VideoFrameFlags.KEYFRAME if is_keyframe else VideoFrameFlags.NONE
        header = encode_video_header(frame_type, codec, chroma, flags, timestamp)
        tcp_data = header + frame_data

        for ws, cs in list(self.clients.items()):
            if cs.authenticated and self._event_loop:
                asyncio.run_coroutine_threadsafe(
                    self._enqueue_frame(cs, tcp_data), self._event_loop)

        self.health.record_frame_sent(len(frame_data))

    async def _enqueue_frame(self, cs: "ClientSession", data: bytes):
        if not await cs.enqueue(data):
            self.health.record_frame_dropped()

    def _on_audio_frame(self, audio_data: bytes, timestamp_ms: int):
        ts = timestamp_ms & 0xFFFFFFFF
        header = encode_audio_header(AudioCodec.OPUS, ts)
        data = header + audio_data
        for ws, cs in list(self.clients.items()):
            if cs.authenticated and cs.supports_audio and self._event_loop:
                asyncio.run_coroutine_threadsafe(cs.enqueue(data), self._event_loop)

    def _on_clipboard_change(self, text: str):
        msg_json = ClipboardMsg(type=MsgType.CLIPBOARD_RECV, data=text).to_json()
        for ws, cs in list(self.clients.items()):
            if cs.authenticated and self._event_loop:
                asyncio.run_coroutine_threadsafe(cs.enqueue(msg_json), self._event_loop)

    # ── Quality / encoder management ─────────────────────────

    def apply_quality(self, session: "ClientSession", msg: dict):
        session.quality = QualitySettings(**{k: v for k, v in msg.items()
                                             if k in QualitySettings.__dataclass_fields__})
        self.quality = session.quality

        if self.quality.codec in ("h264", "h265", "av1") and \
           self.ffmpeg_caps.get(self.quality.codec, False):
            if not self.use_h264:
                self.use_h264 = True
                self._restart_encoder()
            elif self.encoder:
                self.encoder.update_settings(self.quality)
        else:
            self.use_h264 = False

        self.health.current_codec = self.quality.codec
        self.health.current_chroma = self.quality.chroma
        self.health.target_fps = self.quality.effective_fps()

        if self.audio:
            self.audio.update_bitrate(self.quality.audio_bitrate_kbps)

    def _restart_encoder(self):
        if self.encoder:
            old_available = self.encoder._available
            self.encoder.stop()
        else:
            old_available = None
        self.encoder = VideoEncoder(self.capture.width, self.capture.height,
                                     self.quality,
                                     available_encoders=old_available)
        self.encoder.start(self._on_encoded_frame)
        self.health.current_resolution = f"{self.capture.width}x{self.capture.height}"

    # ── Input handling ───────────────────────────────────────

    def handle_input(self, session: "ClientSession", msg: dict):
        msg_type = msg.get("type")
        t0 = time.time()

        if msg_type == MsgType.KEY_EVENT:
            if isinstance(self.injector, XTestInputInjector):
                # XTest uses Qt key codes directly
                self.injector.handle_message(msg)
            else:
                qt_key = msg.get("scan_code", 0)
                linux_code = qt_key_to_linux_scancode(qt_key)
                if linux_code == 0:
                    return
                msg["scan_code"] = linux_code
                self.injector.handle_message(msg)

        elif msg_type in (MsgType.MOUSE_MOVE, MsgType.MOUSE_BUTTON,
                          MsgType.MOUSE_SCROLL, MsgType.PEN_EVENT):
            self.injector.handle_message(msg)

        elif msg_type == MsgType.REQUEST_FULL_FRAME:
            self.capture.invalidate()
            if self.encoder:
                self.encoder.request_keyframe()

        elif msg_type == MsgType.QUALITY_SETTINGS:
            self.apply_quality(session, msg)

        elif msg_type == MsgType.SELECT_MONITOR:
            self.capture.switch_monitor(msg.get("monitor_id", 1))
            self._restart_encoder()

        elif msg_type == MsgType.HEALTH_PONG:
            self.health.record_pong(msg.get("sequence", 0),
                                    msg.get("ping_timestamp_ms", 0))

        elif msg_type == MsgType.CLIPBOARD_SEND:
            if self.clipboard:
                self.clipboard.set_clipboard(msg.get("data", ""))

        elif msg_type == MsgType.CLIENT_HELLO:
            session.supports_h264 = msg.get("supports_h264", True)
            session.supports_h265 = msg.get("supports_h265", False)
            session.supports_yuv444 = msg.get("supports_yuv444", True)
            session.supports_audio = msg.get("supports_audio", True)

        elapsed_ms = (time.time() - t0) * 1000
        self.health.record_input_latency(elapsed_ms)

    # ── Shutdown ─────────────────────────────────────────────

    def stop(self):
        self._running = False
        for task in (self._stream_task, self._health_task, self._hotplug_task):
            if task:
                task.cancel()
        if self.encoder:
            self.encoder.stop()
        if self.audio:
            self.audio.stop()
        if self.clipboard:
            self.clipboard.stop()
        if self.injector:
            self.injector.close()
        if self.capture:
            self.capture.close()
        logger.info("[%s] Session runtime stopped", self.username)


# ═══════════════════════════════════════════════════════════════
# Client Session (per WebSocket connection)
# ═══════════════════════════════════════════════════════════════

class ClientSession:
    """Tracks per-client connection state."""

    def __init__(self, ws: WebSocketServerProtocol):
        self.ws = ws
        self.client_id = str(id(ws))
        self.authenticated = False
        self.username = ""
        self.challenge = ""
        self.quality = QualitySettings()
        self.monitor_id = 1
        self.supports_h264 = True
        self.supports_h265 = False
        self.supports_yuv444 = True
        self.supports_audio = True
        self.runtime: Optional[SessionRuntime] = None
        self.send_queue: asyncio.Queue = asyncio.Queue(maxsize=30)
        self._send_task: Optional[asyncio.Task] = None

    def start_sender(self):
        self._send_task = asyncio.create_task(self._send_loop())

    async def _send_loop(self):
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
        try:
            self.send_queue.put_nowait(data)
            return True
        except asyncio.QueueFull:
            return False

    def stop(self):
        if self._send_task:
            self.send_queue.put_nowait(None)


# ═══════════════════════════════════════════════════════════════
# Server
# ═══════════════════════════════════════════════════════════════

# Global state
auth: Authenticator = None
session_mgr = None   # SessionManager (PAM mode only)
runtimes: Dict[str, SessionRuntime] = {}   # username -> SessionRuntime
default_runtime: Optional[SessionRuntime] = None  # Legacy mode
quality_settings: QualitySettings = QualitySettings()
ffmpeg_caps: dict = {}
available_encoders: dict = {}
running = True
server_args = None  # Parsed CLI args


async def handle_client(websocket: WebSocketServerProtocol):
    """Handle a single client connection lifecycle."""
    addr = websocket.remote_address
    session = ClientSession(websocket)
    logger.info("Client connected: %s", addr)
    runtime = None

    try:
        # ── Authentication ───────────────────────────────────
        if auth.enabled:
            if auth.mode == "pam":
                # PAM mode: request username + password directly
                auth_req = AuthRequest(
                    challenge="",
                    auth_methods=["pam"],
                )
                # Add auth_mode to the JSON so client knows to send password
                req_dict = json.loads(auth_req.to_json())
                req_dict["auth_mode"] = "pam"
                await websocket.send(json.dumps(req_dict))

                raw = await asyncio.wait_for(websocket.recv(), timeout=30)
                msg = parse_message(raw)
                if msg.get("type") != MsgType.AUTH_RESPONSE:
                    await websocket.send(
                        AuthResult(success=False, message="Expected auth response").to_json())
                    return

                username = msg.get("username", "")
                password = msg.get("credential", "")
                success = auth.verify_pam(username, password)

                await websocket.send(
                    AuthResult(success=success,
                               message="OK" if success else "Invalid credentials").to_json())
                if not success:
                    return

                session.authenticated = True
                session.username = username

            else:
                # Local mode: challenge-response
                challenge = auth.create_challenge()
                session.challenge = challenge
                auth_req = AuthRequest(challenge=challenge)
                req_dict = json.loads(auth_req.to_json())
                req_dict["auth_mode"] = "local"
                await websocket.send(json.dumps(req_dict))

                raw = await asyncio.wait_for(websocket.recv(), timeout=30)
                msg = parse_message(raw)
                if msg.get("type") != MsgType.AUTH_RESPONSE:
                    await websocket.send(
                        AuthResult(success=False, message="Expected auth response").to_json())
                    return

                success = auth.verify(msg.get("username", ""),
                                      msg.get("credential", ""), challenge)
                await websocket.send(
                    AuthResult(success=success,
                               message="OK" if success else "Invalid credentials").to_json())
                if not success:
                    return

                session.authenticated = True
                session.username = msg.get("username", "unknown")
        else:
            session.authenticated = True
            session.username = "anonymous"

        # ── Get or create session runtime ────────────────────
        if auth.mode == "pam" and session_mgr is not None:
            # PAM mode: per-user X session
            user_info = auth.get_user_info(session.username)
            if not user_info:
                await websocket.send(
                    AuthResult(success=False,
                               message=f"System user '{session.username}' not found").to_json())
                return

            from server.session_manager import SessionManager
            user_session = session_mgr.create_session(
                session.username, user_info["uid"], user_info["gid"], user_info["home"],
                width=server_args.width if hasattr(server_args, 'width') else 0,
                height=server_args.height if hasattr(server_args, 'height') else 0)

            # Get or create runtime for this user
            if session.username not in runtimes:
                runtime = SessionRuntime(
                    display=user_session.display,
                    username=session.username,
                    quality=quality_settings,
                    ffmpeg_caps=ffmpeg_caps,
                    available_encoders=available_encoders,
                    no_audio=server_args.no_audio,
                    no_clipboard=server_args.no_clipboard,
                    sw_only=server_args.sw_only,
                    monitor_index=server_args.monitor,
                    jpeg_quality=server_args.quality,
                )
                runtime.set_event_loop(asyncio.get_event_loop())
                runtimes[session.username] = runtime
            else:
                runtime = runtimes[session.username]

            logger.info("User %s → session %s", session.username, user_session.display)

        else:
            # Legacy mode: single shared runtime
            runtime = default_runtime

        if runtime is None:
            logger.error("No runtime available")
            return

        session.runtime = runtime

        # ── Send server hello ────────────────────────────────
        monitors = [asdict(m) for m in runtime.capture.list_monitors()]
        encoder_backend = runtime.encoder.active_backend if runtime.encoder else ""

        hello = ServerHelloMsg(
            screen_width=runtime.capture.width,
            screen_height=runtime.capture.height,
            monitors=monitors,
            supports_h264=ffmpeg_caps.get("h264", False),
            supports_h265=ffmpeg_caps.get("h265", False),
            supports_av1=ffmpeg_caps.get("av1", False),
            supports_yuv444=ffmpeg_caps.get("h264_444", False),
            supports_audio=runtime.audio is not None and runtime.audio.available,
            supports_pen=True,
            requires_auth=auth.enabled,
            encoder_backend=encoder_backend,
            available_encoders=ffmpeg_caps.get("encoders", {}),
        )
        await websocket.send(hello.to_json())

        mon_msg = MonitorListMsg(monitors=monitors)
        await websocket.send(mon_msg.to_json())

        # Register client
        runtime.add_client(websocket, session)
        session.start_sender()

        # ── Process messages ─────────────────────────────────
        async for message in websocket:
            if isinstance(message, str):
                try:
                    msg = parse_message(message)
                    runtime.handle_input(session, msg)
                except json.JSONDecodeError:
                    logger.warning("Invalid JSON from %s", addr)
                except Exception as e:
                    logger.error("Error from %s: %s", addr, e)

    except asyncio.TimeoutError:
        logger.warning("Client %s: auth timeout", addr)
    except websockets.exceptions.ConnectionClosed:
        logger.info("Client disconnected: %s", addr)
    except Exception as e:
        logger.error("Client error %s: %s", addr, e)
    finally:
        session.stop()
        if runtime:
            runtime.remove_client(websocket)
        logger.info("Client removed: %s (%s)", addr, session.username)


async def run_server(host: str, port: int, tls_context: Optional[ssl.SSLContext]):
    """Start the WebSocket server."""
    global running

    logger.info("Starting Teragucci server on %s:%d", host, port)
    if tls_context:
        logger.info("TLS enabled")
    if auth.mode == "pam":
        logger.info("PAM authentication — per-user X sessions")
    elif auth.mode == "local":
        logger.info("Local authentication — shared display")
    else:
        logger.info("No authentication — shared display")

    # Signal handling
    stop = asyncio.Future()

    def signal_handler():
        global running
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


def create_tls_context(cert_file: str, key_file: str) -> ssl.SSLContext:
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert_file, key_file)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    return ctx


def main():
    global auth, session_mgr, default_runtime, quality_settings
    global ffmpeg_caps, available_encoders, server_args

    parser = argparse.ArgumentParser(description="Teragucci Remote Desktop Server")
    parser.add_argument("--host", default="0.0.0.0", help="Listen address")
    parser.add_argument("--port", type=int, default=443, help="Listen port")
    parser.add_argument("--fps", type=int, default=30, help="Target FPS")
    parser.add_argument("--quality", type=int, default=60, help="JPEG quality (fallback)")
    parser.add_argument("--monitor", type=int, default=1, help="Monitor index (0=all)")
    parser.add_argument("--codec", choices=["h264", "h265", "av1", "jpeg"], default="h264")
    parser.add_argument("--chroma", choices=["yuv420", "yuv422", "yuv444"], default="yuv444")
    parser.add_argument("--lossless", action="store_true")
    parser.add_argument("--max-bandwidth", type=float, default=50.0, help="Max Mbps")
    parser.add_argument("--tls-cert", help="TLS certificate file")
    parser.add_argument("--tls-key", help="TLS key file")
    parser.add_argument("--sw-only", action="store_true", help="Software encoding only")
    parser.add_argument("--verbose", "-v", action="store_true")

    # Auth
    auth_group = parser.add_argument_group("authentication")
    auth_group.add_argument("--auth-mode", choices=["pam", "local", "none"],
                            default="pam",
                            help="pam=Linux users (PCoIP-like), local=JSON db, none=disabled")
    auth_group.add_argument("--no-auth", action="store_true",
                            help="Shortcut for --auth-mode none")
    auth_group.add_argument("--add-user", metavar="USERNAME",
                            help="Add a local user and exit")

    # Session
    sess_group = parser.add_argument_group("session")
    sess_group.add_argument("--width", type=int, default=1920,
                            help="Virtual display width (PAM mode)")
    sess_group.add_argument("--height", type=int, default=1080,
                            help="Virtual display height (PAM mode)")
    sess_group.add_argument("--dpi", type=int, default=96,
                            help="Virtual display DPI (PAM mode)")

    # Features
    parser.add_argument("--no-audio", action="store_true")
    parser.add_argument("--no-clipboard", action="store_true")

    args = parser.parse_args()
    server_args = args

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if args.no_auth:
        args.auth_mode = "none"

    # Handle --add-user (local mode only)
    if args.add_user:
        import getpass
        a = Authenticator(mode="local")
        password = getpass.getpass(f"Password for '{args.add_user}': ")
        a.add_user(args.add_user, password)
        print(f"User '{args.add_user}' added/updated.")
        return

    # PAM mode requires root
    if args.auth_mode == "pam" and os.geteuid() != 0:
        logger.error("PAM auth mode requires root. Run with sudo or as root.")
        logger.error("  sudo python -m server.main --auth-mode pam")
        logger.error("Or use --auth-mode none for testing without auth.")
        sys.exit(1)

    # Check FFmpeg capabilities
    ffmpeg_caps = check_ffmpeg_available()
    available_encoders = detect_encoders()
    logger.info("FFmpeg: %s", {k: v for k, v in ffmpeg_caps.items() if k != "encoders"})

    hw_backends = ffmpeg_caps.get("hw_backends", [])
    if hw_backends:
        logger.info("GPU encoding: %s", ", ".join(hw_backends))

    # Quality settings
    quality_settings = QualitySettings(
        quality_bias=0.5,
        max_fps=args.fps,
        max_bandwidth_mbps=args.max_bandwidth,
        codec=args.codec,
        chroma=args.chroma,
        force_lossless=args.lossless,
        enable_audio=not args.no_audio,
    )

    # Initialize auth
    auth = Authenticator(mode=args.auth_mode)

    # Initialize session manager (PAM mode) or default runtime (legacy)
    if args.auth_mode == "pam":
        from server.session_manager import SessionManager
        session_mgr = SessionManager(
            width=args.width, height=args.height, dpi=args.dpi)
        logger.info("Session manager ready (per-user Xvfb sessions)")
        # Runtimes are created on-demand when users authenticate
    else:
        # Legacy mode: single runtime on current DISPLAY
        display = os.environ.get("DISPLAY", ":0")
        logger.info("Legacy mode: using DISPLAY=%s", display)
        try:
            default_runtime = SessionRuntime(
                display=display,
                username="shared",
                quality=quality_settings,
                ffmpeg_caps=ffmpeg_caps,
                available_encoders=available_encoders,
                no_audio=args.no_audio,
                no_clipboard=args.no_clipboard,
                sw_only=args.sw_only,
                monitor_index=args.monitor,
                jpeg_quality=args.quality,
            )
        except Exception as e:
            logger.error("Failed to initialize: %s", e)
            logger.error("Make sure DISPLAY is set and accessible.")
            sys.exit(1)

    # TLS
    tls_context = None
    if args.tls_cert and args.tls_key:
        tls_context = create_tls_context(args.tls_cert, args.tls_key)

    # Run
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        if default_runtime:
            default_runtime.set_event_loop(loop)
        loop.run_until_complete(run_server(args.host, args.port, tls_context))
    except KeyboardInterrupt:
        logger.info("Interrupted")
    finally:
        # Clean up all runtimes
        for rt in runtimes.values():
            rt.stop()
        if default_runtime:
            default_runtime.stop()
        # Destroy all X sessions
        if session_mgr:
            session_mgr.destroy_all()
        logger.info("Server shutdown complete")


if __name__ == "__main__":
    main()
