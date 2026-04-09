#!/usr/bin/env python3
"""
Teragucci Client — Modern Remote Desktop Client

Features:
- Multiple concurrent connections via tabs
- True fullscreen with auto-hiding toolbar
- Dark theme UI
- H.264/H.265/AV1 + Wacom pen + audio + clipboard
"""

import sys
import logging
import argparse
from dataclasses import asdict

from PySide6.QtCore import Qt, QTimer, Signal, QEvent, QPoint
from PySide6.QtGui import QAction, QKeySequence, QColor, QIcon
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QStatusBar, QToolBar,
    QDialog, QFormLayout, QSpinBox, QMessageBox, QSizePolicy,
    QDockWidget, QListWidget, QListWidgetItem, QCheckBox,
    QComboBox, QMenu, QFileDialog, QTabWidget, QTabBar,
)

sys.path.insert(0, ".")
from client import theme
from client.session import Session
from client.bookmarks import BookmarkManager
from client.health_display import HealthStatusWidget, HealthData
from client.quality_control import QualityControlPanel
from client.fullscreen_toolbar import FullscreenToolbar, REVEAL_ZONE
from common.messages import QualitySettings

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════
# Connection Dialog
# ════════════════════════════════════════════════════

class ConnectionDialog(QDialog):
    def __init__(self, parent=None, default_host="", default_port=443,
                 default_username="", default_password=""):
        super().__init__(parent)
        self.setWindowTitle("Connect to Server")
        self.setMinimumWidth(420)

        layout = QFormLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(24, 24, 24, 24)

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

        self.tls_check = QCheckBox("Encrypt connection")
        self.tls_check.setChecked(True)
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

        # Buttons
        btn_layout = QHBoxLayout()
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.setObjectName("connectBtn")
        self.connect_btn.setDefault(True)
        self.cancel_btn = QPushButton("Cancel")
        btn_layout.addStretch()
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.connect_btn)
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


# ════════════════════════════════════════════════════
# Bookmark Panel
# ════════════════════════════════════════════════════

class BookmarkPanel(QWidget):
    connect_requested = Signal(str)

    def __init__(self, bookmark_mgr: BookmarkManager, parent=None):
        super().__init__(parent)
        self._mgr = bookmark_mgr
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        self._search = QLineEdit()
        self._search.setPlaceholderText("Search bookmarks...")
        self._search.textChanged.connect(self._refresh)
        layout.addWidget(self._search)

        self._list = QListWidget()
        self._list.setContextMenuPolicy(Qt.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._show_context_menu)
        self._list.doubleClicked.connect(self._on_double_click)
        layout.addWidget(self._list)

        btn_row = QHBoxLayout()
        for label, slot in [("Add", self._add_bookmark),
                            ("Import", self._import_bookmarks),
                            ("Export", self._export_bookmarks)]:
            btn = QPushButton(label)
            btn.clicked.connect(slot)
            btn_row.addWidget(btn)
        layout.addLayout(btn_row)

        self._refresh()

    def _refresh(self, _query: str = ""):
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
                item.setBackground(QColor(profile.color_label))
            self._list.addItem(item)

    def _on_double_click(self, _index):
        item = self._list.currentItem()
        if item:
            self.connect_requested.emit(item.data(Qt.UserRole))

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
            self._mgr.add(name=name, host=dialog.host, port=dialog.port,
                          username=dialog.username, password=dialog.password,
                          use_tls=dialog.use_tls)
            self._refresh()

    def _edit_bookmark(self, bid):
        profile = self._mgr.get(bid)
        if not profile:
            return
        dialog = ConnectionDialog(self)
        dialog.setWindowTitle(f"Edit: {profile.name}")
        dialog.save_bookmark_check.setChecked(True)
        dialog.save_bookmark_check.setEnabled(False)
        dialog.bookmark_name_input.setText(profile.name)
        dialog.host_input.setText(profile.host)
        dialog.port_input.setValue(profile.port)
        dialog.username_input.setText(profile.username)
        dialog.password_input.setText(self._mgr.get_password(bid))
        dialog.tls_check.setChecked(profile.use_tls)
        if dialog.exec() == QDialog.Accepted:
            self._mgr.update(bid, name=dialog.bookmark_name or profile.name,
                             host=dialog.host, port=dialog.port,
                             username=dialog.username, password=dialog.password,
                             use_tls=dialog.use_tls)
            self._refresh()

    def _delete_bookmark(self, bid):
        profile = self._mgr.get(bid)
        if not profile:
            return
        if QMessageBox.question(self, "Delete", f"Delete '{profile.name}'?") == QMessageBox.Yes:
            self._mgr.remove(bid)
            self._refresh()

    def _import_bookmarks(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import", "", "JSON (*.json)")
        if path:
            self._mgr.import_bookmarks(path)
            self._refresh()

    def _export_bookmarks(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export", "bookmarks.json", "JSON (*.json)")
        if path:
            self._mgr.export_bookmarks(path, include_passwords=False)


# ════════════════════════════════════════════════════
# Main Window
# ════════════════════════════════════════════════════

class MainWindow(QMainWindow):
    """Tab-based main window with multiple concurrent sessions."""

    def __init__(self, initial_host="", initial_port=443,
                 initial_user="", initial_pass=""):
        super().__init__()
        self.setWindowTitle("Teragucci")
        self.setMinimumSize(900, 600)

        self._bookmarks = BookmarkManager()
        self._sessions: dict[int, Session] = {}  # tab_index -> Session
        self._fullscreen_state = None  # saved UI state for fullscreen restore

        # ── Tabs (central widget) ──
        self._tabs = QTabWidget()
        self._tabs.setTabsClosable(True)
        self._tabs.setMovable(True)
        self._tabs.setDocumentMode(True)
        self._tabs.tabCloseRequested.connect(self._close_tab)
        self._tabs.currentChanged.connect(self._on_tab_changed)
        self.setCentralWidget(self._tabs)

        # "+" button on tab bar
        self._tabs.setCornerWidget(self._make_new_tab_btn(), Qt.TopRightCorner)

        # ── Docks ──
        self._bookmark_dock = QDockWidget("Bookmarks", self)
        self._bookmark_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self._bookmark_panel = BookmarkPanel(self._bookmarks)
        self._bookmark_panel.connect_requested.connect(self._connect_bookmark)
        self._bookmark_dock.setWidget(self._bookmark_panel)
        self.addDockWidget(Qt.LeftDockWidgetArea, self._bookmark_dock)

        self._quality_dock = QDockWidget("Quality", self)
        self._quality_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self._quality_panel = QualityControlPanel()
        self._quality_panel.settings_changed.connect(self._on_quality_changed)
        self._quality_dock.setWidget(self._quality_panel)
        self.addDockWidget(Qt.RightDockWidgetArea, self._quality_dock)

        # ── Toolbar ──
        self._setup_toolbar()

        # ── Status Bar ──
        self._health_status = HealthStatusWidget()
        self._status_label = QLabel("No connections")
        self.statusBar().addWidget(self._status_label)
        self.statusBar().addPermanentWidget(self._health_status)

        # ── Fullscreen toolbar ──
        self._fs_toolbar = FullscreenToolbar()
        self._fs_toolbar.exit_fullscreen.connect(self._toggle_fullscreen)
        self._fs_toolbar.disconnect_requested.connect(
            lambda: self._active_session and self._active_session.disconnect())
        self._fs_toolbar.settings_requested.connect(
            lambda: self._quality_dock.setVisible(not self._quality_dock.isVisible()))
        self._fs_toolbar.hide()

        # ── Timers ──
        self._health_timer = QTimer()
        self._health_timer.timeout.connect(self._update_health)
        self._health_timer.start(500)

        # ── Fullscreen mouse tracking ──
        self.setMouseTracking(True)
        self.centralWidget().setMouseTracking(True)

        # Auto-connect if host given
        if initial_host:
            self._new_session_and_connect(
                initial_host, initial_port, initial_user, initial_pass)

    def _make_new_tab_btn(self):
        btn = QPushButton("+")
        btn.setFixedSize(28, 28)
        btn.setToolTip("New Connection")
        btn.clicked.connect(self._show_connect_dialog)
        return btn

    # ── Toolbar ──────────────────────────────────

    def _setup_toolbar(self):
        tb = QToolBar("Main")
        tb.setMovable(False)
        self.addToolBar(tb)

        tb.addAction(self._action("New Connection", "Ctrl+N", self._show_connect_dialog))
        tb.addAction(self._action("Disconnect", "Ctrl+D", self._disconnect_active))
        tb.addSeparator()
        tb.addAction(self._action("Refresh", "F5",
                     lambda: self._active_session and self._active_session.request_full_frame()))
        tb.addAction(self._action("Fullscreen", "F11", self._toggle_fullscreen))
        tb.addAction(self._action("Health", "F9", self._toggle_health))
        tb.addSeparator()

        tb.addWidget(QLabel(" Monitor: "))
        self._monitor_combo = QComboBox()
        self._monitor_combo.setMinimumWidth(150)
        self._monitor_combo.currentIndexChanged.connect(self._on_monitor_selected)
        tb.addWidget(self._monitor_combo)

        # Menus
        mb = self.menuBar()
        view = mb.addMenu("View")
        view.addAction(self._bookmark_dock.toggleViewAction())
        view.addAction(self._quality_dock.toggleViewAction())
        view.addSeparator()
        view.addAction(self._action("Fullscreen", "F11", self._toggle_fullscreen))
        view.addAction(self._action("Health Overlay", "F9", self._toggle_health))
        view.addSeparator()
        view.addAction(self._action("Key Diagnostic", "F10", self._show_key_diagnostic))

    def _action(self, text, shortcut, slot):
        a = QAction(text, self)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        a.triggered.connect(slot)
        return a

    # ── Properties ───────────────────────────────

    @property
    def _active_session(self) -> Session | None:
        idx = self._tabs.currentIndex()
        return self._sessions.get(idx)

    # ── Session / Tab Management ─────────────────

    def _new_session_and_connect(self, host, port, username, password,
                                  use_tls=True, auto_reconnect=True,
                                  bookmark_id=""):
        session = Session(self)
        idx = self._tabs.addTab(session.viewer, session.display_name)
        self._sessions[idx] = session
        self._tabs.setCurrentIndex(idx)

        # Wire session signals
        session.status_changed.connect(lambda s, i=idx: self._on_session_status(i, s))
        session.title_changed.connect(lambda t, i=idx: self._tabs.setTabText(i, t))
        session.auth_failed.connect(lambda msg: QMessageBox.warning(self, "Auth Failed", msg))
        session.monitor_list_received.connect(self._on_monitor_list)

        session.connect(host, port, username, password,
                        use_tls=use_tls, auto_reconnect=auto_reconnect,
                        bookmark_id=bookmark_id)

        # Send initial quality
        session.apply_quality(self._quality_panel.settings)

        self._status_label.setText(f"Connecting to {host}:{port}...")

    def _close_tab(self, idx):
        session = self._sessions.pop(idx, None)
        if session:
            session.cleanup()
        self._tabs.removeTab(idx)

        # Re-key sessions after removal
        new_sessions = {}
        for i in range(self._tabs.count()):
            # Find the session whose viewer matches this tab
            viewer = self._tabs.widget(i)
            for old_idx, s in list(self._sessions.items()):
                if s.viewer is viewer:
                    new_sessions[i] = s
                    del self._sessions[old_idx]
                    break
        self._sessions.update(new_sessions)

        if self._tabs.count() == 0:
            self._status_label.setText("No connections")
            self._health_status.data = HealthData()

    def _on_tab_changed(self, idx):
        session = self._sessions.get(idx)
        if session:
            self._health_status.data = session.health
            self._status_label.setText(session.display_name)
            if self.isFullScreen():
                self._fs_toolbar.set_connection_label(session.display_name)

    def _on_session_status(self, idx, status):
        session = self._sessions.get(idx)
        if not session:
            return

        # Update tab icon/color hint
        colors = {"connected": theme.SUCCESS, "connecting": theme.WARNING,
                  "disconnected": theme.TEXT_MUTED, "error": theme.DANGER}
        color = colors.get(status, theme.TEXT_MUTED)

        if idx == self._tabs.currentIndex():
            if status == "connected":
                self._status_label.setText(f"Connected: {session.display_name}")
                if session._bookmark_id:
                    self._bookmarks.mark_connected(session._bookmark_id)
            elif status == "disconnected":
                self._status_label.setText(f"Disconnected: {session.display_name}")
            elif status == "connecting":
                self._status_label.setText(f"Connecting: {session.display_name}")

    # ── Actions ──────────────────────────────────

    def _show_connect_dialog(self):
        dialog = ConnectionDialog(self)
        if dialog.exec() == QDialog.Accepted:
            bid = ""
            if dialog.save_bookmark:
                name = dialog.bookmark_name or f"{dialog.host}:{dialog.port}"
                bid = self._bookmarks.add(
                    name=name, host=dialog.host, port=dialog.port,
                    username=dialog.username, password=dialog.password,
                    use_tls=dialog.use_tls)
                self._bookmark_panel._refresh()

            self._new_session_and_connect(
                dialog.host, dialog.port, dialog.username, dialog.password,
                use_tls=dialog.use_tls, auto_reconnect=dialog.auto_reconnect,
                bookmark_id=bid)

    def _connect_bookmark(self, bookmark_id):
        profile = self._bookmarks.get(bookmark_id)
        if not profile:
            return
        password = self._bookmarks.get_password(bookmark_id)
        self._quality_panel.load_from_profile(profile)
        self._new_session_and_connect(
            profile.host, profile.port, profile.username, password,
            use_tls=profile.use_tls, auto_reconnect=profile.auto_connect,
            bookmark_id=bookmark_id)

    def _disconnect_active(self):
        s = self._active_session
        if s:
            s.disconnect()

    def _on_quality_changed(self, settings):
        s = self._active_session
        if s:
            s.apply_quality(settings)

    def _on_monitor_selected(self, index):
        if index >= 0:
            mon_id = self._monitor_combo.itemData(index)
            s = self._active_session
            if s and mon_id is not None:
                s.select_monitor(mon_id)

    def _on_monitor_list(self, monitors):
        self._monitor_combo.blockSignals(True)
        self._monitor_combo.clear()
        for mon in monitors:
            label = f"{mon.get('name', 'Monitor')} ({mon['width']}x{mon['height']})"
            self._monitor_combo.addItem(label, mon.get("id", 0))
        self._monitor_combo.blockSignals(False)
        if self.isFullScreen():
            self._fs_toolbar.update_monitors(monitors)

    def _toggle_health(self):
        s = self._active_session
        if s:
            s.overlay.toggle()

    def _show_key_diagnostic(self):
        from client.key_diagnostic import KeyDiagnosticDialog
        diag = KeyDiagnosticDialog(self)
        diag.show()

    # ── Fullscreen ───────────────────────────────

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self._exit_fullscreen()
        else:
            self._enter_fullscreen()

    def _enter_fullscreen(self):
        # Save state
        self._fullscreen_state = {
            "toolbar": not self.findChild(QToolBar).isHidden(),
            "menubar": not self.menuBar().isHidden(),
            "statusbar": not self.statusBar().isHidden(),
            "bookmarks": self._bookmark_dock.isVisible(),
            "quality": self._quality_dock.isVisible(),
            "tabbar": self._tabs.tabBar().isVisible(),
        }
        # Hide everything
        self.findChild(QToolBar).hide()
        self.menuBar().hide()
        self.statusBar().hide()
        self._bookmark_dock.hide()
        self._quality_dock.hide()
        self._tabs.tabBar().hide()

        self.showFullScreen()

        # Position fullscreen toolbar
        screen = self.screen()
        if screen:
            self._fs_toolbar.position_on_screen(screen.geometry())
            s = self._active_session
            if s:
                self._fs_toolbar.set_connection_label(s.display_name)

        # Install event filter for mouse edge detection
        self.installEventFilter(self)

    def _exit_fullscreen(self):
        self.showNormal()
        self._fs_toolbar.hide()
        self.removeEventFilter(self)

        # Restore state
        st = self._fullscreen_state or {}
        if st.get("toolbar", True):
            self.findChild(QToolBar).show()
        if st.get("menubar", True):
            self.menuBar().show()
        if st.get("statusbar", True):
            self.statusBar().show()
        if st.get("bookmarks", True):
            self._bookmark_dock.show()
        if st.get("quality", False):
            self._quality_dock.show()
        self._tabs.tabBar().setVisible(st.get("tabbar", True))
        self._fullscreen_state = None

    def eventFilter(self, obj, event):
        """Detect mouse at top edge for fullscreen toolbar reveal."""
        if self.isFullScreen() and event.type() == QEvent.MouseMove:
            if event.globalPosition().y() <= REVEAL_ZONE:
                self._fs_toolbar.reveal()
        return super().eventFilter(obj, event)

    def mouseMoveEvent(self, event):
        """Also handle mouse moves on the main window itself."""
        if self.isFullScreen():
            if event.globalPosition().y() <= REVEAL_ZONE:
                self._fs_toolbar.reveal()
        super().mouseMoveEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape and self.isFullScreen():
            self._exit_fullscreen()
            return
        super().keyPressEvent(event)

    # ── Health Updates ───────────────────────────

    def _update_health(self):
        self._health_status.update_display()
        s = self._active_session
        if s:
            s.overlay.update()
            if self.isFullScreen():
                self._fs_toolbar.update_health(s.health)

    # ── Resize ───────────────────────────────────

    def resizeEvent(self, event):
        super().resizeEvent(event)
        s = self._active_session
        if s:
            s.overlay.setGeometry(s.viewer.geometry())
        # Debounced resize request
        if not hasattr(self, '_resize_timer'):
            self._resize_timer = QTimer()
            self._resize_timer.setSingleShot(True)
            self._resize_timer.timeout.connect(self._send_resize)
        self._resize_timer.start(500)

    def _send_resize(self):
        s = self._active_session
        if s and s.is_connected:
            s.send_resize(s.viewer.width(), s.viewer.height())

    def closeEvent(self, event):
        for session in self._sessions.values():
            session.cleanup()
        event.accept()


# ════════════════════════════════════════════════════
# Entry Point
# ════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Teragucci Remote Desktop Client")
    parser.add_argument("--host", default="", help="Server hostname or IP")
    parser.add_argument("--port", type=int, default=443)
    parser.add_argument("--username", "-u", default="")
    parser.add_argument("--password", "-p", default="")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    # macOS: don't swap Control/Meta so physical Control = Control_L on Linux
    if sys.platform == "darwin":
        QApplication.setAttribute(Qt.AA_MacDontSwapCtrlAndMeta, True)

    app = QApplication(sys.argv)
    app.setApplicationName("Teragucci")
    app.setApplicationDisplayName("Teragucci")
    app.setOrganizationName("Teragucci")
    app.setDesktopFileName("teragucci")
    app.setStyle("Fusion")

    # macOS: override process name so dock/menu bar shows "Teragucci"
    import platform
    if platform.system() == "Darwin":
        try:
            from Foundation import NSBundle  # type: ignore
            bundle = NSBundle.mainBundle()
            info = bundle.localizedInfoDictionary() or bundle.infoDictionary()
            if info:
                info["CFBundleName"] = "Teragucci"
                info["CFBundleDisplayName"] = "Teragucci"
        except ImportError:
            pass
    app.setStyleSheet(theme.generate_stylesheet())

    window = MainWindow(
        initial_host=args.host, initial_port=args.port,
        initial_user=args.username, initial_pass=args.password)
    window.resize(1440, 900)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
