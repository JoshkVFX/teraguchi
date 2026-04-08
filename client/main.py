#!/usr/bin/env python3
"""
Teragucci Client - Remote Desktop Client v2

Full-featured remote desktop client with:
- H.264/H.265 decoding with 4:4:4 chroma support
- Wacom pen/stylus pressure sensitivity
- Connection bookmarks with saved credentials
- Health monitoring overlay
- Quality slider (sharpness ↔ temporal stability)
- Audio playback
- Clipboard sync
- Multi-monitor selection
- TLS and authentication
- Auto-reconnect

Usage:
    python -m client.main [--host HOST] [--port PORT]
"""

import sys
import logging
import argparse
import json
import time
from dataclasses import asdict

from PySide6.QtCore import Qt, QTimer, Signal, QObject, QSize
from PySide6.QtGui import QAction, QKeySequence, QClipboard, QImage
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QStatusBar, QToolBar, QSplitter,
    QDialog, QFormLayout, QSpinBox, QMessageBox, QSizePolicy,
    QDockWidget, QListWidget, QListWidgetItem, QCheckBox,
    QComboBox, QInputDialog, QMenu, QFileDialog, QTabWidget,
)

sys.path.insert(0, ".")
from client.viewer import RemoteViewer
from client.protocol import ClientProtocol
from client.audio_player import AudioPlayer
from client.bookmarks import BookmarkManager
from client.health_display import HealthOverlay, HealthStatusWidget, HealthData
from client.quality_control import QualityControlPanel
from client.video_decoder import DecoderManager, check_decode_available, HAS_PYAV
from common.messages import MsgType, FrameType, QualitySettings, VideoCodec

logger = logging.getLogger(__name__)


class ThreadBridge(QObject):
    """Thread-safe Qt signal bridge for protocol callbacks."""
    server_hello = Signal(dict)
    jpeg_frame = Signal(int, int, int, int, int, bytes)   # ft, x, y, w, h, data
    video_frame = Signal(int, int, int, int, int, int, bytes)  # ft, codec, chroma, flags, ts, mon, data
    audio_frame = Signal(int, int, bytes)                  # codec, ts, data
    connected = Signal()
    disconnected = Signal(str)
    error = Signal(str)
    auth_required = Signal(str)        # challenge
    auth_result = Signal(bool, str)    # success, message
    health_stats = Signal(dict)
    monitor_list = Signal(list)
    clipboard_recv = Signal(str)


class ConnectionDialog(QDialog):
    """Connection dialog with full settings."""

    def __init__(self, parent=None, default_host="", default_port=443,
                 default_username="", default_password=""):
        super().__init__(parent)
        self.setWindowTitle("Connect to Server")
        self.setMinimumWidth(400)

        layout = QFormLayout(self)

        self.host_input = QLineEdit(default_host)
        self.host_input.setPlaceholderText("e.g. 192.168.1.100 or hostname")
        layout.addRow("Host:", self.host_input)

        self.port_input = QSpinBox()
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(default_port)
        layout.addRow("Port:", self.port_input)

        self.username_input = QLineEdit(default_username)
        self.username_input.setPlaceholderText("(leave empty if no auth)")
        layout.addRow("Username:", self.username_input)

        self.password_input = QLineEdit(default_password)
        self.password_input.setEchoMode(QLineEdit.Password)
        layout.addRow("Password:", self.password_input)

        self.tls_check = QCheckBox("Use TLS (wss://)")
        layout.addRow(self.tls_check)

        self.auto_reconnect_check = QCheckBox("Auto-reconnect on disconnect")
        self.auto_reconnect_check.setChecked(True)
        layout.addRow(self.auto_reconnect_check)

        self.save_bookmark_check = QCheckBox("Save as bookmark")
        layout.addRow(self.save_bookmark_check)

        self.bookmark_name_input = QLineEdit()
        self.bookmark_name_input.setPlaceholderText("Bookmark name")
        self.bookmark_name_input.setEnabled(False)
        self.save_bookmark_check.toggled.connect(self.bookmark_name_input.setEnabled)
        layout.addRow("Name:", self.bookmark_name_input)

        btn_layout = QHBoxLayout()
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.setDefault(True)
        self.cancel_btn = QPushButton("Cancel")
        btn_layout.addWidget(self.connect_btn)
        btn_layout.addWidget(self.cancel_btn)
        layout.addRow(btn_layout)

        self.connect_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)

    @property
    def host(self): return self.host_input.text().strip()
    @property
    def port(self): return self.port_input.value()
    @property
    def username(self): return self.username_input.text().strip()
    @property
    def password(self): return self.password_input.text()
    @property
    def use_tls(self): return self.tls_check.isChecked()
    @property
    def auto_reconnect(self): return self.auto_reconnect_check.isChecked()
    @property
    def save_bookmark(self): return self.save_bookmark_check.isChecked()
    @property
    def bookmark_name(self): return self.bookmark_name_input.text().strip()


class BookmarkPanel(QWidget):
    """Side panel showing saved connection bookmarks."""

    connect_requested = Signal(str)  # bookmark_id
    delete_requested = Signal(str)

    def __init__(self, bookmark_mgr: BookmarkManager, parent=None):
        super().__init__(parent)
        self._mgr = bookmark_mgr
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # Search
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search bookmarks...")
        self._search.textChanged.connect(self._refresh)
        layout.addWidget(self._search)

        # List
        self._list = QListWidget()
        self._list.setContextMenuPolicy(Qt.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._show_context_menu)
        self._list.doubleClicked.connect(self._on_double_click)
        layout.addWidget(self._list)

        # Buttons
        btn_row = QHBoxLayout()
        add_btn = QPushButton("Add")
        add_btn.clicked.connect(self._add_bookmark)
        import_btn = QPushButton("Import")
        import_btn.clicked.connect(self._import_bookmarks)
        export_btn = QPushButton("Export")
        export_btn.clicked.connect(self._export_bookmarks)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(import_btn)
        btn_row.addWidget(export_btn)
        layout.addLayout(btn_row)

        self._refresh()

    def _refresh(self, query: str = ""):
        self._list.clear()
        query = self._search.text().strip()
        items = self._mgr.search(query) if query else self._mgr.list_all()
        for bid, profile in items:
            text = f"{profile.name}\n{profile.host}:{profile.port}"
            if profile.last_connected:
                text += f"\nLast: {profile.last_connected}"
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, bid)
            if profile.color_label:
                from PySide6.QtGui import QColor
                item.setBackground(QColor(profile.color_label))
            self._list.addItem(item)

    def _on_double_click(self, index):
        item = self._list.currentItem()
        if item:
            bid = item.data(Qt.UserRole)
            self.connect_requested.emit(bid)

    def _show_context_menu(self, pos):
        item = self._list.itemAt(pos)
        if not item:
            return
        bid = item.data(Qt.UserRole)
        menu = QMenu(self)
        menu.addAction("Connect", lambda: self.connect_requested.emit(bid))
        menu.addAction("Edit", lambda: self._edit_bookmark(bid))
        menu.addAction("Delete", lambda: self._delete_bookmark(bid))
        menu.exec(self._list.mapToGlobal(pos))

    def _add_bookmark(self):
        dialog = ConnectionDialog(self)
        dialog.setWindowTitle("Add Bookmark")
        dialog.save_bookmark_check.setChecked(True)
        dialog.save_bookmark_check.setEnabled(False)
        if dialog.exec() == QDialog.Accepted:
            name = dialog.bookmark_name or f"{dialog.host}:{dialog.port}"
            self._mgr.add(
                name=name, host=dialog.host, port=dialog.port,
                username=dialog.username, password=dialog.password,
                use_tls=dialog.use_tls,
            )
            self._refresh()

    def _edit_bookmark(self, bid):
        profile = self._mgr.get(bid)
        if not profile:
            return
        dialog = ConnectionDialog(self)
        dialog.setWindowTitle(f"Edit Bookmark: {profile.name}")
        dialog.save_bookmark_check.setChecked(True)
        dialog.save_bookmark_check.setEnabled(False)
        dialog.bookmark_name_input.setText(profile.name)
        dialog.host_input.setText(profile.host)
        dialog.port_input.setValue(profile.port)
        dialog.username_input.setText(profile.username)
        dialog.password_input.setText(self._mgr.get_password(bid))
        if hasattr(dialog, 'tls_check'):
            dialog.tls_check.setChecked(profile.use_tls)
        if dialog.exec() == QDialog.Accepted:
            self._mgr.update(bid,
                             name=dialog.bookmark_name or profile.name,
                             host=dialog.host,
                             port=dialog.port,
                             username=dialog.username,
                             password=dialog.password,
                             use_tls=dialog.use_tls)
            self._refresh()

    def _delete_bookmark(self, bid):
        profile = self._mgr.get(bid)
        if not profile:
            return
        reply = QMessageBox.question(self, "Delete Bookmark",
                                     f"Delete '{profile.name}'?")
        if reply == QMessageBox.Yes:
            self._mgr.remove(bid)
            self._refresh()

    def _import_bookmarks(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import Bookmarks", "", "JSON (*.json)")
        if path:
            self._mgr.import_bookmarks(path)
            self._refresh()

    def _export_bookmarks(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export Bookmarks", "bookmarks.json", "JSON (*.json)")
        if path:
            self._mgr.export_bookmarks(path, include_passwords=False)
            QMessageBox.information(self, "Export", f"Exported to {path}\n(passwords excluded)")


class MainWindow(QMainWindow):
    """Main application window with all features."""

    def __init__(self, initial_host="", initial_port=443, initial_user="", initial_pass=""):
        super().__init__()

        self._host = initial_host
        self._port = initial_port
        self._username = initial_user
        self._password = initial_pass
        self._current_bookmark_id = ""

        self.setWindowTitle("Teragucci")
        self.setMinimumSize(800, 600)

        # Subsystems
        self._protocol = ClientProtocol()
        self._bridge = ThreadBridge()
        self._bookmarks = BookmarkManager()
        self._health_data = HealthData()
        self._decoder_mgr = DecoderManager()

        self._setup_protocol_bridge()

        # Audio player
        self._audio_player = AudioPlayer()
        if self._audio_player.available:
            self._audio_player.start()

        # --- Central Layout ---
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # Viewer (remote screen)
        self._viewer = RemoteViewer()
        self._viewer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Health overlay (drawn on top of viewer)
        self._health_overlay = HealthOverlay(self._viewer)
        self._health_overlay.data = self._health_data

        main_layout.addWidget(self._viewer)

        # --- Dock: Bookmarks ---
        self._bookmark_dock = QDockWidget("Bookmarks", self)
        self._bookmark_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self._bookmark_panel = BookmarkPanel(self._bookmarks)
        self._bookmark_panel.connect_requested.connect(self._connect_bookmark)
        self._bookmark_dock.setWidget(self._bookmark_panel)
        self.addDockWidget(Qt.LeftDockWidgetArea, self._bookmark_dock)

        # --- Dock: Quality Settings ---
        self._quality_dock = QDockWidget("Quality", self)
        self._quality_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self._quality_panel = QualityControlPanel()
        self._quality_panel.settings_changed.connect(self._on_quality_changed)
        self._quality_dock.setWidget(self._quality_panel)
        self.addDockWidget(Qt.RightDockWidgetArea, self._quality_dock)

        # --- Toolbar ---
        self._setup_toolbar()

        # --- Status Bar ---
        self._health_status = HealthStatusWidget()
        self._health_status.data = self._health_data
        self._status_label = QLabel("Disconnected")
        self.statusBar().addWidget(self._status_label)
        self.statusBar().addPermanentWidget(self._health_status)

        # --- Timers ---
        self._health_timer = QTimer()
        self._health_timer.timeout.connect(self._update_health_display)
        self._health_timer.start(500)

        # --- Connect signals ---
        self._connect_viewer_signals()

        # Auto-connect
        if self._host:
            QTimer.singleShot(100, self._do_connect)

    def _setup_toolbar(self):
        toolbar = QToolBar("Main")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        connect_action = QAction("Connect", self)
        connect_action.setShortcut(QKeySequence("Ctrl+N"))
        connect_action.triggered.connect(self._show_connect_dialog)
        toolbar.addAction(connect_action)

        disconnect_action = QAction("Disconnect", self)
        disconnect_action.setShortcut(QKeySequence("Ctrl+D"))
        disconnect_action.triggered.connect(self._do_disconnect)
        toolbar.addAction(disconnect_action)

        toolbar.addSeparator()

        refresh_action = QAction("Refresh", self)
        refresh_action.setShortcut(QKeySequence("F5"))
        refresh_action.triggered.connect(lambda: self._protocol.request_full_frame())
        toolbar.addAction(refresh_action)

        fullscreen_action = QAction("Fullscreen", self)
        fullscreen_action.setShortcut(QKeySequence("F11"))
        fullscreen_action.triggered.connect(self._toggle_fullscreen)
        toolbar.addAction(fullscreen_action)

        bookmarks_action = QAction("Bookmarks", self)
        bookmarks_action.setShortcut(QKeySequence("Ctrl+B"))
        bookmarks_action.triggered.connect(self._toggle_bookmarks)
        toolbar.addAction(bookmarks_action)

        health_action = QAction("Health Overlay", self)
        health_action.setShortcut(QKeySequence("F9"))
        health_action.triggered.connect(self._health_overlay.toggle)
        toolbar.addAction(health_action)

        toolbar.addSeparator()

        # View menu for toggling panels
        menu_bar = self.menuBar()
        view_menu = menu_bar.addMenu("View")
        view_menu.addAction(self._bookmark_dock.toggleViewAction())
        view_menu.addAction(self._quality_dock.toggleViewAction())
        view_menu.addSeparator()
        view_menu.addAction(fullscreen_action)
        view_menu.addAction(health_action)

        # Monitor selector
        toolbar.addWidget(QLabel(" Monitor: "))
        self._monitor_combo = QComboBox()
        self._monitor_combo.setMinimumWidth(150)
        self._monitor_combo.currentIndexChanged.connect(self._on_monitor_selected)
        toolbar.addWidget(self._monitor_combo)

    def _setup_protocol_bridge(self):
        """Wire protocol callbacks through Qt signals for thread safety."""
        self._protocol.on_server_hello = self._bridge.server_hello.emit
        self._protocol.on_jpeg_frame = lambda ft, x, y, w, h, d: \
            self._bridge.jpeg_frame.emit(ft, x, y, w, h, d)
        self._protocol.on_video_frame = lambda ft, c, ch, f, t, m, d: \
            self._bridge.video_frame.emit(ft, c, ch, f, t, m, d)
        self._protocol.on_audio_frame = lambda c, t, d: \
            self._bridge.audio_frame.emit(c, t, d)
        self._protocol.on_connected = self._bridge.connected.emit
        self._protocol.on_disconnected = self._bridge.disconnected.emit
        self._protocol.on_error = self._bridge.error.emit
        self._protocol.on_auth_required = self._bridge.auth_required.emit
        self._protocol.on_auth_result = self._bridge.auth_result.emit
        self._protocol.on_health_stats = self._bridge.health_stats.emit
        self._protocol.on_monitor_list = self._bridge.monitor_list.emit
        self._protocol.on_clipboard = self._bridge.clipboard_recv.emit

        self._bridge.server_hello.connect(self._on_server_hello)
        self._bridge.jpeg_frame.connect(self._on_jpeg_frame)
        self._bridge.video_frame.connect(self._on_video_frame)
        self._bridge.connected.connect(self._on_connected)
        self._bridge.disconnected.connect(self._on_disconnected)
        self._bridge.error.connect(self._on_error)
        self._bridge.auth_result.connect(self._on_auth_result)
        self._bridge.health_stats.connect(self._on_health_stats)
        self._bridge.monitor_list.connect(self._on_monitor_list)
        self._bridge.clipboard_recv.connect(self._on_clipboard_recv)
        self._bridge.audio_frame.connect(self._on_audio_frame)

    def _connect_viewer_signals(self):
        self._viewer.mouse_moved.connect(self._send_mouse_move)
        self._viewer.mouse_button_changed.connect(self._send_mouse_button)
        self._viewer.mouse_scrolled.connect(self._send_mouse_scroll)
        self._viewer.key_changed.connect(self._send_key_event)
        self._viewer.pen_event.connect(self._send_pen_event)

    # --- Input sending ---

    def _send_mouse_move(self, x, y):
        self._protocol.send_input({"type": MsgType.MOUSE_MOVE, "x": x, "y": y})

    def _send_mouse_button(self, btn, pressed, x, y):
        self._protocol.send_input({"type": MsgType.MOUSE_BUTTON,
                                    "button": btn, "pressed": pressed, "x": x, "y": y})

    def _send_mouse_scroll(self, dx, dy, x, y):
        self._protocol.send_input({"type": MsgType.MOUSE_SCROLL,
                                    "dx": dx, "dy": dy, "x": x, "y": y})

    def _send_key_event(self, qt_key, scan_code, pressed, mods):
        self._protocol.send_input({"type": MsgType.KEY_EVENT,
                                    "key": "", "scan_code": qt_key,
                                    "pressed": pressed, "modifiers": mods})

    def _send_pen_event(self, data):
        data["type"] = MsgType.PEN_EVENT
        self._protocol.send_input(data)

    # --- Protocol events ---

    def _on_server_hello(self, msg):
        w = msg.get("screen_width", 1920)
        h = msg.get("screen_height", 1080)
        self._viewer.set_remote_size(w, h)
        encoder_backend = msg.get("encoder_backend", "")
        backend_str = f" [{encoder_backend}]" if encoder_backend else ""
        self.setWindowTitle(f"Teragucci - {self._host}:{self._port} ({w}x{h}){backend_str}")
        logger.info("Server: %dx%d h264=%s h265=%s av1=%s 444=%s encoder=%s",
                     w, h, msg.get("supports_h264"), msg.get("supports_h265"),
                     msg.get("supports_av1"), msg.get("supports_yuv444"),
                     msg.get("encoder_backend", "unknown"))

    def _on_jpeg_frame(self, ft, x, y, w, h, data):
        self._health_data.record_frame_received()
        if ft == FrameType.VIDEO_FULL:
            self._viewer.update_full_frame(data)
        else:
            self._viewer.update_partial_frame(x, y, w, h, data)

    def _on_video_frame(self, ft, codec, chroma, flags, ts, mon, data):
        """Decode H.264/H.265/AV1 frames via PyAV and display."""
        self._health_data.record_frame_received()

        # Map codec ID to name
        codec_map = {
            VideoCodec.H264: "h264",
            VideoCodec.H265: "h265",
            VideoCodec.AV1: "av1",
        }
        codec_name = codec_map.get(codec, "h264")

        # Decode via PyAV
        rgb_data = self._decoder_mgr.decode(codec_name, data)
        if rgb_data is not None:
            # Get frame dimensions from decoder
            decoder = self._decoder_mgr.get_decoder(codec_name)
            size = decoder.get_frame_size() if decoder else None

            if size:
                w, h = size
                img = QImage(rgb_data, w, h, w * 3, QImage.Format_RGB888)
                if not img.isNull():
                    self._viewer._screen_image = img
                    self._viewer._pixmap = None  # Invalidate cache
                    self._viewer.update()
        else:
            logger.debug("Video frame: decode pending (codec=%s, len=%d)", codec_name, len(data))

    def _on_connected(self):
        self._status_label.setText(f"Connected to {self._host}:{self._port}")
        if self._current_bookmark_id:
            self._bookmarks.mark_connected(self._current_bookmark_id)
        # Send initial quality settings
        self._protocol.send_quality_settings(self._quality_panel.settings)

    def _on_disconnected(self, reason):
        self._status_label.setText(f"Disconnected: {reason}")

    def _on_error(self, error):
        self._status_label.setText(f"Error: {error}")

    def _on_auth_result(self, success, message):
        if not success:
            QMessageBox.warning(self, "Authentication Failed", message)

    def _on_health_stats(self, stats):
        self._health_data.update_from_server(stats)

    def _on_monitor_list(self, monitors):
        self._monitor_combo.blockSignals(True)
        self._monitor_combo.clear()
        for mon in monitors:
            label = f"{mon.get('name', 'Monitor')} ({mon['width']}x{mon['height']})"
            self._monitor_combo.addItem(label, mon.get("id", 0))
        self._monitor_combo.blockSignals(False)

    def _on_audio_frame(self, codec: int, timestamp_ms: int, data: bytes):
        if self._audio_player and self._audio_player.available:
            self._audio_player.feed(codec, timestamp_ms, data)

    def _on_clipboard_recv(self, text):
        clipboard = QApplication.clipboard()
        clipboard.setText(text)

    def _on_monitor_selected(self, index):
        if index >= 0:
            mon_id = self._monitor_combo.itemData(index)
            if mon_id is not None:
                self._protocol.select_monitor(mon_id)

    def _on_quality_changed(self, settings):
        self._protocol.send_quality_settings(settings)
        # Toggle local audio playback
        if hasattr(self, '_audio_player') and self._audio_player:
            if settings.get("enable_audio", True):
                if not self._audio_player._started:
                    self._audio_player.start()
            else:
                if self._audio_player._started:
                    self._audio_player.stop()

    # --- Actions ---

    def _show_connect_dialog(self):
        dialog = ConnectionDialog(self, self._host, self._port,
                                  self._username, self._password)
        if dialog.exec() == QDialog.Accepted:
            self._host = dialog.host
            self._port = dialog.port
            self._username = dialog.username
            self._password = dialog.password

            if dialog.save_bookmark:
                name = dialog.bookmark_name or f"{dialog.host}:{dialog.port}"
                bid = self._bookmarks.add(
                    name=name, host=dialog.host, port=dialog.port,
                    username=dialog.username, password=dialog.password,
                    use_tls=dialog.use_tls,
                )
                self._current_bookmark_id = bid
                self._bookmark_panel._refresh()

            self._do_connect(use_tls=dialog.use_tls,
                             auto_reconnect=dialog.auto_reconnect)

    def _connect_bookmark(self, bookmark_id):
        profile = self._bookmarks.get(bookmark_id)
        if not profile:
            return
        self._host = profile.host
        self._port = profile.port
        self._username = profile.username
        self._password = self._bookmarks.get_password(bookmark_id)
        self._current_bookmark_id = bookmark_id

        # Load quality settings from profile
        self._quality_panel.load_from_profile(profile)

        self._do_connect(use_tls=profile.use_tls, auto_reconnect=profile.auto_connect)

    def _do_connect(self, use_tls=False, auto_reconnect=True):
        if not self._host:
            self._show_connect_dialog()
            return
        self._status_label.setText(f"Connecting to {self._host}:{self._port}...")
        self._protocol.disconnect()
        self._protocol.connect(
            self._host, self._port,
            username=self._username, password=self._password,
            use_tls=use_tls, auto_reconnect=auto_reconnect,
        )

    def _do_disconnect(self):
        self._protocol.disconnect()
        self._status_label.setText("Disconnected")

    def _toggle_bookmarks(self):
        self._bookmark_dock.setVisible(not self._bookmark_dock.isVisible())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Send resize request to server when window size changes
        if hasattr(self, '_protocol') and self._protocol and hasattr(self, '_viewer'):
            # Use viewer size (the actual display area), not window size
            from PySide6.QtCore import QTimer
            if not hasattr(self, '_resize_timer'):
                self._resize_timer = QTimer()
                self._resize_timer.setSingleShot(True)
                self._resize_timer.timeout.connect(self._send_resize)
            self._resize_timer.start(500)  # Debounce 500ms

    def _send_resize(self):
        if hasattr(self, '_viewer') and self._viewer:
            w = self._viewer.width()
            h = self._viewer.height()
            # Round to even numbers (required by video encoders)
            w = w - (w % 2)
            h = h - (h % 2)
            if w >= 640 and h >= 480:
                self._protocol.send_input({
                    "type": "resize_request",
                    "width": w,
                    "height": h,
                })

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _update_health_display(self):
        self._health_status.update_display()
        self._health_overlay.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Keep health overlay same size as viewer
        self._health_overlay.setGeometry(self._viewer.geometry())

    def closeEvent(self, event):
        self._protocol.disconnect()
        self._decoder_mgr.close_all()
        event.accept()


def main():
    parser = argparse.ArgumentParser(description="Teragucci Remote Desktop Client")
    parser.add_argument("--host", default="", help="Server hostname or IP")
    parser.add_argument("--port", type=int, default=443, help="Server port (default: 443)")
    parser.add_argument("--username", "-u", default="", help="Username")
    parser.add_argument("--password", "-p", default="", help="Password")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    app = QApplication(sys.argv)
    app.setApplicationName("Teragucci")
    app.setOrganizationName("Teragucci")

    # Set a reasonable default style
    app.setStyle("Fusion")

    window = MainWindow(
        initial_host=args.host,
        initial_port=args.port,
        initial_user=args.username,
        initial_pass=args.password,
    )
    window.resize(1440, 900)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
