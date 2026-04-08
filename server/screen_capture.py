"""
Screen capture module for Linux.

Uses mss for fast screen capture, with dirty-rectangle detection
to minimize bandwidth by only sending changed regions.
"""

import io
import time
import logging
from typing import Optional

import mss
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

# Default JPEG quality (0-100). Lower = smaller files, more artifacts.
DEFAULT_JPEG_QUALITY = 60
# Minimum change threshold (0-255) for a pixel to be considered "dirty"
CHANGE_THRESHOLD = 10
# Minimum dirty area (pixels) to bother sending a partial update
MIN_DIRTY_AREA = 100
# Grid block size for dirty detection (larger = coarser but faster)
BLOCK_SIZE = 32


class ScreenCapture:
    """Captures the Linux screen and detects changed regions."""

    def __init__(self, monitor_index: int = 1, jpeg_quality: int = DEFAULT_JPEG_QUALITY):
        self.monitor_index = monitor_index
        self.jpeg_quality = jpeg_quality
        self._sct = mss.mss()
        self._last_frame: Optional[np.ndarray] = None
        self._monitor = self._sct.monitors[self.monitor_index]
        self.width = self._monitor["width"]
        self.height = self._monitor["height"]
        logger.info("Screen capture initialized: %dx%d (monitor %d)",
                     self.width, self.height, monitor_index)

    @property
    def screen_size(self) -> tuple:
        return (self.width, self.height)

    def capture_full_frame(self) -> bytes:
        """Capture the entire screen and return JPEG bytes."""
        sct_img = self._sct.grab(self._monitor)
        # mss returns BGRA, convert to RGB
        frame = np.array(sct_img)[:, :, :3]  # Drop alpha
        frame = frame[:, :, ::-1]  # BGR -> RGB
        self._last_frame = frame.copy()
        return self._encode_jpeg(frame)

    def capture_dirty_regions(self) -> list:
        """
        Capture screen and detect dirty rectangles.

        Returns list of (x, y, w, h, jpeg_bytes) tuples for changed regions.
        Returns empty list if nothing changed.
        If this is the first capture, returns a single full-frame region.
        """
        sct_img = self._sct.grab(self._monitor)
        frame = np.array(sct_img)[:, :, :3]
        frame = frame[:, :, ::-1]  # BGR -> RGB

        if self._last_frame is None:
            self._last_frame = frame.copy()
            jpeg_data = self._encode_jpeg(frame)
            return [(0, 0, self.width, self.height, jpeg_data)]

        # Compute per-pixel difference
        diff = np.abs(frame.astype(np.int16) - self._last_frame.astype(np.int16))
        changed = np.max(diff, axis=2) > CHANGE_THRESHOLD

        # Find dirty blocks
        dirty_regions = self._find_dirty_blocks(changed)

        if not dirty_regions:
            return []

        # Merge nearby dirty blocks into larger rectangles
        merged = self._merge_regions(dirty_regions)

        results = []
        for x, y, w, h in merged:
            # Clamp to screen bounds
            x2 = min(x + w, self.width)
            y2 = min(y + h, self.height)
            region = frame[y:y2, x:x2]
            jpeg_data = self._encode_jpeg(region)
            results.append((x, y, x2 - x, y2 - y, jpeg_data))

        self._last_frame = frame.copy()
        return results

    def _find_dirty_blocks(self, changed: np.ndarray) -> list:
        """Find grid blocks that contain changes."""
        blocks = []
        h, w = changed.shape
        for by in range(0, h, BLOCK_SIZE):
            for bx in range(0, w, BLOCK_SIZE):
                block = changed[by:by + BLOCK_SIZE, bx:bx + BLOCK_SIZE]
                if np.any(block):
                    blocks.append((bx, by, BLOCK_SIZE, BLOCK_SIZE))
        return blocks

    def _merge_regions(self, blocks: list) -> list:
        """
        Merge adjacent dirty blocks into larger rectangles.
        Simple row-based merging for efficiency.
        """
        if not blocks:
            return []

        # Group by row
        rows = {}
        for x, y, w, h in blocks:
            if y not in rows:
                rows[y] = []
            rows[y].append((x, w))

        merged = []
        for y, spans in rows.items():
            spans.sort()
            # Merge horizontally contiguous spans
            current_x, current_w = spans[0]
            for x, w in spans[1:]:
                if x <= current_x + current_w:
                    current_w = max(current_w, x + w - current_x)
                else:
                    merged.append((current_x, y, current_w, BLOCK_SIZE))
                    current_x, current_w = x, w
            merged.append((current_x, y, current_w, BLOCK_SIZE))

        # Now merge vertically contiguous rectangles with same x,w
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
        """Encode an RGB numpy array as JPEG bytes."""
        img = Image.fromarray(frame)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=self.jpeg_quality, optimize=False)
        return buf.getvalue()

    def invalidate(self):
        """Force next capture to be a full frame."""
        self._last_frame = None

    def close(self):
        """Release resources."""
        self._sct.close()
