"""SessionRuntime — per-user session lifecycle (STAB-05 / D-11 extraction).

Moved wholesale from ``server/main.py`` as Plan 01-11 Task 2. Owns:

  * capture (ScreenCapture) + injector (InputInjector / XTestInputInjector)
  * encoder lifecycle (via EncoderLifecycle from Plan 01-10 Task 2)
  * HealthMonitor (shared metrics)
  * audio / clipboard / cursor-tracker / file-transfer / USB-passthrough
    sub-systems
  * the three async loops — StreamLoop, HealthLoop, MonitorHotplug (all
    extracted in Plan 01-10 Task 1) — kept as sub-objects that back-reference
    this runtime for shared state
  * the per-user ``clients`` dict keyed by websocket, guarded by
    ``threading.Lock`` because both the encoder thread and the asyncio loop
    touch it
  * the cached event loop, used by the encoder callback to schedule
    ``cs.enqueue`` coroutines onto the main asyncio loop via
    ``asyncio.run_coroutine_threadsafe``

Preservation invariants (zero behavior change from the pre-extraction monolith):

  * ``IS_MACOS`` platform branch in ``__init__`` (try/finally DISPLAY swap)
  * ``threading.Lock`` + cross-thread ``asyncio.run_coroutine_threadsafe``
    are untouched
  * Back-compat ``self.encoder`` handle kept in sync by EncoderLifecycle
  * Public API (``add_client``, ``remove_client``, ``handle_input``,
    ``apply_quality``, ``stop``, ``set_event_loop``, ``client_count``,
    ``_on_encoded_frame``, ``_on_audio_frame``) unchanged — handle_client
    + handle_http in server/main.py still reach them via the same attribute
    paths.

``server/main.py`` re-exports ``SessionRuntime`` from this module so the
existing import path (``from server.main import SessionRuntime``) used by
``tests/integration/test_server_bootstrap.py`` continues to resolve.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import threading
import time
from typing import TYPE_CHECKING, Dict, Optional

from websockets.server import WebSocketServerProtocol

from common.messages import (
    AudioCodec,
    ClipboardMsg,
    FrameType,
    MsgType,
    QualitySettings,
    VideoCodec,
    VideoFrameFlags,
    encode_audio_header,
    encode_video_header,
)
from common.session_fsm import is_state_pair_allowed
from common.keymap import qt_key_to_linux_scancode
from server.platform_backends import (
    ClipboardSync,
    InputInjector,
    IS_MACOS,
    ScreenCapture,
    XTestInputInjector,
)
from server.cursor_tracker import CursorTracker
from server.video_encoder import JpegFallbackEncoder, VideoEncoder
from server.audio_capture import AudioCapture, check_audio_available
from server.health import HealthMonitor
from server.file_transfer import FileReceiver
from server.usb_passthrough import USBForwardingManager
from server.stream_loop import StreamLoop
from server.health_loop import HealthLoop
from server.encoder_lifecycle import EncoderLifecycle
from server.monitor_hotplug import MonitorHotplug

if TYPE_CHECKING:
    from server.client_session import ClientSession


logger = logging.getLogger("teraguchi.server.session_runtime")


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
                 jpeg_quality: int = 60, uid: int = 0, gid: int = 0,
                 home_dir: str = "", pen_tablet=None):
        self.display = display
        self.username = username
        self.quality = quality
        self._uid = uid
        self._gid = gid
        self.clients: Dict[WebSocketServerProtocol, "ClientSession"] = {}
        self._lock = threading.Lock()
        self._event_loop: Optional[asyncio.AbstractEventLoop] = None

        # Set DISPLAY for this session's subsystems
        old_display = os.environ.get("DISPLAY", "")
        os.environ["DISPLAY"] = display

        try:
            self.capture = ScreenCapture(monitor_index=monitor_index,
                                         jpeg_quality=jpeg_quality)
            if IS_MACOS:
                # On macOS there's no Xvfb / uinput — CoreGraphics posts
                # events directly into the logged-in user's event stream.
                self.injector = InputInjector(
                    screen_width=self.capture.width,
                    screen_height=self.capture.height,
                )
            # Use XTest for virtual displays (Xvfb), uinput for physical
            elif display.startswith(":") and int(display[1:]) >= 10:
                try:
                    self.injector = XTestInputInjector(display,
                                                       screen_width=self.capture.width,
                                                       screen_height=self.capture.height,
                                                       pen_tablet=pen_tablet)
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

        # Video encoder — lifecycle is owned by the EncoderLifecycle helper
        # (D-11 Plan 01-10 Task 2). self.encoder stays as a back-compat
        # attribute (ClientSession.enqueue + tests/server/test_pipelines.py
        # reach it via ``runtime.encoder``) and is kept fresh by
        # EncoderLifecycle.spawn()/restart()/stop().
        self.encoder: Optional[VideoEncoder] = None
        self.jpeg_encoder: Optional[JpegFallbackEncoder] = None
        self.use_h264 = False
        self.ffmpeg_caps = ffmpeg_caps
        self.available_encoders = available_encoders
        self.encoder_lifecycle = EncoderLifecycle(self)
        self.encoder_lifecycle.spawn(sw_only=sw_only, jpeg_quality=jpeg_quality)

        # Health monitor
        self.health = HealthMonitor(target_fps=quality.effective_fps())
        self.health.current_codec = quality.codec
        self.health.current_chroma = quality.chroma
        self.health.current_resolution = f"{self.capture.width}x{self.capture.height}"

        # Audio
        self.audio: Optional[AudioCapture] = None
        if not no_audio and check_audio_available(uid=self._uid, gid=self._gid):
            self.audio = AudioCapture(bitrate_kbps=quality.audio_bitrate_kbps,
                                      uid=self._uid, gid=self._gid)

        # Clipboard
        self.clipboard: Optional[ClipboardSync] = None
        if not no_clipboard:
            self.clipboard = ClipboardSync(display=display)

        # Local-cursor tracker — polls XFixes for cursor shape changes
        # so the client can draw the real Flame cursor locally at zero
        # latency. Falls back gracefully if XFixes is unavailable (we
        # just won't send cursor_update messages and the client will
        # keep using its placeholder cursor).
        self.cursor_tracker: Optional[CursorTracker] = None
        if not IS_MACOS:
            # CursorTracker uses XFixes on Linux; on macOS we bake the
            # cursor into the video frame via SCK's showsCursor=True.
            try:
                self.cursor_tracker = CursorTracker(display_name=display,
                                                    poll_hz=30.0)
            except Exception as e:
                logger.warning("[%s] Cursor tracker unavailable: %s",
                               username, e)

        # File transfer
        ft_home = home_dir or os.path.expanduser("~")
        self.file_receiver = FileReceiver(ft_home, uid=uid, gid=gid)

        # USB passthrough — Linux-only (uses usbip / vhci kernel modules).
        # Stubbed out on macOS; a Mac-native IOKit forwarder is future work.
        self.usb_manager = None if IS_MACOS else USBForwardingManager()

        # Streaming state
        self._streaming = False
        self._running = True

        # D-11 / Plan 01-10: stream + health + hotplug loops are now sub-
        # objects. SessionRuntime remains the owner of shared state (capture,
        # encoder, clients, health); the loops only hold the run-flag + task
        # handle and reach shared state via the back-reference.
        self._stream_loop = StreamLoop(self)
        self._health_loop = HealthLoop(self)
        self._hotplug = MonitorHotplug(self)

        logger.info("[%s] Session runtime ready on %s (%dx%d)",
                    username, display, self.capture.width, self.capture.height)

    def set_event_loop(self, loop: asyncio.AbstractEventLoop):
        self._event_loop = loop

    # ── Client management ────────────────────────────────────

    def add_client(self, ws: WebSocketServerProtocol, session: "ClientSession"):
        with self._lock:
            self.clients[ws] = session
            self.health.clients_connected = len(self.clients)
        # Clear stuck modifier keys on new connection
        if hasattr(self.injector, 'reset_modifiers'):
            self.injector.reset_modifiers()
        if not self._streaming:
            self._start_streaming()
        elif self.encoder:
            # Reused session: force an IDR so the new client can start decoding
            # immediately instead of waiting for the next natural GOP boundary
            # (or staying black forever if nvenc doesn't emit one).
            self.capture.invalidate()
            self.encoder.request_keyframe()

        # Push current cursor shape so late-joining clients don't stare
        # at their placeholder until Flame next changes the cursor.
        if self.cursor_tracker is not None and self._event_loop:
            latest = self.cursor_tracker.latest()
            if latest is not None:
                try:
                    asyncio.run_coroutine_threadsafe(
                        session.enqueue(json.dumps(latest)), self._event_loop)
                except Exception:
                    pass

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

        # D-11 / Plan 01-10: stream + health + hotplug loops all live in
        # their own modules. The loops read shared state off this
        # SessionRuntime via back-reference; wiring stays a pure module
        # split with zero behavior change.
        self._stream_loop.start(fps)
        self._health_loop.start()
        self._hotplug.start()

        if self.audio and self.audio.available and self.quality.enable_audio:
            self.audio.start(self._on_audio_frame)

        if self.clipboard and self.clipboard.available:
            self.clipboard.start_monitoring(self._on_clipboard_change)

        if self.cursor_tracker is not None:
            self.cursor_tracker.start(self._on_cursor_shape_change)

        logger.info("[%s] Streaming started (%d fps)", self.username, fps)

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
                    self._enqueue_frame(cs, tcp_data, is_keyframe), self._event_loop)

        self.health.record_frame_sent(len(frame_data))

    async def _enqueue_frame(self, cs: "ClientSession", data: bytes, is_keyframe: bool = False):
        if not await cs.enqueue(data, is_keyframe=is_keyframe):
            self.health.record_frame_dropped()

    def _on_audio_frame(self, audio_data: bytes, timestamp_ms: int):
        ts = timestamp_ms & 0xFFFFFFFF
        header = encode_audio_header(AudioCodec.OPUS, ts)
        data = header + audio_data
        for ws, cs in list(self.clients.items()):
            if cs.authenticated and cs.supports_audio and self._event_loop:
                asyncio.run_coroutine_threadsafe(cs.enqueue(data), self._event_loop)

    def _send_to_client(self, session: "ClientSession", msg_dict: dict):
        """Send a JSON response to a specific client (thread-safe)."""
        if self._event_loop and msg_dict:
            msg_json = json.dumps(msg_dict)
            asyncio.run_coroutine_threadsafe(session.enqueue(msg_json), self._event_loop)

    def _on_clipboard_change(self, text: str):
        msg_json = ClipboardMsg(type=MsgType.CLIPBOARD_RECV, data=text).to_json()
        for ws, cs in list(self.clients.items()):
            if cs.authenticated and self._event_loop:
                asyncio.run_coroutine_threadsafe(cs.enqueue(msg_json), self._event_loop)

    def _on_cursor_shape_change(self, update: dict):
        """Called from the CursorTracker polling thread whenever Flame
        swaps cursor shapes. Broadcast to every authenticated client so
        they can swap their local QCursor with zero latency."""
        if not self._event_loop:
            return
        msg_json = json.dumps(update)
        for ws, cs in list(self.clients.items()):
            if cs.authenticated:
                asyncio.run_coroutine_threadsafe(
                    cs.enqueue(msg_json), self._event_loop)

    # ── Quality / encoder management ─────────────────────────

    def apply_quality(self, session: "ClientSession", msg: dict):
        session.quality = QualitySettings(**{k: v for k, v in msg.items()
                                             if k in QualitySettings.__dataclass_fields__})
        self.quality = session.quality

        if self.quality.codec in ("h264", "h265", "av1") and \
           self.ffmpeg_caps.get(self.quality.codec, False):
            if not self.use_h264:
                self.use_h264 = True
                self.encoder_lifecycle.restart()
            elif self.encoder:
                self.encoder.update_settings(self.quality)
        else:
            self.use_h264 = False

        self.health.current_codec = self.quality.codec
        self.health.current_chroma = self.quality.chroma
        self.health.target_fps = self.quality.effective_fps()

        if self.audio:
            if self.quality.enable_audio:
                if not self.audio._running:
                    self.audio.start(self._on_audio_frame)
                self.audio.update_bitrate(self.quality.audio_bitrate_kbps)
            else:
                if self.audio._running:
                    self.audio.stop()

    def _handle_resize(self, width: int, height: int):
        """Handle a resize request from the client."""
        if width == self.capture.width and height == self.capture.height:
            return

        try:
            env = {"DISPLAY": self.display, "PATH": os.environ.get("PATH", "/usr/bin:/bin")}

            # Find the connected output name (DP-0 for GPU, screen for Xvfb)
            query = subprocess.run(
                ["xrandr", "--query"],
                capture_output=True, text=True, timeout=5, env=env)
            output_name = "screen"  # default for Xvfb
            for line in query.stdout.splitlines():
                if " connected" in line:
                    output_name = line.split()[0]
                    break

            mode_name = f"{width}x{height}"

            # Try setting mode directly first
            result = subprocess.run(
                ["xrandr", "--output", output_name, "--mode", mode_name],
                capture_output=True, text=True, timeout=5, env=env)
            if result.returncode == 0:
                self.capture.reinit(width, height)
                self.encoder_lifecycle.restart()
                logger.info("Resized to %dx%d", width, height)
                return

            # Mode doesn't exist — create it
            modeline = subprocess.run(
                ["cvt", str(width), str(height)],
                capture_output=True, text=True, timeout=5, env=env)
            if modeline.returncode == 0:
                for line in modeline.stdout.strip().split("\n"):
                    if line.startswith("Modeline"):
                        parts = line.split(None, 2)
                        mode_label = parts[1].strip('"')
                        mode_params = parts[2]

                        subprocess.run(
                            ["xrandr", "--newmode", mode_label] + mode_params.split(),
                            capture_output=True, timeout=5, env=env)
                        subprocess.run(
                            ["xrandr", "--addmode", output_name, mode_label],
                            capture_output=True, timeout=5, env=env)
                        result = subprocess.run(
                            ["xrandr", "--output", output_name, "--mode", mode_label],
                            capture_output=True, text=True, timeout=5, env=env)
                        if result.returncode == 0:
                            self.capture.reinit(width, height)
                            self.encoder_lifecycle.restart()
                            logger.info("Resized to %dx%d", width, height)
                            return
                        else:
                            logger.warning("Resize failed: %s", result.stderr)
        except Exception as e:
            logger.warning("Resize error: %s", e)

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

        elif msg_type == MsgType.RESIZE_REQUEST:
            # Resize temporarily disabled — xrandr triggers SIGSEGV in
            # NVIDIA X11 libraries, crashing the entire server process.
            # TODO: investigate safe resize path for GPU displays
            logger.debug("Resize request ignored (disabled to prevent SEGV)")

        elif msg_type == MsgType.SELECT_MONITOR:
            self.capture.switch_monitor(msg.get("monitor_id", 1))
            self.encoder_lifecycle.restart()

        elif msg_type == MsgType.HEALTH_PONG:
            self.health.record_pong(msg.get("sequence", 0),
                                    msg.get("ping_timestamp_ms", 0))

        elif msg_type == MsgType.HEALTH_PING:
            # STAB-06 / Plan 01-08 — client now originates HealthPing and
            # stamps it with client_state from its ClientFSM. Server reads
            # the state, checks the (client_state, server_state) pair
            # against ALLOWED_PAIRS, and flags disagreements. Structured
            # ERROR logging of the disagreement event is wired in Plan 01-17.
            incoming_client_state = msg.get("client_state", "")
            session.last_reported_client_state = incoming_client_state
            try:
                if incoming_client_state and not is_state_pair_allowed(
                    incoming_client_state, session.fsm.current_state.id,
                ):
                    logger.warning(
                        "fsm.state_disagreement client_state=%s server_state=%s",
                        incoming_client_state, session.fsm.current_state.id,
                    )
            except Exception:
                pass

        elif msg_type == MsgType.CLIPBOARD_SEND:
            if self.clipboard:
                self.clipboard.set_clipboard(msg.get("data", ""))

        elif msg_type in (MsgType.FILE_OFFER, MsgType.FILE_CHUNK,
                          MsgType.FILE_DONE, MsgType.FILE_CANCEL):
            response = self.file_receiver.handle_message(msg)
            if response:
                self._send_to_client(session, response)

        elif msg_type in (MsgType.USB_DEVICE_LIST, MsgType.USB_ATTACH,
                          MsgType.USB_DETACH):
            if self.usb_manager is not None:
                response = self.usb_manager.handle_message(msg, session.client_host)
                if response:
                    self._send_to_client(session, response)

        elif msg_type == MsgType.CLIENT_HELLO:
            session.supports_h264 = msg.get("supports_h264", True)
            session.supports_h265 = msg.get("supports_h265", False)
            session.supports_yuv444 = msg.get("supports_yuv444", True)
            session.supports_audio = msg.get("supports_audio", True)
            session.client_screen_width = msg.get("screen_width", 0)
            session.client_screen_height = msg.get("screen_height", 0)
            logger.info("Client screen: %dx%d", session.client_screen_width, session.client_screen_height)
            # STAB-06 / Plan 01-08 — capability_exchange → streaming.
            try:
                session.fsm.send("client_hello")
            except Exception:
                pass

        elapsed_ms = (time.time() - t0) * 1000
        self.health.record_input_latency(elapsed_ms)

    # ── Shutdown ─────────────────────────────────────────────

    def stop(self):
        self._running = False
        # D-11 / Plan 01-10: delegate loop + encoder teardown to the
        # sub-objects. Each sub-loop owns its own task cancellation;
        # encoder_lifecycle.stop() keeps the back-compat self.encoder
        # handle in sync (sets it to None alongside its internal handle).
        self._stream_loop.stop()
        self._health_loop.stop()
        self._hotplug.stop()
        self.encoder_lifecycle.stop()
        if self.audio:
            self.audio.stop()
        if self.clipboard:
            self.clipboard.stop()
        if self.cursor_tracker:
            self.cursor_tracker.stop()
        if self.usb_manager:
            self.usb_manager.cleanup()
        if self.injector:
            self.injector.close()
        if self.capture:
            self.capture.close()
        logger.info("[%s] Session runtime stopped", self.username)
