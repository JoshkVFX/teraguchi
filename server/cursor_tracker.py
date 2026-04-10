"""
XFixes-based cursor tracker for local-cursor rendering on the client.

Polls the X display's cursor shape via XFixesGetCursorImage and emits
serial-based updates so the client can draw the cursor locally with
zero latency. This is how PCoIP, RDP, VNC, and Parsec all work — only
the cursor *shape* crosses the network, never cursor *motion*.

Runs in its own thread with its own X display connection so XFixes
round-trips don't block the asyncio event loop and don't race with
the XTest injector's Display handle.
"""

from __future__ import annotations

import base64
import logging
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger(__name__)

try:
    from Xlib import display as xdisplay
    from Xlib.ext import xfixes  # noqa: F401 — registers xfixes_* methods
    XLIB_AVAILABLE = True
except ImportError:
    XLIB_AVAILABLE = False


class CursorTracker:
    """Polls X cursor shape via XFixes and invokes a callback on change.

    The callback runs on the tracker's own polling thread. Callers
    are responsible for marshalling the update to whatever transport
    they need (for teragucci, that's ``run_coroutine_threadsafe`` onto
    the asyncio loop that owns the WebSocket).

    ``latest()`` returns the most recent update so newly-connected
    clients can be brought up to date without waiting for the next
    shape change.
    """

    def __init__(self, display_name: str, poll_hz: float = 30.0):
        if not XLIB_AVAILABLE:
            raise RuntimeError("python-xlib required for CursorTracker")

        self._display_name = display_name
        self._interval = 1.0 / max(poll_hz, 1.0)
        self._dpy: Optional[xdisplay.Display] = None
        self._root = None
        self._last_serial: int = -1
        self._last_update: Optional[dict] = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._on_change: Optional[Callable[[dict], None]] = None

        self._open_display()

    def _open_display(self):
        self._dpy = xdisplay.Display(self._display_name)
        if not self._dpy.has_extension("XFIXES"):
            try:
                self._dpy.close()
            except Exception:
                pass
            self._dpy = None
            raise RuntimeError(
                f"XFixes extension not available on {self._display_name}")
        # Required handshake — some implementations refuse cursor
        # requests until the client has agreed on a version.
        self._dpy.xfixes_query_version()
        self._root = self._dpy.screen().root

    def start(self, on_change: Callable[[dict], None]):
        self._on_change = on_change
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name="cursor-tracker", daemon=True)
        self._thread.start()
        logger.info("Cursor tracker started on %s (%.0f Hz)",
                    self._display_name, 1.0 / self._interval)

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None
        if self._dpy is not None:
            try:
                self._dpy.close()
            except Exception:
                pass
            self._dpy = None

    def latest(self) -> Optional[dict]:
        """Most recent cursor update — useful for late-joining clients."""
        with self._lock:
            return self._last_update

    # ── Internals ────────────────────────────────────────────

    def _loop(self):
        while not self._stop.is_set():
            try:
                self._poll_once()
            except Exception as e:
                # Display went away (Xorg restart, session teardown) —
                # drop the connection and try to reopen. If that keeps
                # failing we just keep logging; the tracker is
                # decorative, it should never take the server with it.
                logger.warning("Cursor poll error: %s — reconnecting", e)
                try:
                    if self._dpy:
                        self._dpy.close()
                except Exception:
                    pass
                self._dpy = None
                time.sleep(1.0)
                try:
                    self._open_display()
                except Exception as e2:
                    logger.error("Cursor display reopen failed: %s", e2)
            self._stop.wait(self._interval)

    def _poll_once(self):
        if self._dpy is None:
            return
        reply = self._dpy.xfixes_get_cursor_image(self._root)
        serial = int(getattr(reply, "cursor_serial", 0)) & 0xFFFFFFFF
        if serial == self._last_serial:
            return

        width = int(reply.width)
        height = int(reply.height)
        if width <= 0 or height <= 0 or width > 256 or height > 256:
            # Sanity — cursors should fit comfortably in ~128px.
            logger.debug("Skipping absurd cursor shape %dx%d", width, height)
            return

        xhot = int(reply.xhot)
        yhot = int(reply.yhot)
        pixels = reply.cursor_image  # list of CARD32, ARGB premultiplied

        # Convert to RGBA8888 (R, G, B, A byte order). Premultiplied
        # alpha is preserved — the client renders with
        # QImage.Format_RGBA8888_Premultiplied so Qt composites it
        # correctly.
        rgba = bytearray(width * height * 4)
        for i, p in enumerate(pixels):
            rgba[i * 4 + 0] = (p >> 16) & 0xFF  # R
            rgba[i * 4 + 1] = (p >> 8) & 0xFF   # G
            rgba[i * 4 + 2] = p & 0xFF          # B
            rgba[i * 4 + 3] = (p >> 24) & 0xFF  # A

        update = {
            "type": "cursor_update",
            "serial": serial,
            "width": width,
            "height": height,
            "hot_x": xhot,
            "hot_y": yhot,
            "rgba_b64": base64.b64encode(bytes(rgba)).decode("ascii"),
        }

        with self._lock:
            self._last_serial = serial
            self._last_update = update

        if self._on_change is not None:
            try:
                self._on_change(update)
            except Exception as e:
                logger.warning("Cursor update callback error: %s", e)
