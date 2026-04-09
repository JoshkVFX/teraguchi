"""
Built-in keystroke diagnostic dialog for Teragucci.

Shows the full key translation path in real time:
  Physical key → Qt key code → Wire message → X11 keysym

Accessible from View → Key Diagnostic (F10) in the client.
"""

import sys
import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent, QFont
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QTextEdit, QPushButton, QHBoxLayout,
)

logger = logging.getLogger(__name__)

# Qt key code → X11 keysym (must match server/xtest_injector.py QT_TO_XKEYSYM)
_QT_TO_XKEYSYM = {
    0x01000000: 'Escape', 0x01000001: 'Tab', 0x01000003: 'BackSpace',
    0x01000004: 'Return', 0x01000005: 'KP_Enter', 0x01000006: 'Insert',
    0x01000007: 'Delete', 0x01000008: 'Pause', 0x01000009: 'Print',
    0x01000010: 'Home', 0x01000011: 'End',
    0x01000012: 'Left', 0x01000013: 'Up', 0x01000014: 'Right', 0x01000015: 'Down',
    0x01000016: 'Page_Up', 0x01000017: 'Page_Down',
    0x01000020: 'Shift_L', 0x01000021: 'Control_L', 0x01000022: 'Meta_L',
    0x01000023: 'Alt_L', 0x01000024: 'Caps_Lock', 0x01000025: 'Num_Lock',
    0x01000026: 'Scroll_Lock',
    0x01000030: 'F1', 0x01000031: 'F2', 0x01000032: 'F3', 0x01000033: 'F4',
    0x01000034: 'F5', 0x01000035: 'F6', 0x01000036: 'F7', 0x01000037: 'F8',
    0x01000038: 'F9', 0x01000039: 'F10', 0x0100003a: 'F11', 0x0100003b: 'F12',
    0x01000058: 'Super_L', 0x01000059: 'Super_R',
    0x01000055: 'Menu',
    0x20: 'space',
}

_QT_KEY_NAMES = {
    0x01000000: "Escape", 0x01000001: "Tab", 0x01000002: "Backtab",
    0x01000003: "Backspace", 0x01000004: "Return", 0x01000005: "KP_Enter",
    0x01000006: "Insert", 0x01000007: "Delete", 0x01000008: "Pause",
    0x01000009: "Print",
    0x01000010: "Home", 0x01000011: "End",
    0x01000012: "Left", 0x01000013: "Up", 0x01000014: "Right", 0x01000015: "Down",
    0x01000016: "PageUp", 0x01000017: "PageDown",
    0x01000020: "Shift", 0x01000021: "Control", 0x01000022: "Meta",
    0x01000023: "Alt", 0x01000024: "CapsLock", 0x01000025: "NumLock",
    0x01000026: "ScrollLock",
    0x01000030: "F1", 0x01000031: "F2", 0x01000032: "F3", 0x01000033: "F4",
    0x01000034: "F5", 0x01000035: "F6", 0x01000036: "F7", 0x01000037: "F8",
    0x01000038: "F9", 0x01000039: "F10", 0x0100003a: "F11", 0x0100003b: "F12",
    0x01000058: "Super_L", 0x01000059: "Super_R", 0x01000055: "Menu",
    0x20: "Space",
}


def _key_name(code: int) -> str:
    if code in _QT_KEY_NAMES:
        return _QT_KEY_NAMES[code]
    if 0x20 <= code <= 0x7e:
        return chr(code)
    return f"0x{code:x}"


def _mods_str(mods) -> str:
    parts = []
    if mods & Qt.ShiftModifier:
        parts.append("Shift")
    if mods & Qt.ControlModifier:
        parts.append("Ctrl")
    if mods & Qt.AltModifier:
        parts.append("Alt")
    if mods & Qt.MetaModifier:
        parts.append("Meta")
    return "+".join(parts) if parts else ""


def _x11_target(qt_key: int) -> str:
    if qt_key in _QT_TO_XKEYSYM:
        return _QT_TO_XKEYSYM[qt_key]
    if 0x20 <= qt_key <= 0x7e:
        return f"'{chr(qt_key).lower()}'"
    return "UNMAPPED"


class KeyDiagnosticDialog(QDialog):
    """Modal-less dialog that captures keystrokes and shows the translation path."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Teragucci — Key Diagnostic")
        self.setMinimumSize(680, 480)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setFocusPolicy(Qt.StrongFocus)

        layout = QVBoxLayout(self)

        # Header
        header = QLabel(
            "Press any key or combo to see how Teragucci translates it.\n"
            "Green = mapped to X11   Red = UNMAPPED (will be dropped)")
        header.setWordWrap(True)
        layout.addWidget(header)

        # Current keystroke display
        mono = QFont("Menlo" if sys.platform == "darwin" else "Monospace", 16)
        self._current = QLabel("Press a key...")
        self._current.setFont(mono)
        self._current.setStyleSheet(
            "background: #1a1a2e; color: #e0e0e0; padding: 16px; border-radius: 8px;")
        self._current.setMinimumHeight(80)
        layout.addWidget(self._current)

        # Platform info
        dont_swap = getattr(Qt, 'AA_MacDontSwapCtrlAndMeta', None)
        plat_text = f"Platform: {sys.platform}"
        if sys.platform == "darwin" and dont_swap is not None:
            plat_text += "  |  AA_MacDontSwapCtrlAndMeta: ON"
        layout.addWidget(QLabel(plat_text))

        # Event log
        layout.addWidget(QLabel("Event log (most recent at bottom):"))
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setFont(QFont("Menlo" if sys.platform == "darwin" else "Monospace", 11))
        self._log.setStyleSheet("background: #0d1117; color: #c9d1d9;")
        layout.addWidget(self._log)

        # Flame reference
        ref = QLabel(
            "Flame keys to test: Ctrl+Z · Ctrl+Shift+Z · F5–F8 · "
            "` (backtick) · Tab · Space · Esc · Ctrl+C · Delete · Home/End")
        ref.setWordWrap(True)
        ref.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(ref)

        # Buttons
        btn_row = QHBoxLayout()
        clear_btn = QPushButton("Clear Log")
        clear_btn.clicked.connect(self._log.clear)
        btn_row.addWidget(clear_btn)
        btn_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self._count = 0

    def keyPressEvent(self, event: QKeyEvent):
        if event.isAutoRepeat():
            return
        self._record(event, pressed=True)
        event.accept()

    def keyReleaseEvent(self, event: QKeyEvent):
        if event.isAutoRepeat():
            return
        self._record(event, pressed=False)
        event.accept()

    def _record(self, event: QKeyEvent, pressed: bool):
        qt_key = event.key()
        raw_mods = event.modifiers()
        name = _key_name(qt_key)
        x11 = _x11_target(qt_key)
        mapped = x11 != "UNMAPPED"
        action = "PRESS  " if pressed else "RELEASE"
        mods = _mods_str(raw_mods)

        # Update big display on press
        if pressed:
            combo = f"{mods}+{name}" if mods and qt_key not in (
                Qt.Key_Shift, Qt.Key_Control, Qt.Key_Alt, Qt.Key_Meta) else name
            color = "#00ff88" if mapped else "#ff4444"
            self._current.setText(
                f'<span style="color:{color}; font-size:18px">{combo}</span><br>'
                f'<span style="color:#888; font-size:13px">'
                f'Qt: 0x{qt_key:x}  →  X11: {x11}</span>')

        # Log line
        self._count += 1
        color = "#00ff88" if mapped else "#ff4444"
        press_color = "#88ccff" if pressed else "#555"
        mod_display = mods if mods else "—"
        self._log.append(
            f'<span style="color:#555">{self._count:4d}</span> '
            f'<span style="color:{press_color}">{action}</span> '
            f'<span style="color:{color}">{name:12s}</span> '
            f'<span style="color:#888">mods=[{mod_display:16s}]  '
            f'qt=0x{qt_key:08x}  →  x11={x11}</span>')
