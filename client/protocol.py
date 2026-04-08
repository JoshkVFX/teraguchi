"""
Client-side WebSocket protocol handler.

Manages the connection to the Teragucci server, sends input events,
and receives screen frames. Runs the WebSocket I/O on a background thread
to keep the Qt GUI responsive.
"""

import json
import logging
import threading
import asyncio
from typing import Optional, Callable

import websockets

from common.messages import (
    MsgType, ClientHelloMsg, FrameType,
    decode_frame_header, FRAME_HEADER_SIZE,
)

logger = logging.getLogger(__name__)


class ClientProtocol:
    """
    WebSocket client that communicates with the Teragucci server.

    Runs an asyncio event loop in a background thread for non-blocking I/O.
    Provides thread-safe methods for sending messages from the Qt GUI thread.
    """

    def __init__(self):
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._connected = False
        self._closing = False

        # Callbacks (called from the background thread - must be thread-safe)
        self.on_server_hello: Optional[Callable] = None    # (msg_dict)
        self.on_full_frame: Optional[Callable] = None      # (jpeg_bytes)
        self.on_partial_frame: Optional[Callable] = None   # (x, y, w, h, jpeg_bytes)
        self.on_connected: Optional[Callable] = None       # ()
        self.on_disconnected: Optional[Callable] = None    # (reason: str)
        self.on_error: Optional[Callable] = None           # (error: str)

    @property
    def connected(self) -> bool:
        return self._connected

    def connect(self, host: str, port: int):
        """Start connecting to the server (non-blocking, launches background thread)."""
        if self._thread and self._thread.is_alive():
            logger.warning("Already connected or connecting")
            return

        self._closing = False
        self._thread = threading.Thread(
            target=self._run_loop,
            args=(host, port),
            daemon=True,
            name="teragucci-client-io",
        )
        self._thread.start()

    def disconnect(self):
        """Disconnect from the server."""
        self._closing = True
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread:
            self._thread.join(timeout=3.0)
            self._thread = None
        self._connected = False

    def send_input(self, msg_dict: dict):
        """Send an input message to the server (thread-safe)."""
        if not self._connected or not self._ws:
            return
        try:
            json_str = json.dumps(msg_dict)
            if self._loop and self._loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    self._ws.send(json_str), self._loop
                )
        except Exception as e:
            logger.error("Failed to send input: %s", e)

    def request_full_frame(self):
        """Request a full frame refresh from the server."""
        self.send_input({"type": MsgType.REQUEST_FULL_FRAME})

    def _run_loop(self, host: str, port: int):
        """Background thread: run the asyncio event loop."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._connect_and_receive(host, port))
        except Exception as e:
            if not self._closing:
                logger.error("Connection error: %s", e)
                if self.on_error:
                    self.on_error(str(e))
        finally:
            self._connected = False
            if self.on_disconnected and not self._closing:
                self.on_disconnected("Connection closed")
            self._loop.close()
            self._loop = None

    async def _connect_and_receive(self, host: str, port: int):
        """Connect to the server and process incoming messages."""
        uri = f"ws://{host}:{port}"
        logger.info("Connecting to %s", uri)

        async with websockets.connect(
            uri,
            max_size=50 * 1024 * 1024,  # 50MB
            ping_interval=20,
            ping_timeout=30,
        ) as ws:
            self._ws = ws
            self._connected = True
            logger.info("Connected to server")

            if self.on_connected:
                self.on_connected()

            # Send client hello
            hello = ClientHelloMsg()
            await ws.send(hello.to_json())

            # Receive loop
            async for message in ws:
                if self._closing:
                    break

                if isinstance(message, str):
                    # JSON control message
                    self._handle_json_message(message)
                elif isinstance(message, bytes):
                    # Binary frame data
                    self._handle_binary_frame(message)

    def _handle_json_message(self, data: str):
        """Process a JSON message from the server."""
        try:
            msg = json.loads(data)
            msg_type = msg.get("type")

            if msg_type == MsgType.SERVER_HELLO:
                logger.info("Server hello: %s", msg)
                if self.on_server_hello:
                    self.on_server_hello(msg)

            elif msg_type == MsgType.CLIPBOARD_RECV:
                # TODO: clipboard support
                pass

        except json.JSONDecodeError:
            logger.warning("Invalid JSON from server")

    def _handle_binary_frame(self, data: bytes):
        """Process a binary screen frame from the server."""
        if len(data) < FRAME_HEADER_SIZE:
            logger.warning("Frame too small: %d bytes", len(data))
            return

        frame_type, x, y, w, h, jpeg_data = decode_frame_header(data)

        if frame_type == FrameType.FULL:
            if self.on_full_frame:
                self.on_full_frame(jpeg_data)
        elif frame_type == FrameType.PARTIAL:
            if self.on_partial_frame:
                self.on_partial_frame(x, y, w, h, jpeg_data)
