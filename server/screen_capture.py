"""
Screen capture module for Linux with multi-monitor support.

Uses mss for fast screen capture. Supports:
- Individual monitor capture
- All-monitors (virtual desktop) capture
- Raw BGRA output for H.264/H.265 encoding pipeline
- JPEG fallback with dirty-rectangle detection
- Monitor enumeration and hot-switching
"""

import io
import time
import logging
from typing import Optional, List

import mss
import numpy as np
from PIL import Image

from common.messages import MonitorInfo

logger = logging.getLogger(__name__)

DEFAULT_JPEG_QUALITY = 60
CHANGE_THRESHOLD = 10
BLOCK_SIZE = 32


class ScreenCapture:
    """Captures the Linux screen with multi-monitor support."""

    def __init__(self, monitor_index: int = 1, jpeg_quality: int = DEFAULT_JPEG_QUALITY):
        """
        Args:
            monitor_index: 0 = all monitors (virtual desktop),
                          1+ = specific monitor
            jpeg_quality: JPEG quality for fallback mode
        """
        self.monitor_index = monitor_index
        self.jpeg_quality = jpeg_quality
        self._sct = mss.mss()
        self._last_frame: Optional[np.ndarray] = None
        self._select_monitor(monitor_index)
        logger.info("Screen capture initialized: %dx%d (monitor %d)",
                     self.width, self.height, monitor_index)

    def _select_monitor(self, index: int):
        """Select which monitor to capture."""
        monitors = self._sct.monitors
        if index >= len(monitors):
            index = 1  # Fall back to primary
        self.monitor_index = index
        self._monitor = monitors[index]
        self.width = self._monitor["width"]
        self.height = self._monitor["height"]
        self._last_frame = None

    def switch_monitor(self, index: int):
        """Switch to a different monitor (or 0 for all)."""
        self._select_monitor(index)
        logger.info("Switched to monitor %d: %dx%d", index, self.width, self.height)

    def list_monitors(self) -> List[MonitorInfo]:
        """Enumerate all available monitors."""
        monitors = []
        for i, mon in enumerate(self._sct.monitors):
            if i == 0:
                name = "All Monitors (Virtual Desktop)"
            else:
                name = f"Monitor {i}"
            monitors.append(MonitorInfo(
                id=i,
                name=name,
                width=mon["width"],
                height=mon["height"],
                x=mon.get("left", 0),
                y=mon.get("top", 0),
                primary=(i == 1),
            ))
        return monitors

    @property
    def screen_size(self) -> tuple:
        return (self.width, self.height)

    # --- Raw BGRA capture (for H.264/H.265 encoder pipeline) ---

    def capture_raw_bgra(self) -> bytes:
        """
        Capture the screen and return raw BGRA pixel data.

        This is the format expected by FFmpeg rawvideo input.
        Returns width * height * 4 bytes.
        """
        sct_img = self._sct.grab(self._monitor)
        return bytes(sct_img.raw)

    def capture_raw_frame(self) -> np.ndarray:
        """Capture and return as numpy BGRA array."""
        sct_img = self._sct.grab(self._monitor)
        return np.array(sct_img)

    # --- JPEG capture (fallback mode) ---

    def capture_full_frame(self) -> bytes:
        """Capture the entire screen and return JPEG bytes."""
        sct_img = self._sct.grab(self._monitor)
        frame = np.array(sct_img)[:, :, :3]
        frame = frame[:, :, ::-1]  # BGR -> RGB
        self._last_frame = frame.copy()
        return self._encode_jpeg(frame)

    def capture_dirty_regions(self) -> list:
        """
        Capture screen and detect dirty rectangles.

        Returns list of (x, y, w, h, jpeg_bytes) tuples for changed regions.
        Returns empty list if nothing changed.
        """
        sct_img = self._sct.grab(self._monitor)
        frame = np.array(sct_img)[:, :, :3]
        frame = frame[:, :, ::-1]

        if self._last_frame is None:
            self._last_frame = frame.copy()
            jpeg_data = self._encode_jpeg(frame)
            return [(0, 0, self.width, self.height, jpeg_data)]

        diff = np.abs(frame.astype(np.int16) - self._last_frame.astype(np.int16))
        changed = np.max(diff, axis=2) > CHANGE_THRESHOLD

        dirty_regions = self._find_dirty_blocks(changed)
        if not dirty_regions:
            return []

        merged = self._merge_regions(dirty_regions)
        results = []
        for x, y, w, h in merged:
            x2 = min(x + w, self.width)
            y2 = min(y + h, self.height)
            region = frame[y:y2, x:x2]
            jpeg_data = self._encode_jpeg(region)
            results.append((x, y, x2 - x, y2 - y, jpeg_data))

        self._last_frame = frame.copy()
        return results

    def _find_dirty_blocks(self, changed: np.ndarray) -> list:
        blocks = []
        h, w = changed.shape
        for by in range(0, h, BLOCK_SIZE):
            for bx in range(0, w, BLOCK_SIZE):
                block = changed[by:by + BLOCK_SIZE, bx:bx + BLOCK_SIZE]
                if np.any(block):
                    blocks.append((bx, by, BLOCK_SIZE, BLOCK_SIZE))
        return blocks

    def _merge_regions(self, blocks: list) -> list:
        if not blocks:
            return []
        rows = {}
        for x, y, w, h in blocks:
            if y not in rows:
                rows[y] = []
            rows[y].append((x, w))

        merged = []
        for y, spans in rows.items():
            spans.sort()
            current_x, current_w = spans[0]
            for x, w in spans[1:]:
                if x <= current_x + current_w:
                    current_w = max(current_w, x + w - current_x)
                else:
                    merged.append((current_x, y, current_w, BLOCK_SIZE))
                    current_x, current_w = x, w
            merged.append((current_x, y, current_w, BLOCK_SIZE))

        if not merged:
            return merged

        merged.sort(key=lambda r: (r[0], r[1]))
        final = [merged[0]]
        for x, y, w, h in merged[1:]:
            px, py, pw, ph = final[-1]
            if x == px and w == pw and y == py + ph:
                final[-1] = (px, py, pw, ph + h)
            else:
                final.append((x, y, w, h))

        return final

    def _encode_jpeg(self, frame: np.ndarray) -> bytes:
        img = Image.fromarray(frame)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=self.jpeg_quality, optimize=False)
        return buf.getvalue()

    def invalidate(self):
        """Force next capture to be a full frame."""
        self._last_frame = None

    def close(self):
        self._sct.close()
