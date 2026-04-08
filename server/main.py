#!/usr/bin/env python3
"""
Teragucci Server - Linux Remote Desktop Server

Captures the screen, streams it to connected clients via WebSocket,
and injects received input events (mouse, keyboard, pen/tablet with pressure).

Usage:
    python -m server.main [--host HOST] [--port PORT] [--quality QUALITY] [--fps FPS]
"""

import asyncio
import argparse
import json
import logging
import signal
import sys
import time
from typing import Set

import websockets
from websockets.server import WebSocketServerProtocol

sys.path.insert(0, ".")
from common.messages import (
    MsgType, ServerHelloMsg, FrameType,
    encode_frame_header, parse_message,
)
from common.keymap import qt_key_to_linux_scancode
from server.screen_capture import ScreenCapture
from server.input_injector import InputInjector

logger = logging.getLogger("teragucci.server")

# Global state
clients: Set[WebSocketServerProtocol] = set()
capture: ScreenCapture = None
injector: InputInjector = None
running = True


async def handle_client(websocket: WebSocketServerProtocol):
    """Handle a single client connection."""
    client_addr = websocket.remote_address
    logger.info("Client connected: %s", client_addr)
    clients.add(websocket)

    try:
        # Send server hello
        hello = ServerHelloMsg(
            screen_width=capture.width,
            screen_height=capture.height,
            supports_pen=True,
        )
        await websocket.send(hello.to_json())

        # Send initial full frame
        full_frame = capture.capture_full_frame()
        header = encode_frame_header(FrameType.FULL, 0, 0, capture.width, capture.height)
        await websocket.send(header + full_frame)

        # Process incoming messages (input events)
        async for message in websocket:
            if isinstance(message, str):
                try:
                    msg = parse_message(message)
                    _handle_input(msg)
                except json.JSONDecodeError:
                    logger.warning("Invalid JSON from %s", client_addr)
                except Exception as e:
                    logger.error("Error handling input from %s: %s", client_addr, e)

    except websockets.exceptions.ConnectionClosed:
        logger.info("Client disconnected: %s", client_addr)
    except Exception as e:
        logger.error("Client error %s: %s", client_addr, e)
    finally:
        clients.discard(websocket)
        logger.info("Client removed: %s (total: %d)", client_addr, len(clients))


def _handle_input(msg: dict):
    """Route input messages to the injector, with key mapping."""
    msg_type = msg.get("type")

    # For keyboard events, translate Qt key codes to Linux scan codes
    if msg_type == MsgType.KEY_EVENT:
        qt_key = msg.get("scan_code", 0)
        linux_code = qt_key_to_linux_scancode(qt_key)
        if linux_code == 0:
            logger.debug("Unmapped Qt key: 0x%x", qt_key)
            return
        msg["scan_code"] = linux_code

    elif msg_type == MsgType.REQUEST_FULL_FRAME:
        capture.invalidate()
        return

    injector.handle_message(msg)


async def stream_frames(fps: int):
    """Continuously capture screen and broadcast dirty regions to all clients."""
    frame_interval = 1.0 / fps
    frame_count = 0
    last_log_time = time.time()

    while running:
        start = time.time()

        if clients:
            try:
                regions = capture.capture_dirty_regions()

                for x, y, w, h, jpeg_data in regions:
                    frame_type = FrameType.FULL if (x == 0 and y == 0 and
                                 w == capture.width and h == capture.height) else FrameType.PARTIAL
                    header = encode_frame_header(frame_type, x, y, w, h)
                    data = header + jpeg_data

                    # Broadcast to all clients
                    disconnected = set()
                    for ws in clients.copy():
                        try:
                            await ws.send(data)
                        except websockets.exceptions.ConnectionClosed:
                            disconnected.add(ws)
                    clients.difference_update(disconnected)

                frame_count += 1
            except Exception as e:
                logger.error("Frame capture error: %s", e)

        # FPS logging
        now = time.time()
        if now - last_log_time >= 10.0:
            actual_fps = frame_count / (now - last_log_time)
            logger.debug("Streaming at %.1f fps to %d clients", actual_fps, len(clients))
            frame_count = 0
            last_log_time = now

        # Maintain target frame rate
        elapsed = time.time() - start
        sleep_time = frame_interval - elapsed
        if sleep_time > 0:
            await asyncio.sleep(sleep_time)
        else:
            await asyncio.sleep(0.001)  # Yield to event loop


async def run_server(host: str, port: int, fps: int):
    """Start the WebSocket server and frame streaming."""
    global running

    logger.info("Starting Teragucci server on %s:%d (target %d fps)", host, port, fps)

    # Start the frame streaming task
    stream_task = asyncio.create_task(stream_frames(fps))

    # Start the WebSocket server
    stop = asyncio.Future()

    def signal_handler():
        nonlocal running
        running = False
        if not stop.done():
            stop.set_result(None)

    loop = asyncio.get_event_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)

    async with websockets.serve(handle_client, host, port,
                                max_size=50 * 1024 * 1024,  # 50MB max message
                                ping_interval=20,
                                ping_timeout=30):
        logger.info("Server ready. Waiting for connections...")
        await stop

    running = False
    stream_task.cancel()
    try:
        await stream_task
    except asyncio.CancelledError:
        pass

    logger.info("Server stopped")


def main():
    parser = argparse.ArgumentParser(description="Teragucci Remote Desktop Server")
    parser.add_argument("--host", default="0.0.0.0",
                        help="Listen address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=9876,
                        help="Listen port (default: 9876)")
    parser.add_argument("--fps", type=int, default=30,
                        help="Target frame rate (default: 30)")
    parser.add_argument("--quality", type=int, default=60,
                        help="JPEG quality 1-100 (default: 60)")
    parser.add_argument("--monitor", type=int, default=1,
                        help="Monitor index (default: 1 = primary)")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Enable debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    global capture, injector

    try:
        capture = ScreenCapture(
            monitor_index=args.monitor,
            jpeg_quality=args.quality,
        )
        injector = InputInjector(
            screen_width=capture.width,
            screen_height=capture.height,
        )
    except Exception as e:
        logger.error("Failed to initialize: %s", e)
        logger.error("Make sure you have access to /dev/uinput and a display.")
        logger.error("Run with: sudo python -m server.main")
        sys.exit(1)

    try:
        asyncio.run(run_server(args.host, args.port, args.fps))
    except KeyboardInterrupt:
        logger.info("Interrupted")
    finally:
        if injector:
            injector.close()
        if capture:
            capture.close()


if __name__ == "__main__":
    main()
