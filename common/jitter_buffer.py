"""
Jitter buffer for UDP media reception.

Smooths out packet arrival timing variation (jitter) that is natural
with UDP transport. Holds frames briefly before delivering them to
maintain smooth playback despite uneven network delivery.

The buffer dynamically adjusts its depth:
- Deeper when jitter is high (sacrifice latency for smoothness)
- Shallower when jitter is low (minimize latency)
- Drains immediately on keyframes (fast recovery after loss)
"""

import collections
import logging
import threading
import time
from dataclasses import dataclass
from typing import Optional, Callable

logger = logging.getLogger(__name__)


@dataclass
class BufferedFrame:
    """A frame waiting in the jitter buffer."""
    timestamp_ms: int
    arrival_time: float  # time.time() when received
    channel: int
    flags: int
    data: bytes
    is_keyframe: bool


class JitterBuffer:
    """
    Adaptive jitter buffer for video and audio frames.

    Frames are inserted with their capture timestamp and delivered
    after a calculated delay based on observed jitter.
    """

    # Jitter buffer target ranges
    MIN_BUFFER_MS = 5.0      # Minimum buffer depth (near-zero latency)
    MAX_BUFFER_MS = 100.0    # Maximum buffer depth (high jitter)
    DEFAULT_BUFFER_MS = 20.0

    def __init__(self, on_frame_ready: Optional[Callable] = None):
        """
        Args:
            on_frame_ready: Callback(channel, flags, timestamp_ms, data)
                           called when a frame should be displayed.
        """
        self.on_frame_ready = on_frame_ready
        self._buffer: collections.deque = collections.deque()
        self._lock = threading.Lock()

        # Adaptive depth
        self._target_depth_ms = self.DEFAULT_BUFFER_MS
        self._jitter_samples: collections.deque = collections.deque(maxlen=100)
        self._last_arrival: float = 0.0
        self._last_timestamp: int = 0

        # Playback thread
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # Stats
        self._frames_in = 0
        self._frames_out = 0
        self._frames_dropped = 0
        self._late_frames = 0

    def start(self):
        """Start the jitter buffer playback thread."""
        self._running = True
        self._thread = threading.Thread(
            target=self._playback_loop,
            daemon=True,
            name="jitter-buffer",
        )
        self._thread.start()

    def push(self, channel: int, flags: int, timestamp_ms: int,
             data: bytes, is_keyframe: bool = False):
        """
        Push a received frame into the buffer.

        Frames are sorted by timestamp for correct ordering even
        if packets arrive out of order.
        """
        now = time.time()
        self._frames_in += 1

        # Measure jitter (variation in inter-arrival times)
        if self._last_arrival > 0 and self._last_timestamp > 0:
            expected_delta = (timestamp_ms - self._last_timestamp)
            actual_delta = (now - self._last_arrival) * 1000
            jitter = abs(actual_delta - expected_delta)
            self._jitter_samples.append(jitter)
            self._update_target_depth()

        self._last_arrival = now
        self._last_timestamp = timestamp_ms

        frame = BufferedFrame(
            timestamp_ms=timestamp_ms,
            arrival_time=now,
            channel=channel,
            flags=flags,
            data=data,
            is_keyframe=is_keyframe,
        )

        with self._lock:
            # On keyframe: flush old frames (fast recovery)
            if is_keyframe:
                old_count = len(self._buffer)
                self._buffer.clear()
                if old_count > 0:
                    self._frames_dropped += old_count
                    logger.debug("Keyframe: flushed %d buffered frames", old_count)

            # Insert in timestamp order
            inserted = False
            for i in range(len(self._buffer) - 1, -1, -1):
                if self._buffer[i].timestamp_ms <= timestamp_ms:
                    self._buffer.insert(i + 1, frame)
                    inserted = True
                    break
            if not inserted:
                self._buffer.appendleft(frame)

    def _update_target_depth(self):
        """Adapt buffer depth based on measured jitter."""
        if len(self._jitter_samples) < 10:
            return

        # Use 95th percentile jitter as target
        sorted_jitter = sorted(self._jitter_samples)
        p95_idx = int(len(sorted_jitter) * 0.95)
        p95_jitter = sorted_jitter[p95_idx]

        # Target depth = 1.5x the 95th percentile jitter
        target = p95_jitter * 1.5
        target = max(self.MIN_BUFFER_MS, min(self.MAX_BUFFER_MS, target))

        # Smooth the change
        self._target_depth_ms = (self._target_depth_ms * 0.8) + (target * 0.2)

    def _playback_loop(self):
        """Continuously drain the buffer at the right timing."""
        while self._running:
            frame = None

            with self._lock:
                if self._buffer:
                    oldest = self._buffer[0]
                    buffered_ms = (time.time() - oldest.arrival_time) * 1000

                    if buffered_ms >= self._target_depth_ms:
                        frame = self._buffer.popleft()

                        # Drop any frames that are too old (more than 2x buffer depth)
                        while self._buffer:
                            next_frame = self._buffer[0]
                            age_ms = (time.time() - next_frame.arrival_time) * 1000
                            if age_ms > self._target_depth_ms * 2:
                                self._buffer.popleft()
                                self._frames_dropped += 1
                            else:
                                break

            if frame:
                self._frames_out += 1
                if self.on_frame_ready:
                    self.on_frame_ready(
                        frame.channel, frame.flags,
                        frame.timestamp_ms, frame.data)

            # Sleep briefly — aim for ~1ms resolution
            time.sleep(0.001)

    def stop(self):
        """Stop the buffer."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None

    @property
    def depth_ms(self) -> float:
        """Current buffer depth in milliseconds."""
        with self._lock:
            if not self._buffer:
                return 0.0
            return (time.time() - self._buffer[0].arrival_time) * 1000

    @property
    def target_depth_ms(self) -> float:
        return self._target_depth_ms

    @property
    def stats(self) -> dict:
        avg_jitter = 0.0
        if self._jitter_samples:
            avg_jitter = sum(self._jitter_samples) / len(self._jitter_samples)

        return {
            "buffer_depth_ms": round(self.depth_ms, 1),
            "target_depth_ms": round(self._target_depth_ms, 1),
            "avg_jitter_ms": round(avg_jitter, 1),
            "frames_in": self._frames_in,
            "frames_out": self._frames_out,
            "frames_dropped": self._frames_dropped,
            "buffered_count": len(self._buffer),
        }
