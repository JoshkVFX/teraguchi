"""
Teragucci Protocol Message Definitions

All control messages are JSON over WebSocket text frames.
Screen frame data is sent as binary WebSocket frames with a small header.

Binary frame format:
  [1 byte: frame type] [4 bytes: x uint16 BE, y uint16 BE] [4 bytes: w uint16 BE, h uint16 BE] [JPEG data]

Frame types:
  0x01 = full frame
  0x02 = partial/dirty-rect update
"""

import json
import struct
from enum import IntEnum, auto
from dataclasses import dataclass, asdict, field
from typing import Optional


# --- Binary frame constants ---

class FrameType(IntEnum):
    FULL = 0x01
    PARTIAL = 0x02


FRAME_HEADER_SIZE = 9  # 1 + 2 + 2 + 2 + 2


def encode_frame_header(frame_type: FrameType, x: int, y: int, w: int, h: int) -> bytes:
    return struct.pack("!BHHHH", frame_type, x, y, w, h)


def decode_frame_header(data: bytes) -> tuple:
    """Returns (frame_type, x, y, w, h, jpeg_data)"""
    frame_type, x, y, w, h = struct.unpack("!BHHHH", data[:FRAME_HEADER_SIZE])
    return FrameType(frame_type), x, y, w, h, data[FRAME_HEADER_SIZE:]


# --- JSON control messages ---

class MsgType:
    # Client -> Server
    MOUSE_MOVE = "mouse_move"
    MOUSE_BUTTON = "mouse_button"
    MOUSE_SCROLL = "mouse_scroll"
    KEY_EVENT = "key_event"
    PEN_EVENT = "pen_event"
    CLIENT_HELLO = "client_hello"
    REQUEST_FULL_FRAME = "request_full_frame"
    CLIPBOARD_SEND = "clipboard_send"

    # Server -> Client
    SERVER_HELLO = "server_hello"
    CURSOR_UPDATE = "cursor_update"
    CLIPBOARD_RECV = "clipboard_recv"


@dataclass
class MouseMoveMsg:
    type: str = MsgType.MOUSE_MOVE
    x: float = 0.0  # Normalized 0.0-1.0 relative to screen
    y: float = 0.0

    def to_json(self) -> str:
        return json.dumps(asdict(self))


@dataclass
class MouseButtonMsg:
    type: str = MsgType.MOUSE_BUTTON
    button: int = 1  # 1=left, 2=middle, 3=right
    pressed: bool = True
    x: float = 0.0
    y: float = 0.0

    def to_json(self) -> str:
        return json.dumps(asdict(self))


@dataclass
class MouseScrollMsg:
    type: str = MsgType.MOUSE_SCROLL
    dx: int = 0
    dy: int = 0
    x: float = 0.0
    y: float = 0.0

    def to_json(self) -> str:
        return json.dumps(asdict(self))


@dataclass
class KeyEventMsg:
    type: str = MsgType.KEY_EVENT
    key: str = ""        # Qt key name or X11 keysym name
    scan_code: int = 0   # Platform scan code
    pressed: bool = True
    modifiers: int = 0   # Bitmask: 1=shift, 2=ctrl, 4=alt, 8=meta

    def to_json(self) -> str:
        return json.dumps(asdict(self))


@dataclass
class PenEventMsg:
    """Pen/stylus event with full tablet data."""
    type: str = MsgType.PEN_EVENT
    x: float = 0.0           # Normalized 0.0-1.0
    y: float = 0.0
    pressure: float = 0.0    # 0.0-1.0
    tilt_x: float = 0.0      # -90 to 90 degrees
    tilt_y: float = 0.0      # -90 to 90 degrees
    rotation: float = 0.0    # 0-360 degrees
    button: int = 0           # 0=none, 1=tip, 2=eraser, 3=barrel button
    pressed: bool = False     # Tip touching surface
    hovering: bool = False    # Pen in proximity but not touching
    pen_type: str = "pen"     # "pen", "eraser", "cursor"

    def to_json(self) -> str:
        return json.dumps(asdict(self))


@dataclass
class ClientHelloMsg:
    type: str = MsgType.CLIENT_HELLO
    client_name: str = "Teragucci Client"
    version: str = "1.0.0"
    screen_width: int = 1920
    screen_height: int = 1080

    def to_json(self) -> str:
        return json.dumps(asdict(self))


@dataclass
class ServerHelloMsg:
    type: str = MsgType.SERVER_HELLO
    server_name: str = "Teragucci Server"
    version: str = "1.0.0"
    screen_width: int = 1920
    screen_height: int = 1080
    supports_pen: bool = True

    def to_json(self) -> str:
        return json.dumps(asdict(self))


def parse_message(json_str: str) -> dict:
    """Parse a JSON control message and return as dict."""
    return json.loads(json_str)
