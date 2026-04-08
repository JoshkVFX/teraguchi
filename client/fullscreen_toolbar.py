"""
Auto-hiding slide-down toolbar for fullscreen mode.

Appears when the cursor touches the top edge of the screen.
Hides automatically when the cursor moves away.
"""

import logging

from PySide6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QPoint, QEasingCurve, Signal,
)
from PySide6.QtGui import QColor, QPainter, QFont
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QGraphicsDropShadowEffect, QApplication,
)

from client import theme

logger = logging.getLogger(__name__)

TOOLBAR_HEIGHT = 48
REVEAL_ZONE = 3          # pixels from top edge to trigger reveal
HIDE_DELAY_MS = 1200     # ms after mouse leaves before hiding


class FullscreenToolbar(QWidget):
    """
    Slide-down toolbar that appears at the top of the screen in fullscreen mode.
    """

    exit_fullscreen = Signal()
    disconnect_requested = Signal()
    settings_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedHeight(TOOLBAR_HEIGHT)
        self.setMouseTracking(True)

        self._visible = False
        self._animation = QPropertyAnimation(self, b"pos")
        self._animation.setDuration(200)
        self._animation.setEasingCurve(QEasingCurve.OutCubic)

        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._slide_up)

        # Shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 160))
        shadow.setOffset(0, 4)
        self.setGraphicsEffect(shadow)

        self._build_ui()

    def _build_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(12)

        # Connection label
        self._conn_label = QLabel("Not Connected")
        self._conn_label.setStyleSheet(
            f"color: {theme.TEXT_PRIMARY}; font-weight: 600; font-size: 13px;")
        layout.addWidget(self._conn_label)

        layout.addSpacing(8)

        # Separator
        sep = QLabel("|")
        sep.setStyleSheet(f"color: {theme.BORDER};")
        layout.addWidget(sep)

        layout.addSpacing(8)

        # Monitor selector
        self._monitor_combo = QComboBox()
        self._monitor_combo.setMinimumWidth(120)
        self._monitor_combo.setMaximumWidth(200)
        layout.addWidget(self._monitor_combo)

        layout.addStretch()

        # Health summary
        self._health_dot = QLabel()
        self._health_dot.setFixedSize(8, 8)
        self._health_dot.setStyleSheet(
            f"border-radius: 4px; background: {theme.TEXT_MUTED};")
        layout.addWidget(self._health_dot)

        self._latency_label = QLabel("-- ms")
        self._latency_label.setStyleSheet(
            f"color: {theme.TEXT_SECONDARY}; font-size: 12px;")
        layout.addWidget(self._latency_label)

        self._fps_label = QLabel("-- fps")
        self._fps_label.setStyleSheet(
            f"color: {theme.TEXT_SECONDARY}; font-size: 12px;")
        layout.addWidget(self._fps_label)

        layout.addSpacing(12)

        # Settings button
        settings_btn = QPushButton("Settings")
        settings_btn.setFixedHeight(30)
        settings_btn.clicked.connect(self.settings_requested.emit)
        layout.addWidget(settings_btn)

        # Disconnect button
        dc_btn = QPushButton("Disconnect")
        dc_btn.setFixedHeight(30)
        dc_btn.setProperty("danger", True)
        dc_btn.clicked.connect(self.disconnect_requested.emit)
        layout.addWidget(dc_btn)

        # Exit fullscreen
        exit_btn = QPushButton("Exit Fullscreen")
        exit_btn.setFixedHeight(30)
        exit_btn.clicked.connect(self.exit_fullscreen.emit)
        layout.addWidget(exit_btn)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QColor(theme.BG_SECONDARY + "ee"))  # slight transparency
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(0, 0, self.width(), self.height(), 0, 0)
        p.end()

    def position_on_screen(self, screen_geo):
        """Position above the screen (hidden) ready for slide-down."""
        w = screen_geo.width()
        x = screen_geo.x()
        self.setFixedWidth(w)
        self._screen_geo = screen_geo
        self._hidden_pos = QPoint(x, screen_geo.y() - TOOLBAR_HEIGHT)
        self._shown_pos = QPoint(x, screen_geo.y())
        self.move(self._hidden_pos)

    def reveal(self):
        if self._visible:
            self._hide_timer.stop()
            return
        self._visible = True
        self.show()
        self.raise_()
        self._animation.stop()
        self._animation.setStartValue(self.pos())
        self._animation.setEndValue(self._shown_pos)
        self._animation.start()

    def _slide_up(self):
        if not self._visible:
            return
        self._visible = False
        self._animation.stop()
        self._animation.setStartValue(self.pos())
        self._animation.setEndValue(self._hidden_pos)
        self._animation.start()

    def enterEvent(self, event):
        self._hide_timer.stop()

    def leaveEvent(self, event):
        self._hide_timer.start(HIDE_DELAY_MS)

    def update_health(self, health_data):
        color = health_data.quality_color
        self._health_dot.setStyleSheet(f"border-radius: 4px; background: {color};")
        self._latency_label.setText(f"{health_data.rtt_ms:.0f} ms")
        self._fps_label.setText(f"{health_data.fps_actual:.0f} fps")

    def set_connection_label(self, text: str):
        self._conn_label.setText(text)

    def update_monitors(self, monitors: list):
        self._monitor_combo.blockSignals(True)
        self._monitor_combo.clear()
        for mon in monitors:
            label = f"{mon.get('name', 'Monitor')} ({mon['width']}x{mon['height']})"
            self._monitor_combo.addItem(label, mon.get("id", 0))
        self._monitor_combo.blockSignals(False)
