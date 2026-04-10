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
    0x01000000: 'Escape', 0x01000001: 'Tab', 0x01000002: 'ISO_Left_Tab',
    0x01000003: 'BackSpace',
    0x01000004: 'Return', 0x01000005: 'KP_Enter', 0x01000006: 'Insert',
    0x01000007: 'Delete', 0x01000008: 'Pause', 0x01000009: 'Print',
    0x0100000a: 'Sys_Req',
    0x01000010: 'Home', 0x01000011: 'End',
    0x01000012: 'Left', 0x01000013: 'Up', 0x01000014: 'Right', 0x01000015: 'Down',
    0x01000016: 'Page_Up', 0x01000017: 'Page_Down',
    0x01000020: 'Shift_L', 0x01000021: 'Control_L', 0x01000022: 'Meta_L',
    0x01000023: 'Alt_L', 0x01000024: 'Caps_Lock', 0x01000025: 'Num_Lock',
    0x01000026: 'Scroll_Lock',
    0x01000030: 'F1', 0x01000031: 'F2', 0x01000032: 'F3', 0x01000033: 'F4',
    0x01000034: 'F5', 0x01000035: 'F6', 0x01000036: 'F7', 0x01000037: 'F8',
    0x01000038: 'F9', 0x01000039: 'F10', 0x0100003a: 'F11', 0x0100003b: 'F12',
    0x0100003c: 'F13', 0x0100003d: 'F14', 0x0100003e: 'F15', 0x0100003f: 'F16',
    0x01000040: 'F17', 0x01000041: 'F18', 0x01000042: 'F19', 0x01000043: 'F20',
    0x01000044: 'F21', 0x01000045: 'F22', 0x01000046: 'F23', 0x01000047: 'F24',
    0x01000058: 'Super_L', 0x01000059: 'Super_R',
    0x01000055: 'Menu',
    0x01000056: 'Hyper_L', 0x01000057: 'Hyper_R',
    0x20: 'space',
}


# When the KeypadModifier flag is set (bit 0x10 in wire modifiers), Qt
# digit/symbol keys should resolve to numpad keysyms instead of the main
# row equivalents. Qt.Key_Enter is already handled above.
KEYPAD_REMAP = {
    0x30: 'KP_0', 0x31: 'KP_1', 0x32: 'KP_2', 0x33: 'KP_3', 0x34: 'KP_4',
    0x35: 'KP_5', 0x36: 'KP_6', 0x37: 'KP_7', 0x38: 'KP_8', 0x39: 'KP_9',
    0x2a: 'KP_Multiply', 0x2b: 'KP_Add', 0x2c: 'KP_Separator',
    0x2d: 'KP_Subtract', 0x2e: 'KP_Decimal', 0x2f: 'KP_Divide',
    0x3d: 'KP_Equal',
}


class XTestInputInjector:
    """Input injector using X11 XTest extension for Xvfb/Xorg displays.

    Can optionally hold a uinput VirtualPenTablet so that pen events with
    pressure/tilt/rotation reach Xorg as proper XInput2 tablet events.
    Mouse and keyboard still go through XTest, which is fast and works
    without needing any physical or uinput input devices to be hot-plugged.
    """

    def __init__(self, display_name: str, screen_width: int = 1920, screen_height: int = 1080,
                 pen_tablet=None):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self._display_name = display_name
        self._pen_tablet = pen_tablet

        if not XLIB_AVAILABLE:
            raise RuntimeError("python-xlib required for XTest input injection")

        self._dpy = xdisplay.Display(display_name)
        # Verify XTest extension
        if not self._dpy.has_extension('XTEST'):
            raise RuntimeError(f"XTest extension not available on {display_name}")

        self._root = self._dpy.screen().root
        self.reset_modifiers()
        logger.info("XTest input injector ready on %s (%dx%d)%s",
                     display_name, screen_width, screen_height,
                     " + uinput pen tablet" if pen_tablet else "")

    def reset_modifiers(self):
        """Release all modifier keys to prevent stuck state."""
        modifier_keysyms = [
            'Shift_L', 'Shift_R', 'Control_L', 'Control_R',
            'Alt_L', 'Alt_R', 'Super_L', 'Super_R',
            'Meta_L', 'Meta_R', 'Caps_Lock', 'Num_Lock',
        ]
        for name in modifier_keysyms:
            keysym = string_to_keysym(name)
            if keysym:
                keycode = self._dpy.keysym_to_keycode(keysym)
                if keycode:
                    xtest.fake_input(self._dpy, X.KeyRelease, detail=keycode)
        self._dpy.sync()
        logger.debug("All modifier keys released")

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

    def key(self, qt_key: int, pressed: bool, modifiers: int = 0):
        """Press/release a key by Qt key code."""
        keycode = self._qt_key_to_keycode(qt_key, modifiers)
        action = "PRESS" if pressed else "RELEASE"
        if keycode:
            event_type = X.KeyPress if pressed else X.KeyRelease
            xtest.fake_input(self._dpy, event_type, detail=keycode)
            self._dpy.sync()
            keysym_name = QT_TO_XKEYSYM.get(qt_key, chr(qt_key) if 0x20 <= qt_key <= 0x7e else "?")
            logger.info("KEY %s qt=0x%x → x11_keycode=%d (%s)", action, qt_key, keycode, keysym_name)
        else:
            logger.warning("KEY %s qt=0x%x → NO KEYCODE (unmapped)", action, qt_key)

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
        """Pen/stylus move. Routes through uinput tablet if available."""
        if self._pen_tablet is not None:
            # Hover move — no tip touch, no button
            self._pen_tablet.pen_event(
                x=x_norm, y=y_norm, pressure=pressure,
                pressed=pressure > 0.0, hovering=pressure <= 0.0)
        else:
            self.move_abs(x_norm, y_norm)

    def pen_button(self, button: int, pressed: bool):
        """Pen button — mapped to mouse button when no uinput tablet."""
        if self._pen_tablet is None:
            self.button(button, pressed)

    def _qt_key_to_keycode(self, qt_key: int, modifiers: int = 0) -> Optional[int]:
        """Convert Qt key code to X11 keycode."""
        # Numpad-origin keys: remap to KP_* keysyms when the client marked
        # the event as coming from the keypad.
        if modifiers & 0x10:
            kp_name = KEYPAD_REMAP.get(qt_key)
            if kp_name:
                keysym = string_to_keysym(kp_name)
                if keysym:
                    kc = self._dpy.keysym_to_keycode(keysym)
                    if kc:
                        return kc

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
            self.key(msg["scan_code"], msg["pressed"], msg.get("modifiers", 0))

        elif msg_type == "pen_event":
            # Diagnostic: log first event + one per 60 to confirm the path
            self._pen_msg_count = getattr(self, "_pen_msg_count", 0) + 1
            if self._pen_msg_count == 1 or self._pen_msg_count % 60 == 0:
                logger.info("PEN #%d x=%.3f y=%.3f p=%.3f tx=%.1f ty=%.1f "
                            "pressed=%s hover=%s type=%s via=%s",
                            self._pen_msg_count, msg.get("x", 0), msg.get("y", 0),
                            msg.get("pressure", 0.0),
                            msg.get("tilt_x", 0.0), msg.get("tilt_y", 0.0),
                            msg.get("pressed", False), msg.get("hovering", False),
                            msg.get("pen_type", "pen"),
                            "uinput" if self._pen_tablet else "xtest")
            if self._pen_tablet is not None:
                # Full pressure/tilt/rotation path via uinput
                self._pen_tablet.pen_event(
                    x=msg["x"],
                    y=msg["y"],
                    pressure=msg.get("pressure", 0.0),
                    tilt_x=msg.get("tilt_x", 0.0),
                    tilt_y=msg.get("tilt_y", 0.0),
                    rotation=msg.get("rotation", 0.0),
                    button=msg.get("button", 0),
                    pressed=msg.get("pressed", False),
                    hovering=msg.get("hovering", False),
                    pen_type=msg.get("pen_type", "pen"),
                )
            else:
                self.pen_move(msg["x"], msg["y"], msg.get("pressure", 0.0))
                if msg.get("button", 0) and "pressed" in msg:
                    self.pen_button(msg["button"], msg["pressed"])

    def close(self):
        if self._dpy:
            self._dpy.close()
            self._dpy = None
