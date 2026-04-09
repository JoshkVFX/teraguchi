#!/usr/bin/env python3
"""
Teragucci Keystroke Diagnostic Tool

Shows the full key translation path:
  Physical key → Qt key code → Wire message → X11 keysym → X11 keycode

Run on the Mac client to see exactly what Qt captures and what gets sent
to the remote server. Essential for verifying Flame hotkeys work correctly.

Usage:
    python tools/keydiag.py                   # interactive Qt window
    python tools/keydiag.py --server :10      # server-side X11 keycode dump
"""

import sys
import os
import argparse

# ── Qt key name lookup table ──────────────────────────────────────────
# Reverse of the viewer's mapping — for human-readable output
QT_KEY_NAMES = {
    0x01000000: "Escape", 0x01000001: "Tab", 0x01000002: "Backtab",
    0x01000003: "Backspace", 0x01000004: "Return", 0x01000005: "KP_Enter",
    0x01000006: "Insert", 0x01000007: "Delete", 0x01000008: "Pause",
    0x01000009: "Print", 0x0100000a: "SysReq", 0x0100000b: "Clear",
    0x01000010: "Home", 0x01000011: "End",
    0x01000012: "Left", 0x01000013: "Up", 0x01000014: "Right", 0x01000015: "Down",
    0x01000016: "PageUp", 0x01000017: "PageDown",
    0x01000020: "Shift", 0x01000021: "Control", 0x01000022: "Meta",
    0x01000023: "Alt", 0x01000024: "CapsLock", 0x01000025: "NumLock",
    0x01000026: "ScrollLock",
    0x01000030: "F1", 0x01000031: "F2", 0x01000032: "F3", 0x01000033: "F4",
    0x01000034: "F5", 0x01000035: "F6", 0x01000036: "F7", 0x01000037: "F8",
    0x01000038: "F9", 0x01000039: "F10", 0x0100003a: "F11", 0x0100003b: "F12",
    0x01000058: "Super_L", 0x01000059: "Super_R",
    0x01000055: "Menu",
    0x20: "Space",
}

# XTest mapping (must match server/xtest_injector.py QT_TO_XKEYSYM)
QT_TO_XKEYSYM = {
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


def qt_key_name(code: int) -> str:
    """Human-readable name for a Qt key code."""
    if code in QT_KEY_NAMES:
        return QT_KEY_NAMES[code]
    if 0x20 <= code <= 0x7e:
        return chr(code)
    return f"Unknown(0x{code:x})"


def mods_str(mods: int) -> str:
    """Modifier bitmask to readable string."""
    parts = []
    if mods & 1:
        parts.append("Shift")
    if mods & 2:
        parts.append("Ctrl")
    if mods & 4:
        parts.append("Alt")
    if mods & 8:
        parts.append("Meta")
    return "+".join(parts) if parts else "none"


def xkeysym_for_qt(qt_key: int) -> str:
    """What X11 keysym the server will map this to."""
    if qt_key in QT_TO_XKEYSYM:
        return QT_TO_XKEYSYM[qt_key]
    if 0x20 <= qt_key <= 0x7e:
        return f"'{chr(qt_key).lower()}' (ASCII)"
    return "UNMAPPED — will be DROPPED"


# ══════════════════════════════════════════════════════════════════
# Client-side: Interactive Qt key capture window
# ══════════════════════════════════════════════════════════════════

def run_client_diag():
    """Qt window that captures and displays every keystroke."""
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtGui import QKeyEvent, QFont
    from PySide6.QtWidgets import (
        QApplication, QWidget, QVBoxLayout, QLabel,
        QTextEdit, QHBoxLayout,
    )

    # Same setting as the real client
    if sys.platform == "darwin":
        QApplication.setAttribute(Qt.AA_MacDontSwapCtrlAndMeta, True)

    app = QApplication(sys.argv)
    app.setApplicationName("Teragucci Key Diagnostic")

    class KeyDiagWindow(QWidget):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("Teragucci Key Diagnostic")
            self.setMinimumSize(700, 500)
            self.setFocusPolicy(Qt.StrongFocus)

            layout = QVBoxLayout(self)

            # Header
            header = QLabel(
                "Press any key or combo. Shows what Teragucci would send to the remote server.\n"
                "Green = mapped correctly  |  Red = UNMAPPED (will be dropped)")
            header.setWordWrap(True)
            layout.addWidget(header)

            # Current key display
            self._current = QLabel("Waiting for keypress...")
            self._current.setFont(QFont("Menlo" if sys.platform == "darwin" else "Monospace", 16))
            self._current.setStyleSheet(
                "background: #1a1a2e; color: #e0e0e0; padding: 16px; border-radius: 8px;")
            self._current.setMinimumHeight(80)
            layout.addWidget(self._current)

            # Platform info
            plat = QLabel(
                f"Platform: {sys.platform}  |  "
                f"AA_MacDontSwapCtrlAndMeta: "
                f"{'ON' if sys.platform == 'darwin' else 'N/A (not macOS)'}")
            plat.setStyleSheet("color: #888; font-size: 11px;")
            layout.addWidget(plat)

            # Event log
            layout.addWidget(QLabel("Event log:"))
            self._log = QTextEdit()
            self._log.setReadOnly(True)
            self._log.setFont(QFont("Menlo" if sys.platform == "darwin" else "Monospace", 11))
            self._log.setStyleSheet("background: #0d1117; color: #c9d1d9;")
            layout.addWidget(self._log)

            # Flame hotkey reference
            ref = QLabel(
                "Flame keys to test: Ctrl+Z (undo) · Ctrl+Shift+Z (redo) · "
                "F5–F8 (views) · ` (backtick) · Tab · Shift+click · "
                "Ctrl+click · Alt+drag · Space+drag · Esc")
            ref.setWordWrap(True)
            ref.setStyleSheet("color: #888; font-size: 11px; margin-top: 8px;")
            layout.addWidget(ref)

            self._event_count = 0

        def keyPressEvent(self, event: QKeyEvent):
            self._log_key(event, pressed=True)
            event.accept()

        def keyReleaseEvent(self, event: QKeyEvent):
            if event.isAutoRepeat():
                return
            self._log_key(event, pressed=False)
            event.accept()

        def _log_key(self, event: QKeyEvent, pressed: bool):
            if event.isAutoRepeat():
                return

            qt_key = event.key()
            raw_mods = event.modifiers()
            action = "PRESS  " if pressed else "RELEASE"

            # Modifiers bitmask (same encoding as viewer.py)
            mod_bits = 0
            if raw_mods & Qt.ShiftModifier:
                mod_bits |= 1
            if raw_mods & Qt.ControlModifier:
                mod_bits |= 2
            if raw_mods & Qt.AltModifier:
                mod_bits |= 4
            if raw_mods & Qt.MetaModifier:
                mod_bits |= 8

            name = qt_key_name(qt_key)
            x11_target = xkeysym_for_qt(qt_key)
            mapped = "UNMAPPED" not in x11_target

            # Wire message (what would be sent to server)
            wire = (f'{{"type":"key_event", "scan_code":0x{qt_key:x}, '
                    f'"pressed":{str(pressed).lower()}, "modifiers":{mod_bits}}}')

            # Update current display
            if pressed:
                mod_prefix = mods_str(mod_bits)
                if mod_prefix != "none" and qt_key not in (
                        Qt.Key_Shift, Qt.Key_Control, Qt.Key_Alt, Qt.Key_Meta):
                    combo = f"{mod_prefix}+{name}"
                else:
                    combo = name
                color = "#00c878" if mapped else "#e5484d"
                self._current.setText(
                    f'<span style="color:{color}; font-size:18px">{combo}</span><br>'
                    f'<span style="color:#888; font-size:13px">'
                    f'Qt: 0x{qt_key:x} → X11: {x11_target}</span>')

            # Log entry
            self._event_count += 1
            color = "#00c878" if mapped else "#e5484d"
            log_line = (
                f'<span style="color:#666">{self._event_count:4d}</span> '
                f'<span style="color:{"#88ccff" if pressed else "#666"}">{action}</span> '
                f'<span style="color:{color}">{name:12s}</span> '
                f'<span style="color:#888">qt=0x{qt_key:08x}  mods={mods_str(mod_bits):16s}  '
                f'→ x11={x11_target}</span>')
            self._log.append(log_line)

            # Also print to terminal for easy copying
            print(f"{action} {name:12s}  qt=0x{qt_key:08x}  mods={mods_str(mod_bits):16s}  "
                  f"→ x11={x11_target}")

    win = KeyDiagWindow()
    win.show()
    win.setFocus()
    sys.exit(app.exec())


# ══════════════════════════════════════════════════════════════════
# Server-side: X11 keycode mapping verification
# ══════════════════════════════════════════════════════════════════

def run_server_diag(display: str):
    """Verify X11 keysym → keycode mappings on the server display."""
    try:
        from Xlib import display as xdisplay
        from Xlib.XK import string_to_keysym
    except ImportError:
        print("ERROR: python-xlib not installed. Install with: pip install python-xlib")
        sys.exit(1)

    print(f"Teragucci Server Key Diagnostic — Display {display}")
    print("=" * 70)

    try:
        dpy = xdisplay.Display(display)
    except Exception as e:
        print(f"ERROR: Cannot open display {display}: {e}")
        sys.exit(1)

    print(f"Display: {display}")
    print(f"XTest available: {dpy.has_extension('XTEST')}")
    print()

    # Check all special key mappings
    print("Special key mappings (QT_TO_XKEYSYM):")
    print(f"  {'Qt Code':>12s}  {'Qt Name':12s}  {'X11 Keysym':15s}  {'X11 Keycode':>11s}  Status")
    print(f"  {'─'*12}  {'─'*12}  {'─'*15}  {'─'*11}  {'─'*8}")

    issues = []
    for qt_key in sorted(QT_TO_XKEYSYM.keys()):
        xname = QT_TO_XKEYSYM[qt_key]
        keysym = string_to_keysym(xname)
        keycode = dpy.keysym_to_keycode(keysym) if keysym else 0
        qt_name = qt_key_name(qt_key)

        if keycode > 0:
            status = "OK"
            color = ""
        else:
            status = "MISSING"
            color = " <<<< "
            issues.append((qt_name, xname))

        print(f"  0x{qt_key:08x}  {qt_name:12s}  {xname:15s}  {keycode:11d}  {status}{color}")

    # Check ASCII range
    print()
    print("ASCII key mappings (a-z, 0-9, symbols):")
    ascii_issues = []
    for code in range(0x20, 0x7f):
        char = chr(code).lower()
        keysym = string_to_keysym(char)
        if keysym == 0:
            keysym = ord(char)
        keycode = dpy.keysym_to_keycode(keysym)
        if keycode == 0:
            ascii_issues.append(char)

    if ascii_issues:
        print(f"  MISSING keycodes for: {', '.join(repr(c) for c in ascii_issues)}")
    else:
        print(f"  All ASCII keys (0x20–0x7e) map correctly.")

    # Flame-critical combos
    print()
    print("Flame-critical key verification:")
    flame_keys = [
        ("Ctrl+Z (Undo)", "Control_L", "z"),
        ("Ctrl+Shift+Z (Redo)", "Control_L", "z"),  # Shift is separate press
        ("Ctrl+C (Copy/SIGINT)", "Control_L", "c"),
        ("Ctrl+V (Paste)", "Control_L", "v"),
        ("Ctrl+S (Save)", "Control_L", "s"),
        ("Tab (Timeline)", "Tab", None),
        ("Escape", "Escape", None),
        ("Space (Pan)", "space", None),
        ("Backtick (Toggle)", "grave", None),
        ("F5 (Player)", "F5", None),
        ("F6 (Timeline)", "F6", None),
        ("F7 (Batch)", "F7", None),
        ("F8 (Tools)", "F8", None),
        ("F11 (Fullscreen)", "F11", None),
        ("Delete", "Delete", None),
        ("Home", "Home", None),
        ("End", "End", None),
    ]

    for label, key1_name, key2_name in flame_keys:
        ks1 = string_to_keysym(key1_name)
        kc1 = dpy.keysym_to_keycode(ks1) if ks1 else 0
        if key2_name:
            ks2 = string_to_keysym(key2_name)
            kc2 = dpy.keysym_to_keycode(ks2) if ks2 else 0
            ok = kc1 > 0 and kc2 > 0
        else:
            ok = kc1 > 0

        status = "OK" if ok else "FAIL"
        print(f"  {label:30s}  {status}")

    dpy.close()

    # Summary
    print()
    if issues:
        print(f"WARNING: {len(issues)} special key(s) have no X11 keycode:")
        for qt_name, xname in issues:
            print(f"  - {qt_name} ({xname})")
    else:
        print("All key mappings verified successfully.")


# ══════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Teragucci Keystroke Diagnostic Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python tools/keydiag.py                  # Client mode (interactive Qt window)
  python tools/keydiag.py --server :10     # Server mode (verify X11 mappings)
  python tools/keydiag.py --server :10 --display :10  # Same thing
        """)
    parser.add_argument("--server", metavar="DISPLAY",
                        help="Server mode: verify X11 keymaps on DISPLAY (e.g. :10)")

    args = parser.parse_args()

    if args.server:
        run_server_diag(args.server)
    else:
        run_client_diag()


if __name__ == "__main__":
    main()
