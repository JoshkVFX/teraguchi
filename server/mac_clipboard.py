"""
Clipboard synchronization for the macOS server.

Mirrors the interface of ``server/clipboard.py`` (the Linux xclip/xsel
wrapper) so the session manager can treat the two platforms
identically.

NSPasteboard has no push-style change notification API — you poll
``changeCount`` and diff against the last value. Any increment means
something (possibly another app, possibly us) changed the pasteboard.
We remember what we last wrote so we don't echo our own writes back
to the client.
"""

import logging
import threading
import time
from typing import Optional, Callable

logger = logging.getLogger(__name__)

try:
    from AppKit import (
        NSPasteboard,
        NSPasteboardTypeString,
    )
    _HAS_APPKIT = True
except Exception as _e:
    _HAS_APPKIT = False
    _import_error = _e


class MacClipboardSync:
    """NSPasteboard-backed clipboard sync.

    Matches ``ClipboardSync`` from server/clipboard.py:
      * ``available`` property
      * ``get_clipboard() -> str``
      * ``set_clipboard(text: str)``
      * ``start_monitoring(on_change)`` / ``stop()``
    """

    def __init__(self, display: str = "", poll_interval: float = 0.25):
        # ``display`` is only here to match the Linux constructor
        # signature; it's meaningless on macOS.
        del display
        self.poll_interval = poll_interval
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_content = ""
        self._last_change_count = -1
        self._on_clipboard_change: Optional[Callable] = None

        if _HAS_APPKIT:
            self._pb = NSPasteboard.generalPasteboard()
            try:
                self._last_change_count = int(self._pb.changeCount())
            except Exception:
                self._last_change_count = -1
        else:
            self._pb = None
            logger.warning(
                "AppKit not available (%s) — clipboard sync disabled",
                _import_error,
            )

    @property
    def available(self) -> bool:
        return self._pb is not None

    def get_clipboard(self) -> str:
        if self._pb is None:
            return ""
        try:
            s = self._pb.stringForType_(NSPasteboardTypeString)
            return str(s) if s is not None else ""
        except Exception as e:
            logger.debug("NSPasteboard read failed: %s", e)
            return ""

    def set_clipboard(self, text: str):
        if self._pb is None:
            return
        try:
            self._pb.clearContents()
            ok = self._pb.setString_forType_(text, NSPasteboardTypeString)
            if not ok:
                logger.warning("NSPasteboard setString returned False")
                return
            self._last_content = text
            # Bump our cached change count so the poll loop doesn't
            # fire the callback for our own write.
            try:
                self._last_change_count = int(self._pb.changeCount())
            except Exception:
                pass
            logger.debug("Clipboard set: %d chars", len(text))
        except Exception as e:
            logger.error("Failed to set clipboard: %s", e)

    def start_monitoring(self, on_change: Callable):
        if self._pb is None:
            return
        self._on_clipboard_change = on_change
        self._running = True
        self._last_content = self.get_clipboard()
        try:
            self._last_change_count = int(self._pb.changeCount())
        except Exception:
            pass
        self._thread = threading.Thread(
            target=self._poll_loop,
            daemon=True,
            name="mac-clipboard-monitor",
        )
        self._thread.start()

    def _poll_loop(self):
        while self._running:
            try:
                current_cc = int(self._pb.changeCount())
                if current_cc != self._last_change_count:
                    self._last_change_count = current_cc
                    current = self.get_clipboard()
                    if current and current != self._last_content:
                        self._last_content = current
                        if self._on_clipboard_change:
                            try:
                                self._on_clipboard_change(current)
                            except Exception as e:
                                logger.debug(
                                    "Clipboard change callback error: %s", e
                                )
            except Exception as e:
                logger.debug("Clipboard poll error: %s", e)
            time.sleep(self.poll_interval)

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None
