"""
Clipboard synchronization for the server.

Monitors the X11 clipboard for changes and can set clipboard contents
when receiving data from the client.
"""

import logging
import subprocess
import threading
import time
from typing import Optional, Callable

logger = logging.getLogger(__name__)


class ClipboardSync:
    """
    Monitors and controls the system clipboard.

    Uses xclip or xsel for clipboard access (widely available on Linux).
    Polls for changes and notifies via callback.
    """

    def __init__(self, poll_interval: float = 0.5):
        self.poll_interval = poll_interval
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_content = ""
        self._on_clipboard_change: Optional[Callable] = None
        self._tool = self._find_clipboard_tool()

    def _find_clipboard_tool(self) -> str:
        """Find available clipboard tool."""
        for tool in ("xclip", "xsel"):
            try:
                subprocess.run([tool, "--version"], capture_output=True, timeout=2)
                logger.info("Using clipboard tool: %s", tool)
                return tool
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue
        logger.warning("No clipboard tool found (install xclip or xsel)")
        return ""

    @property
    def available(self) -> bool:
        return bool(self._tool)

    def get_clipboard(self) -> str:
        """Get current clipboard text content."""
        if not self._tool:
            return ""
        try:
            if self._tool == "xclip":
                cmd = ["xclip", "-selection", "clipboard", "-o"]
            else:
                cmd = ["xsel", "--clipboard", "--output"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=2)
            return result.stdout if result.returncode == 0 else ""
        except (subprocess.TimeoutExpired, Exception):
            return ""

    def set_clipboard(self, text: str):
        """Set clipboard text content."""
        if not self._tool:
            return
        try:
            if self._tool == "xclip":
                cmd = ["xclip", "-selection", "clipboard", "-i"]
            else:
                cmd = ["xsel", "--clipboard", "--input"]
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, timeout=2)
            proc.communicate(input=text.encode("utf-8"), timeout=2)
            self._last_content = text
        except (subprocess.TimeoutExpired, Exception) as e:
            logger.error("Failed to set clipboard: %s", e)

    def start_monitoring(self, on_change: Callable):
        """
        Start monitoring clipboard for changes.

        Args:
            on_change: Callback(text) called when clipboard content changes.
        """
        if not self._tool:
            return
        self._on_clipboard_change = on_change
        self._running = True
        self._last_content = self.get_clipboard()
        self._thread = threading.Thread(
            target=self._poll_loop,
            daemon=True,
            name="clipboard-monitor",
        )
        self._thread.start()

    def _poll_loop(self):
        """Poll clipboard for changes."""
        while self._running:
            try:
                current = self.get_clipboard()
                if current and current != self._last_content:
                    self._last_content = current
                    if self._on_clipboard_change:
                        self._on_clipboard_change(current)
            except Exception as e:
                logger.debug("Clipboard poll error: %s", e)
            time.sleep(self.poll_interval)

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None
