"""
Key mapping from Qt key names to Linux scan codes.

Qt sends key names (from QKeyEvent.key()), and we need to convert
them to Linux evdev scan codes for uinput injection.
"""

# Mapping from Qt key enum values to Linux evdev scan codes
# Qt key values -> Linux KEY_* codes (from linux/input-event-codes.h)
QT_KEY_TO_LINUX = {
    # Letters
    0x41: 30,   # Key_A -> KEY_A
    0x42: 48,   # Key_B -> KEY_B
    0x43: 46,   # Key_C -> KEY_C
    0x44: 32,   # Key_D -> KEY_D
    0x45: 18,   # Key_E -> KEY_E
    0x46: 33,   # Key_F -> KEY_F
    0x47: 34,   # Key_G -> KEY_G
    0x48: 35,   # Key_H -> KEY_H
    0x49: 23,   # Key_I -> KEY_I
    0x4A: 36,   # Key_J -> KEY_J
    0x4B: 37,   # Key_K -> KEY_K
    0x4C: 38,   # Key_L -> KEY_L
    0x4D: 50,   # Key_M -> KEY_M
    0x4E: 49,   # Key_N -> KEY_N
    0x4F: 24,   # Key_O -> KEY_O
    0x50: 25,   # Key_P -> KEY_P
    0x51: 16,   # Key_Q -> KEY_Q
    0x52: 19,   # Key_R -> KEY_R
    0x53: 31,   # Key_S -> KEY_S
    0x54: 20,   # Key_T -> KEY_T
    0x55: 22,   # Key_U -> KEY_U
    0x56: 47,   # Key_V -> KEY_V
    0x57: 17,   # Key_W -> KEY_W
    0x58: 45,   # Key_X -> KEY_X
    0x59: 21,   # Key_Y -> KEY_Y
    0x5A: 44,   # Key_Z -> KEY_Z

    # Numbers
    0x30: 11,   # Key_0 -> KEY_0
    0x31: 2,    # Key_1 -> KEY_1
    0x32: 3,    # Key_2 -> KEY_2
    0x33: 4,    # Key_3 -> KEY_3
    0x34: 5,    # Key_4 -> KEY_4
    0x35: 6,    # Key_5 -> KEY_5
    0x36: 7,    # Key_6 -> KEY_6
    0x37: 8,    # Key_7 -> KEY_7
    0x38: 9,    # Key_8 -> KEY_8
    0x39: 10,   # Key_9 -> KEY_9

    # Function keys
    0x01000030: 59,   # Key_F1
    0x01000031: 60,   # Key_F2
    0x01000032: 61,   # Key_F3
    0x01000033: 62,   # Key_F4
    0x01000034: 63,   # Key_F5
    0x01000035: 64,   # Key_F6
    0x01000036: 65,   # Key_F7
    0x01000037: 66,   # Key_F8
    0x01000038: 67,   # Key_F9
    0x01000039: 68,   # Key_F10
    0x0100003a: 87,   # Key_F11
    0x0100003b: 88,   # Key_F12

    # Modifiers
    0x01000020: 42,   # Key_Shift -> KEY_LEFTSHIFT
    0x01000021: 29,   # Key_Control -> KEY_LEFTCTRL
    0x01000023: 56,   # Key_Alt -> KEY_LEFTALT
    0x01000022: 125,  # Key_Meta -> KEY_LEFTMETA (Super/Windows)

    # Navigation
    0x01000013: 103,  # Key_Up -> KEY_UP
    0x01000015: 108,  # Key_Down -> KEY_DOWN
    0x01000012: 105,  # Key_Left -> KEY_LEFT
    0x01000014: 106,  # Key_Right -> KEY_RIGHT
    0x01000010: 102,  # Key_Home -> KEY_HOME
    0x01000011: 107,  # Key_End -> KEY_END
    0x01000016: 104,  # Key_PageUp -> KEY_PAGEUP
    0x01000017: 109,  # Key_PageDown -> KEY_PAGEDOWN

    # Editing
    0x01000003: 14,   # Key_Backspace -> KEY_BACKSPACE
    0x01000007: 111,  # Key_Delete -> KEY_DELETE
    0x01000004: 28,   # Key_Return -> KEY_ENTER
    0x01000005: 28,   # Key_Enter -> KEY_ENTER
    0x01000001: 1,    # Key_Escape -> KEY_ESC
    0x01000000: 15,   # Key_Tab -> KEY_TAB
    0x01000006: 110,  # Key_Insert -> KEY_INSERT

    # Symbols
    0x20: 57,         # Key_Space -> KEY_SPACE
    0x2D: 12,         # Key_Minus -> KEY_MINUS
    0x3D: 13,         # Key_Equal -> KEY_EQUAL
    0x5B: 26,         # Key_BracketLeft -> KEY_LEFTBRACE
    0x5D: 27,         # Key_BracketRight -> KEY_RIGHTBRACE
    0x5C: 43,         # Key_Backslash -> KEY_BACKSLASH
    0x3B: 39,         # Key_Semicolon -> KEY_SEMICOLON
    0x27: 40,         # Key_Apostrophe -> KEY_APOSTROPHE
    0x60: 41,         # Key_QuoteLeft (backtick) -> KEY_GRAVE
    0x2C: 51,         # Key_Comma -> KEY_COMMA
    0x2E: 52,         # Key_Period -> KEY_DOT
    0x2F: 53,         # Key_Slash -> KEY_SLASH

    # Lock keys
    0x01000024: 58,   # Key_CapsLock -> KEY_CAPSLOCK
    0x01000025: 69,   # Key_NumLock -> KEY_NUMLOCK
    0x01000026: 70,   # Key_ScrollLock -> KEY_SCROLLLOCK

    # Print/Pause
    0x01000009: 99,   # Key_Print -> KEY_SYSRQ
    0x01000008: 119,  # Key_Pause -> KEY_PAUSE
}


def qt_key_to_linux_scancode(qt_key: int) -> int:
    """Convert a Qt key enum value to a Linux evdev scan code.

    Returns 0 if no mapping exists.
    """
    return QT_KEY_TO_LINUX.get(qt_key, 0)
