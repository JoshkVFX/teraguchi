"""
XTest-based input injector for Xvfb virtual displays.

Uses the X11 XTest extension for mouse/keyboard injection,
which works with Xvfb unlike uinput (kernel-level devices).
"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from Xlib import X, display as xdisplay, ext
    from Xlib.ext import xtest
    from Xlib.XK import string_to_keysym
    XLIB_AVAILABLE = True
except ImportError:
    XLIB_AVAILABLE = False
    logger.warning("python-xlib not installed — XTest input unavailable")


# Qt key code → X11 keysym mapping (common keys)
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


class XTestInputInjector:
    """Input injector using X11 XTest extension for Xvfb displays."""

    def __init__(self, display_name: str, screen_width: int = 1920, screen_height: int = 1080):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self._display_name = display_name

        if not XLIB_AVAILABLE:
            raise RuntimeError("python-xlib required for XTest input injection")

        self._dpy = xdisplay.Display(display_name)
        # Verify XTest extension
        if not self._dpy.has_extension('XTEST'):
            raise RuntimeError(f"XTest extension not available on {display_name}")

        self._root = self._dpy.screen().root
        logger.info("XTest input injector ready on %s (%dx%d)",
                     display_name, screen_width, screen_height)

    def move_abs(self, x_norm: float, y_norm: float):
        """Move mouse to absolute position. x, y are normalized 0.0-1.0."""
        x = int(x_norm * (self.screen_width - 1))
        y = int(y_norm * (self.screen_height - 1))
        x = max(0, min(x, self.screen_width - 1))
        y = max(0, min(y, self.screen_height - 1))
        xtest.fake_input(self._dpy, X.MotionNotify, x=x, y=y, root=self._root)
        self._dpy.sync()

    def button(self, button: int, pressed: bool):
        """Press/release mouse button. button: 1=left, 2=middle, 3=right."""
        event_type = X.ButtonPress if pressed else X.ButtonRelease
        xtest.fake_input(self._dpy, event_type, detail=button)
        self._dpy.sync()

    def click(self, button: int = 1):
        """Click a mouse button."""
        self.button(button, True)
        self.button(button, False)

    def scroll(self, dx: int, dy: int):
        """Scroll wheel. dy>0 = up, dy<0 = down."""
        if dy > 0:
            for _ in range(abs(dy)):
                xtest.fake_input(self._dpy, X.ButtonPress, detail=4)
                xtest.fake_input(self._dpy, X.ButtonRelease, detail=4)
        elif dy < 0:
            for _ in range(abs(dy)):
                xtest.fake_input(self._dpy, X.ButtonPress, detail=5)
                xtest.fake_input(self._dpy, X.ButtonRelease, detail=5)
        if dx > 0:
            for _ in range(abs(dx)):
                xtest.fake_input(self._dpy, X.ButtonPress, detail=6)
                xtest.fake_input(self._dpy, X.ButtonRelease, detail=6)
        elif dx < 0:
            for _ in range(abs(dx)):
                xtest.fake_input(self._dpy, X.ButtonPress, detail=7)
                xtest.fake_input(self._dpy, X.ButtonRelease, detail=7)
        self._dpy.sync()

    def key(self, qt_key: int, pressed: bool):
        """Press/release a key by Qt key code."""
        keycode = self._qt_key_to_keycode(qt_key)
        if keycode:
            event_type = X.KeyPress if pressed else X.KeyRelease
            xtest.fake_input(self._dpy, event_type, detail=keycode)
            self._dpy.sync()

    def key_char(self, char: str, pressed: bool):
        """Press/release a key by character."""
        keysym = string_to_keysym(char)
        if keysym == 0 and len(char) == 1:
            keysym = ord(char)
        keycode = self._dpy.keysym_to_keycode(keysym)
        if keycode:
            event_type = X.KeyPress if pressed else X.KeyRelease
            xtest.fake_input(self._dpy, event_type, detail=keycode)
            self._dpy.sync()

    def pen_move(self, x_norm: float, y_norm: float, pressure: float = 0.0):
        """Pen/stylus move — mapped to mouse move (XTest has no pressure)."""
        self.move_abs(x_norm, y_norm)

    def pen_button(self, button: int, pressed: bool):
        """Pen button — mapped to mouse button."""
        self.button(button, pressed)

    def _qt_key_to_keycode(self, qt_key: int) -> Optional[int]:
        """Convert Qt key code to X11 keycode."""
        # Check special keys map
        keysym_name = QT_TO_XKEYSYM.get(qt_key)
        if keysym_name:
            keysym = string_to_keysym(keysym_name)
            if keysym:
                return self._dpy.keysym_to_keycode(keysym)

        # ASCII range
        if 0x20 <= qt_key <= 0x7e:
            char = chr(qt_key).lower()
            keysym = string_to_keysym(char)
            if keysym == 0:
                keysym = ord(char)
            return self._dpy.keysym_to_keycode(keysym)

        return None

    def handle_message(self, msg: dict):
        """Dispatch input message — compatible with InputInjector API."""
        msg_type = msg.get("type")

        if msg_type == "mouse_move":
            self.move_abs(msg["x"], msg["y"])

        elif msg_type == "mouse_button":
            self.move_abs(msg["x"], msg["y"])
            self.button(msg["button"], msg["pressed"])

        elif msg_type == "mouse_scroll":
            self.move_abs(msg["x"], msg["y"])
            self.scroll(msg.get("dx", 0), msg.get("dy", 0))

        elif msg_type == "key_event":
            # scan_code here is Qt key code (NOT Linux scancode)
            self.key(msg["scan_code"], msg["pressed"])

        elif msg_type == "pen_event":
            self.pen_move(msg["x"], msg["y"], msg.get("pressure", 0.0))
            if msg.get("button", 0) and "pressed" in msg:
                self.pen_button(msg["button"], msg["pressed"])

    def close(self):
        if self._dpy:
            self._dpy.close()
            self._dpy = None
