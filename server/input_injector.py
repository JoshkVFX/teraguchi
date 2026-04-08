"""
Input injection module for Linux.

Creates virtual input devices via uinput:
- Virtual mouse (relative + absolute positioning)
- Virtual keyboard
- Virtual pen tablet (with pressure, tilt, and button support)

This allows injecting mouse, keyboard, and Wacom-style pen events
into the Linux input subsystem, which X11/Wayland will pick up.
"""

import logging
import struct
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)

# Linux input event constants (from linux/input.h)
# Event types
EV_SYN = 0x00
EV_KEY = 0x01
EV_REL = 0x02
EV_ABS = 0x03
EV_MSC = 0x04

# Sync events
SYN_REPORT = 0x00

# Relative axes
REL_X = 0x00
REL_Y = 0x01
REL_WHEEL = 0x08
REL_HWHEEL = 0x06

# Absolute axes
ABS_X = 0x00
ABS_Y = 0x01
ABS_Z = 0x02
ABS_PRESSURE = 0x18
ABS_TILT_X = 0x1a
ABS_TILT_Y = 0x1b
ABS_MISC = 0x28

# Mouse buttons
BTN_LEFT = 0x110
BTN_RIGHT = 0x111
BTN_MIDDLE = 0x112

# Pen buttons
BTN_TOOL_PEN = 0x140
BTN_TOOL_RUBBER = 0x141
BTN_TOOL_BRUSH = 0x142
BTN_TOOL_PENCIL = 0x143
BTN_TOUCH = 0x14a
BTN_STYLUS = 0x14b
BTN_STYLUS2 = 0x14c

# MSC
MSC_SERIAL = 0x00

# uinput ioctl numbers
UINPUT_IOCTL_BASE = ord('U')

# The input_event struct format: time_sec(L), time_usec(L), type(H), code(H), value(i)
INPUT_EVENT_FORMAT = 'llHHi'
INPUT_EVENT_SIZE = struct.calcsize(INPUT_EVENT_FORMAT)

# uinput_user_dev struct: name(80s), input_id(4H), ff_effects_max(I), absmax(64i), absmin(64i), absfuzz(64i), absflat(64i)
UINPUT_USER_DEV_FORMAT = '80sHHHHI' + 'i' * 64 * 4
UINPUT_USER_DEV_SIZE = struct.calcsize(UINPUT_USER_DEV_FORMAT)

# ioctl helpers
import fcntl

UI_SET_EVBIT = 0x40045564   # _IOW('U', 100, int)
UI_SET_KEYBIT = 0x40045565  # _IOW('U', 101, int)
UI_SET_RELBIT = 0x40045566  # _IOW('U', 102, int)
UI_SET_ABSBIT = 0x40045567  # _IOW('U', 103, int)
UI_SET_MSCBIT = 0x40045568  # _IOW('U', 104, int)
UI_DEV_CREATE = 0x5501       # _IO('U', 1)
UI_DEV_DESTROY = 0x5502      # _IO('U', 2)

# For setting abs parameters via UI_ABS_SETUP
UI_ABS_SETUP = 0x401c5504   # _IOW('U', 4, struct uinput_abs_setup)

# uinput_abs_setup: code(H), pad(H), absinfo(6i) = minimum, maximum, fuzz, flat, resolution, pad
UINPUT_ABS_SETUP_FORMAT = 'HH6i'

# Maximum values for pen coordinates
PEN_MAX_X = 65535
PEN_MAX_Y = 65535
PEN_MAX_PRESSURE = 8191  # Wacom typically uses 8192 levels (0-8191)
PEN_MAX_TILT = 127       # -127 to 127


def _ioctl_set(fd, request, value):
    """Perform an ioctl to set a bit."""
    fcntl.ioctl(fd, request, value)


def _write_event(fd, ev_type, code, value):
    """Write a single input event to the uinput device."""
    t = time.time()
    sec = int(t)
    usec = int((t - sec) * 1000000)
    data = struct.pack(INPUT_EVENT_FORMAT, sec, usec, ev_type, code, value)
    os.write(fd, data)


def _setup_abs(fd, code, minimum, maximum, fuzz=0, flat=0, resolution=0):
    """Set up an absolute axis using UI_ABS_SETUP ioctl."""
    data = struct.pack(UINPUT_ABS_SETUP_FORMAT,
                       code, 0,  # code + padding
                       0, minimum, maximum, fuzz, flat, resolution)
    fcntl.ioctl(fd, UI_ABS_SETUP, data)


class VirtualMouse:
    """Virtual mouse device using uinput."""

    def __init__(self, screen_width: int = 1920, screen_height: int = 1080):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self._fd = None
        self._setup()

    def _setup(self):
        self._fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)

        # Enable event types
        _ioctl_set(self._fd, UI_SET_EVBIT, EV_KEY)
        _ioctl_set(self._fd, UI_SET_EVBIT, EV_ABS)
        _ioctl_set(self._fd, UI_SET_EVBIT, EV_REL)

        # Enable mouse buttons
        for btn in (BTN_LEFT, BTN_RIGHT, BTN_MIDDLE):
            _ioctl_set(self._fd, UI_SET_KEYBIT, btn)

        # Enable absolute positioning
        _ioctl_set(self._fd, UI_SET_ABSBIT, ABS_X)
        _ioctl_set(self._fd, UI_SET_ABSBIT, ABS_Y)

        # Enable relative for scroll
        _ioctl_set(self._fd, UI_SET_RELBIT, REL_WHEEL)
        _ioctl_set(self._fd, UI_SET_RELBIT, REL_HWHEEL)

        # Setup abs ranges
        _setup_abs(self._fd, ABS_X, 0, self.screen_width - 1, resolution=1)
        _setup_abs(self._fd, ABS_Y, 0, self.screen_height - 1, resolution=1)

        # Create the device
        name = b"Teragucci Virtual Mouse"
        dev_data = struct.pack('80sHHHHI',
                               name, 0x03, 0x01, 0x01, 0x01, 0)
        # Pad with zeros for abs arrays
        dev_data += b'\x00' * (64 * 4 * 4)  # absmax, absmin, absfuzz, absflat
        os.write(self._fd, dev_data[:UINPUT_USER_DEV_SIZE])
        fcntl.ioctl(self._fd, UI_DEV_CREATE)
        time.sleep(0.2)  # Give kernel time to register device
        logger.info("Virtual mouse created")

    def move_abs(self, x: float, y: float):
        """Move mouse to absolute position. x, y are normalized 0.0-1.0."""
        abs_x = int(x * (self.screen_width - 1))
        abs_y = int(y * (self.screen_height - 1))
        _write_event(self._fd, EV_ABS, ABS_X, abs_x)
        _write_event(self._fd, EV_ABS, ABS_Y, abs_y)
        _write_event(self._fd, EV_SYN, SYN_REPORT, 0)

    def button(self, button: int, pressed: bool):
        """Press/release a mouse button. button: 1=left, 2=middle, 3=right."""
        btn_map = {1: BTN_LEFT, 2: BTN_MIDDLE, 3: BTN_RIGHT}
        btn_code = btn_map.get(button, BTN_LEFT)
        _write_event(self._fd, EV_KEY, btn_code, 1 if pressed else 0)
        _write_event(self._fd, EV_SYN, SYN_REPORT, 0)

    def scroll(self, dx: int, dy: int):
        """Scroll wheel. dy>0 = up, dy<0 = down."""
        if dy != 0:
            _write_event(self._fd, EV_REL, REL_WHEEL, dy)
        if dx != 0:
            _write_event(self._fd, EV_REL, REL_HWHEEL, dx)
        _write_event(self._fd, EV_SYN, SYN_REPORT, 0)

    def close(self):
        if self._fd is not None:
            try:
                fcntl.ioctl(self._fd, UI_DEV_DESTROY)
            except Exception:
                pass
            os.close(self._fd)
            self._fd = None
            logger.info("Virtual mouse destroyed")


class VirtualKeyboard:
    """Virtual keyboard device using uinput."""

    def __init__(self):
        self._fd = None
        self._setup()

    def _setup(self):
        self._fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)

        _ioctl_set(self._fd, UI_SET_EVBIT, EV_KEY)

        # Enable all standard keyboard keys (1-248)
        for key in range(1, 249):
            _ioctl_set(self._fd, UI_SET_KEYBIT, key)

        # Create the device
        name = b"Teragucci Virtual Keyboard"
        dev_data = struct.pack('80sHHHHI',
                               name, 0x03, 0x01, 0x01, 0x01, 0)
        dev_data += b'\x00' * (64 * 4 * 4)
        os.write(self._fd, dev_data[:UINPUT_USER_DEV_SIZE])
        fcntl.ioctl(self._fd, UI_DEV_CREATE)
        time.sleep(0.2)
        logger.info("Virtual keyboard created")

    def key_event(self, scan_code: int, pressed: bool):
        """Send a key press/release event by Linux scan code."""
        _write_event(self._fd, EV_KEY, scan_code, 1 if pressed else 0)
        _write_event(self._fd, EV_SYN, SYN_REPORT, 0)

    def close(self):
        if self._fd is not None:
            try:
                fcntl.ioctl(self._fd, UI_DEV_DESTROY)
            except Exception:
                pass
            os.close(self._fd)
            self._fd = None
            logger.info("Virtual keyboard destroyed")


class VirtualPenTablet:
    """
    Virtual Wacom-style pen tablet device using uinput.

    Supports:
    - Absolute X/Y positioning (full screen range)
    - Pressure sensitivity (0-8191, matching Wacom Pro)
    - Tilt X/Y (-127 to 127)
    - Pen tip, eraser, and barrel button events
    - Proximity (hover) detection
    """

    def __init__(self, screen_width: int = 1920, screen_height: int = 1080):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self._fd = None
        self._in_proximity = False
        self._setup()

    def _setup(self):
        self._fd = os.open("/dev/uinput", os.O_WRONLY | os.O_NONBLOCK)

        # Enable event types
        _ioctl_set(self._fd, UI_SET_EVBIT, EV_KEY)
        _ioctl_set(self._fd, UI_SET_EVBIT, EV_ABS)
        _ioctl_set(self._fd, UI_SET_EVBIT, EV_MSC)

        # Pen buttons
        for btn in (BTN_TOUCH, BTN_TOOL_PEN, BTN_TOOL_RUBBER, BTN_STYLUS, BTN_STYLUS2):
            _ioctl_set(self._fd, UI_SET_KEYBIT, btn)

        # Absolute axes
        for axis in (ABS_X, ABS_Y, ABS_PRESSURE, ABS_TILT_X, ABS_TILT_Y, ABS_MISC):
            _ioctl_set(self._fd, UI_SET_ABSBIT, axis)

        # MSC for serial
        _ioctl_set(self._fd, UI_SET_MSCBIT, MSC_SERIAL)

        # Setup absolute axis ranges
        _setup_abs(self._fd, ABS_X, 0, PEN_MAX_X, resolution=100)
        _setup_abs(self._fd, ABS_Y, 0, PEN_MAX_Y, resolution=100)
        _setup_abs(self._fd, ABS_PRESSURE, 0, PEN_MAX_PRESSURE)
        _setup_abs(self._fd, ABS_TILT_X, -PEN_MAX_TILT, PEN_MAX_TILT)
        _setup_abs(self._fd, ABS_TILT_Y, -PEN_MAX_TILT, PEN_MAX_TILT)
        _setup_abs(self._fd, ABS_MISC, 0, 0xFFFF)

        # Create the device - use Wacom-like vendor/product IDs
        name = b"Teragucci Virtual Pen Tablet"
        # Bus=0x03(USB), vendor=0x056a(Wacom), product=0x0001, version=0x0001
        dev_data = struct.pack('80sHHHHI',
                               name, 0x03, 0x056a, 0x0001, 0x0100, 0)
        dev_data += b'\x00' * (64 * 4 * 4)
        os.write(self._fd, dev_data[:UINPUT_USER_DEV_SIZE])
        fcntl.ioctl(self._fd, UI_DEV_CREATE)
        time.sleep(0.3)  # Tablet needs a bit more time
        logger.info("Virtual pen tablet created (%dx%d, %d pressure levels)",
                     PEN_MAX_X, PEN_MAX_Y, PEN_MAX_PRESSURE + 1)

    def pen_event(self, x: float, y: float, pressure: float,
                  tilt_x: float = 0.0, tilt_y: float = 0.0,
                  rotation: float = 0.0,
                  button: int = 0, pressed: bool = False,
                  hovering: bool = False, pen_type: str = "pen"):
        """
        Inject a pen/stylus event.

        Args:
            x, y: Normalized position (0.0-1.0)
            pressure: Normalized pressure (0.0-1.0)
            tilt_x, tilt_y: Tilt in degrees (-90 to 90)
            rotation: Rotation in degrees (0-360) - stored in ABS_MISC
            button: 0=none, 1=tip, 2=eraser, 3=barrel
            pressed: Whether pen tip is touching
            hovering: Whether pen is in proximity
            pen_type: "pen" or "eraser"
        """
        # Convert normalized values to device range
        abs_x = int(x * PEN_MAX_X)
        abs_y = int(y * PEN_MAX_Y)
        abs_pressure = int(pressure * PEN_MAX_PRESSURE)
        abs_tilt_x = int(max(-PEN_MAX_TILT, min(PEN_MAX_TILT,
                         tilt_x * PEN_MAX_TILT / 90.0)))
        abs_tilt_y = int(max(-PEN_MAX_TILT, min(PEN_MAX_TILT,
                         tilt_y * PEN_MAX_TILT / 90.0)))

        # Handle proximity enter/exit
        tool_btn = BTN_TOOL_RUBBER if pen_type == "eraser" else BTN_TOOL_PEN
        if hovering or pressed:
            if not self._in_proximity:
                _write_event(self._fd, EV_KEY, tool_btn, 1)
                self._in_proximity = True
        else:
            if self._in_proximity:
                _write_event(self._fd, EV_KEY, tool_btn, 0)
                _write_event(self._fd, EV_SYN, SYN_REPORT, 0)
                self._in_proximity = False
                return

        # Position
        _write_event(self._fd, EV_ABS, ABS_X, abs_x)
        _write_event(self._fd, EV_ABS, ABS_Y, abs_y)

        # Pressure
        _write_event(self._fd, EV_ABS, ABS_PRESSURE, abs_pressure)

        # Tilt
        _write_event(self._fd, EV_ABS, ABS_TILT_X, abs_tilt_x)
        _write_event(self._fd, EV_ABS, ABS_TILT_Y, abs_tilt_y)

        # Rotation via ABS_MISC (some apps read this)
        abs_misc = int(rotation * 65535 / 360.0)
        _write_event(self._fd, EV_ABS, ABS_MISC, abs_misc)

        # Tip touch
        _write_event(self._fd, EV_KEY, BTN_TOUCH, 1 if pressed else 0)

        # Barrel buttons
        if button == 3:  # barrel button
            _write_event(self._fd, EV_KEY, BTN_STYLUS, 1)
        else:
            _write_event(self._fd, EV_KEY, BTN_STYLUS, 0)

        # Serial number (helps identify as a proper tablet)
        _write_event(self._fd, EV_MSC, MSC_SERIAL, 0x12345678)

        # Sync
        _write_event(self._fd, EV_SYN, SYN_REPORT, 0)

    def close(self):
        if self._fd is not None:
            if self._in_proximity:
                _write_event(self._fd, EV_KEY, BTN_TOOL_PEN, 0)
                _write_event(self._fd, EV_SYN, SYN_REPORT, 0)
            try:
                fcntl.ioctl(self._fd, UI_DEV_DESTROY)
            except Exception:
                pass
            os.close(self._fd)
            self._fd = None
            logger.info("Virtual pen tablet destroyed")


class InputInjector:
    """
    Unified input injector that manages all virtual devices.
    """

    def __init__(self, screen_width: int = 1920, screen_height: int = 1080):
        self.screen_width = screen_width
        self.screen_height = screen_height
        self.mouse = VirtualMouse(screen_width, screen_height)
        self.keyboard = VirtualKeyboard()
        self.pen = VirtualPenTablet(screen_width, screen_height)
        logger.info("Input injector ready (all virtual devices created)")

    def handle_message(self, msg: dict):
        """Dispatch a parsed input message to the appropriate device."""
        msg_type = msg.get("type")

        if msg_type == "mouse_move":
            self.mouse.move_abs(msg["x"], msg["y"])

        elif msg_type == "mouse_button":
            self.mouse.move_abs(msg["x"], msg["y"])
            self.mouse.button(msg["button"], msg["pressed"])

        elif msg_type == "mouse_scroll":
            self.mouse.move_abs(msg["x"], msg["y"])
            self.mouse.scroll(msg.get("dx", 0), msg.get("dy", 0))

        elif msg_type == "key_event":
            self.keyboard.key_event(msg["scan_code"], msg["pressed"])

        elif msg_type == "pen_event":
            self.pen.pen_event(
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

    def close(self):
        self.mouse.close()
        self.keyboard.close()
        self.pen.close()
        logger.info("Input injector shut down")
