"""
Session abstraction — one per remote connection.

Encapsulates protocol, viewer, decoder, audio, health data, and all
signal wiring for a single remote desktop session. Multiple sessions
can exist simultaneously (one per tab).
"""

import json
import logging
import time
from dataclasses import asdict

from PySide6.QtCore import Qt, QObject, Signal, QTimer
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from client.viewer import RemoteViewer
from client.protocol import ClientProtocol
from client.audio_player import AudioPlayer
from client.video_decoder import DecoderManager
from client.health_display import HealthOverlay, HealthData
from common.messages import (
    MsgType, FrameType, QualitySettings, VideoCodec,
    HealthPong, parse_message,
)

logger = logging.getLogger(__name__)


class _Bridge(QObject):
    """Thread-safe Qt signal bridge for protocol callbacks."""
    server_hello = Signal(dict)
    jpeg_frame = Signal(int, int, int, int, int, bytes)
    video_frame = Signal(int, int, int, int, int, int, bytes)
    audio_frame = Signal(int, int, bytes)
    connected = Signal()
    disconnected = Signal(str)
    error = Signal(str)
    auth_required = Signal(str)
    auth_result = Signal(bool, str)
    health_stats = Signal(dict)
    monitor_list = Signal(list)
    clipboard_recv = Signal(str)


class Session(QObject):
    """
    A single remote desktop connection session.

    Owns:
      - ClientProtocol (WebSocket + hybrid transport)
      - RemoteViewer widget (display + input capture)
      - DecoderManager (H.264/H.265/AV1 via PyAV)
      - AudioPlayer (QAudioSink raw PCM)
      - HealthData + HealthOverlay
      - ThreadBridge for signal marshalling
    """

    # Emitted for the tab bar / main window
    status_changed = Signal(str)        # "connecting", "connected", "disconnected"
    title_changed = Signal(str)         # e.g. "randy@10.10.0.150 (1920x1080)"
    auth_failed = Signal(str)           # error message
    monitor_list_received = Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._host = ""
        self._port = 443
        self._username = ""
        self._password = ""
        self._bookmark_id = ""

        # Core subsystems
        self.protocol = ClientProtocol()
        self.viewer = RemoteViewer()
        self.decoder = DecoderManager()
        self.health = HealthData()
        self.audio = AudioPlayer()

        # Bridge for thread safety
        self._bridge = _Bridge()

        # Health overlay on viewer
        self.overlay = HealthOverlay(self.viewer)
        self.overlay.data = self.health

        # Wire everything
        self._wire_protocol()
        self._wire_viewer()

        # Screen size
        screen = QApplication.primaryScreen()
        if screen:
            g = screen.availableGeometry()
            w = g.width() - (g.width() % 2)
            h = g.height() - (g.height() % 2)
            self.protocol._screen_size = (w, h)

    @property
    def display_name(self) -> str:
        if self._host:
            name = f"{self._username}@{self._host}" if self._username else self._host
            return f"{name}:{self._port}"
        return "New Connection"

    @property
    def is_connected(self) -> bool:
        return self.protocol.connected

    # ── Connection ───────────────────────────────

    def connect(self, host: str, port: int, username: str = "",
                password: str = "", use_tls: bool = True,
                auto_reconnect: bool = True, bookmark_id: str = ""):
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._bookmark_id = bookmark_id

        self.status_changed.emit("connecting")
        self.title_changed.emit(self.display_name)

        self.protocol.disconnect()
        self.protocol.connect(
            host, port, username=username, password=password,
            use_tls=use_tls, auto_reconnect=auto_reconnect)

    def disconnect(self):
        self.protocol.disconnect()
        self.status_changed.emit("disconnected")

    def cleanup(self):
        """Full teardown."""
        self.protocol.disconnect()
        self.decoder.close_all()
        if self.audio and self.audio._started:
            self.audio.stop()

    # ── Quality / Controls ───────────────────────

    def apply_quality(self, settings: QualitySettings):
        self.protocol.send_quality_settings(settings)
        # Toggle local audio
        if self.audio and self.audio.available:
            if getattr(settings, "enable_audio", True):
                if not self.audio._started:
                    self.audio.start()
            else:
                if self.audio._started:
                    self.audio.stop()

    def select_monitor(self, mon_id: int):
        self.protocol.select_monitor(mon_id)

    def request_full_frame(self):
        self.protocol.request_full_frame()

    def send_resize(self, w: int, h: int):
        w = w - (w % 2)
        h = h - (h % 2)
        if w >= 640 and h >= 480:
            self.protocol.send_input({
                "type": "resize_request", "width": w, "height": h})

    # ── Protocol Wiring ──────────────────────────

    def _wire_protocol(self):
        p = self.protocol
        b = self._bridge

        p.on_server_hello = b.server_hello.emit
        p.on_jpeg_frame = lambda ft, x, y, w, h, d: b.jpeg_frame.emit(ft, x, y, w, h, d)
        p.on_video_frame = lambda ft, c, ch, f, t, m, d: b.video_frame.emit(ft, c, ch, f, t, m, d)
        p.on_audio_frame = lambda c, t, d: b.audio_frame.emit(c, t, d)
        p.on_connected = b.connected.emit
        p.on_disconnected = b.disconnected.emit
        p.on_error = b.error.emit
        p.on_auth_required = b.auth_required.emit
        p.on_auth_result = b.auth_result.emit
        p.on_health_stats = b.health_stats.emit
        p.on_monitor_list = b.monitor_list.emit
        p.on_clipboard = b.clipboard_recv.emit

        b.server_hello.connect(self._on_server_hello)
        b.jpeg_frame.connect(self._on_jpeg_frame)
        b.video_frame.connect(self._on_video_frame)
        b.audio_frame.connect(self._on_audio_frame)
        b.connected.connect(self._on_connected)
        b.disconnected.connect(self._on_disconnected)
        b.error.connect(self._on_error)
        b.auth_result.connect(self._on_auth_result)
        b.health_stats.connect(self._on_health_stats)
        b.monitor_list.connect(self._on_monitor_list)
        b.clipboard_recv.connect(self._on_clipboard_recv)

    def _wire_viewer(self):
        v = self.viewer
        v.mouse_moved.connect(self._send_mouse_move)
        v.mouse_button_changed.connect(self._send_mouse_button)
        v.mouse_scrolled.connect(self._send_mouse_scroll)
        v.key_changed.connect(self._send_key_event)
        v.pen_event.connect(self._send_pen_event)

    # ── Input Sending ────────────────────────────

    def _send_mouse_move(self, x, y):
        self.protocol.send_input({"type": MsgType.MOUSE_MOVE, "x": x, "y": y})

    def _send_mouse_button(self, btn, pressed, x, y):
        self.protocol.send_input({"type": MsgType.MOUSE_BUTTON,
                                   "button": btn, "pressed": pressed, "x": x, "y": y})

    def _send_mouse_scroll(self, dx, dy, x, y):
        self.protocol.send_input({"type": MsgType.MOUSE_SCROLL,
                                   "dx": dx, "dy": dy, "x": x, "y": y})

    def _send_key_event(self, qt_key, scan_code, pressed, mods):
        self.protocol.send_input({"type": MsgType.KEY_EVENT,
                                   "key": "", "scan_code": qt_key,
                                   "pressed": pressed, "modifiers": mods})

    def _send_pen_event(self, data):
        data["type"] = MsgType.PEN_EVENT
        self.protocol.send_input(data)

    # ── Protocol Event Handlers ──────────────────

    def _on_server_hello(self, msg):
        w = msg.get("screen_width", 1920)
        h = msg.get("screen_height", 1080)
        self.viewer.set_remote_size(w, h)
        backend = msg.get("encoder_backend", "")
        if backend:
            self.health.encoder_backend = backend
        suffix = f" [{backend}]" if backend else ""
        self.title_changed.emit(f"{self.display_name} ({w}x{h}){suffix}")

    def _on_jpeg_frame(self, ft, x, y, w, h, data):
        self.health.record_frame_received()
        if ft == FrameType.VIDEO_FULL:
            self.viewer.update_full_frame(data)
        else:
            self.viewer.update_partial_frame(x, y, w, h, data)

    def _on_video_frame(self, ft, codec, chroma, flags, ts, mon, data):
        self.health.record_frame_received()
        codec_map = {VideoCodec.H264: "h264", VideoCodec.H265: "h265", VideoCodec.AV1: "av1"}
        codec_name = codec_map.get(codec, "h264")
        rgb_data = self.decoder.decode(codec_name, data)
        # Update health with decoder backend (once)
        if not self.health.decoder_backend:
            self.health.decoder_backend = self.decoder.active_backend
        if rgb_data is not None:
            decoder = self.decoder.get_decoder(codec_name)
            size = decoder.get_frame_size() if decoder else None
            if size:
                w, h = size
                img = QImage(rgb_data, w, h, w * 3, QImage.Format_RGB888)
                if not img.isNull():
                    self.viewer._screen_image = img
                    self.viewer._pixmap = None
                    self.viewer.update()

    def _on_audio_frame(self, codec, ts, data):
        if self.audio and self.audio.available:
            self.audio.feed(codec, ts, data)

    def _on_connected(self):
        self.status_changed.emit("connected")

    def _on_disconnected(self, reason):
        self.status_changed.emit("disconnected")

    def _on_error(self, error):
        self.status_changed.emit("error")

    def _on_auth_result(self, success, message):
        if not success:
            self.auth_failed.emit(message)

    def _on_health_stats(self, stats):
        self.health.update_from_server(stats)

    def _on_monitor_list(self, monitors):
        self.monitor_list_received.emit(monitors)

    def _on_clipboard_recv(self, text):
        QApplication.clipboard().setText(text)
