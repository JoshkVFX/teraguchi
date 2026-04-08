#!/usr/bin/env python3
"""
Teragucci Client - Remote Desktop Client for Mac/Windows

Connects to a Teragucci server running on Linux and provides
full remote desktop control including Wacom pen pressure support.

Usage:
    python -m client.main [--host HOST] [--port PORT]
"""

import sys
import logging
import argparse
from functools import partial

from PySide6.QtCore import Qt, QTimer, Signal, QObject
from PySide6.QtGui import QAction, QKeySequence, QIcon
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QStatusBar, QToolBar,
    QDialog, QFormLayout, QSpinBox, QMessageBox, QSizePolicy,
)

sys.path.insert(0, ".")
from client.viewer import RemoteViewer
from client.protocol import ClientProtocol
from common.messages import MsgType

logger = logging.getLogger(__name__)


class ThreadBridge(QObject):
    """
    Bridge for thread-safe signal emission from the protocol's background thread
    into the Qt main thread.
    """
    server_hello = Signal(dict)
    full_frame = Signal(bytes)
    partial_frame = Signal(int, int, int, int, bytes)
    connected = Signal()
    disconnected = Signal(str)
    error = Signal(str)


class ConnectionDialog(QDialog):
    """Dialog for entering server connection details."""

    def __init__(self, parent=None, default_host="", default_port=9876):
        super().__init__(parent)
        self.setWindowTitle("Connect to Server")
        self.setMinimumWidth(350)

        layout = QFormLayout(self)

        self.host_input = QLineEdit(default_host)
        self.host_input.setPlaceholderText("e.g. 192.168.1.100 or hostname")
        layout.addRow("Host:", self.host_input)

        self.port_input = QSpinBox()
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(default_port)
        layout.addRow("Port:", self.port_input)

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
    def host(self) -> str:
        return self.host_input.text().strip()

    @property
    def port(self) -> int:
        return self.port_input.value()


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self, initial_host: str = "", initial_port: int = 9876):
        super().__init__()

        self._host = initial_host
        self._port = initial_port

        self.setWindowTitle("Teragucci - Remote Desktop")
        self.setMinimumSize(800, 600)

        # Protocol and thread bridge
        self._protocol = ClientProtocol()
        self._bridge = ThreadBridge()
        self._setup_protocol_bridge()

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)

        # Remote viewer
        self._viewer = RemoteViewer()
        self._viewer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self._viewer)

        # Connect viewer signals to protocol
        self._connect_viewer_signals()

        # Toolbar
        self._setup_toolbar()

        # Status bar
        self._status_label = QLabel("Disconnected")
        self._fps_label = QLabel("")
        self.statusBar().addWidget(self._status_label)
        self.statusBar().addPermanentWidget(self._fps_label)

        # FPS counter
        self._frame_count = 0
        self._fps_timer = QTimer()
        self._fps_timer.timeout.connect(self._update_fps)
        self._fps_timer.start(1000)

        # Auto-connect if host was provided
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
        refresh_action.triggered.connect(self._request_refresh)
        toolbar.addAction(refresh_action)

        fullscreen_action = QAction("Fullscreen", self)
        fullscreen_action.setShortcut(QKeySequence("F11"))
        fullscreen_action.triggered.connect(self._toggle_fullscreen)
        toolbar.addAction(fullscreen_action)

    def _setup_protocol_bridge(self):
        """Wire protocol callbacks through the thread bridge for thread safety."""
        # Protocol callbacks (called from background thread)
        self._protocol.on_server_hello = self._bridge.server_hello.emit
        self._protocol.on_full_frame = self._bridge.full_frame.emit
        self._protocol.on_partial_frame = lambda x, y, w, h, d: \
            self._bridge.partial_frame.emit(x, y, w, h, d)
        self._protocol.on_connected = self._bridge.connected.emit
        self._protocol.on_disconnected = self._bridge.disconnected.emit
        self._protocol.on_error = self._bridge.error.emit

        # Bridge signals (received on Qt main thread)
        self._bridge.server_hello.connect(self._on_server_hello)
        self._bridge.full_frame.connect(self._on_full_frame)
        self._bridge.partial_frame.connect(self._on_partial_frame)
        self._bridge.connected.connect(self._on_connected)
        self._bridge.disconnected.connect(self._on_disconnected)
        self._bridge.error.connect(self._on_error)

    def _connect_viewer_signals(self):
        """Connect viewer input signals to send over the protocol."""
        self._viewer.mouse_moved.connect(self._send_mouse_move)
        self._viewer.mouse_button_changed.connect(self._send_mouse_button)
        self._viewer.mouse_scrolled.connect(self._send_mouse_scroll)
        self._viewer.key_changed.connect(self._send_key_event)
        self._viewer.pen_event.connect(self._send_pen_event)

    # --- Input sending ---

    def _send_mouse_move(self, x: float, y: float):
        self._protocol.send_input({
            "type": MsgType.MOUSE_MOVE,
            "x": x, "y": y,
        })

    def _send_mouse_button(self, button: int, pressed: bool, x: float, y: float):
        self._protocol.send_input({
            "type": MsgType.MOUSE_BUTTON,
            "button": button, "pressed": pressed,
            "x": x, "y": y,
        })

    def _send_mouse_scroll(self, dx: int, dy: int, x: float, y: float):
        self._protocol.send_input({
            "type": MsgType.MOUSE_SCROLL,
            "dx": dx, "dy": dy,
            "x": x, "y": y,
        })

    def _send_key_event(self, qt_key: int, scan_code: int, pressed: bool, modifiers: int):
        self._protocol.send_input({
            "type": MsgType.KEY_EVENT,
            "key": "",
            "scan_code": qt_key,  # Server will translate Qt key -> Linux scancode
            "pressed": pressed,
            "modifiers": modifiers,
        })

    def _send_pen_event(self, data: dict):
        data["type"] = MsgType.PEN_EVENT
        self._protocol.send_input(data)

    # --- Protocol event handlers (called on Qt main thread) ---

    def _on_server_hello(self, msg: dict):
        w = msg.get("screen_width", 1920)
        h = msg.get("screen_height", 1080)
        self._viewer.set_remote_size(w, h)
        self.setWindowTitle(f"Teragucci - {self._host}:{self._port} ({w}x{h})")
        logger.info("Server: %dx%d, pen=%s", w, h, msg.get("supports_pen"))

    def _on_full_frame(self, jpeg_data: bytes):
        self._viewer.update_full_frame(jpeg_data)
        self._frame_count += 1

    def _on_partial_frame(self, x: int, y: int, w: int, h: int, jpeg_data: bytes):
        self._viewer.update_partial_frame(x, y, w, h, jpeg_data)
        self._frame_count += 1

    def _on_connected(self):
        self._status_label.setText(f"Connected to {self._host}:{self._port}")
        logger.info("Connected")

    def _on_disconnected(self, reason: str):
        self._status_label.setText(f"Disconnected: {reason}")
        logger.info("Disconnected: %s", reason)

    def _on_error(self, error: str):
        self._status_label.setText(f"Error: {error}")
        QMessageBox.warning(self, "Connection Error", error)

    # --- Actions ---

    def _show_connect_dialog(self):
        dialog = ConnectionDialog(self, self._host, self._port)
        if dialog.exec() == QDialog.Accepted:
            self._host = dialog.host
            self._port = dialog.port
            self._do_connect()

    def _do_connect(self):
        if not self._host:
            self._show_connect_dialog()
            return
        self._status_label.setText(f"Connecting to {self._host}:{self._port}...")
        self._protocol.disconnect()
        self._protocol.connect(self._host, self._port)

    def _do_disconnect(self):
        self._protocol.disconnect()
        self._status_label.setText("Disconnected")

    def _request_refresh(self):
        self._protocol.request_full_frame()

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _update_fps(self):
        self._fps_label.setText(f"{self._frame_count} fps")
        self._frame_count = 0

    def closeEvent(self, event):
        self._protocol.disconnect()
        event.accept()


def main():
    parser = argparse.ArgumentParser(description="Teragucci Remote Desktop Client")
    parser.add_argument("--host", default="",
                        help="Server hostname or IP")
    parser.add_argument("--port", type=int, default=9876,
                        help="Server port (default: 9876)")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Enable debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    app = QApplication(sys.argv)
    app.setApplicationName("Teragucci")
    app.setOrganizationName("Teragucci")

    window = MainWindow(initial_host=args.host, initial_port=args.port)
    window.resize(1280, 800)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
