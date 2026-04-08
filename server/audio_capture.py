"""
Audio capture module for Linux.

Captures system audio via PulseAudio/PipeWire monitor source
and encodes it as Opus for efficient streaming.

Falls back to no audio if PulseAudio is not available.
"""

import logging
import subprocess
import threading
import time
from typing import Optional, Callable

logger = logging.getLogger(__name__)


class AudioCapture:
    """
    Captures audio from the Linux system using FFmpeg with PulseAudio input.

    Encodes to Opus codec at configurable bitrate, outputting raw Opus frames
    suitable for WebSocket streaming.
    """

    def __init__(self, bitrate_kbps: int = 128, sample_rate: int = 48000, channels: int = 2):
        self.bitrate_kbps = bitrate_kbps
        self.sample_rate = sample_rate
        self.channels = channels
        self._process: Optional[subprocess.Popen] = None
        self._reader_thread: Optional[threading.Thread] = None
        self._running = False
        self._on_audio_frame: Optional[Callable] = None
        self._source = self._find_monitor_source()

    def _find_monitor_source(self) -> str:
        """Find the PulseAudio monitor source for capturing system audio."""
        try:
            # Get the default sink and derive its monitor source
            proc = subprocess.run(
                ["pactl", "get-default-sink"],
                capture_output=True, text=True, timeout=5,
            )
            if proc.returncode == 0:
                sink = proc.stdout.strip()
                source = f"{sink}.monitor"
                logger.info("Found audio monitor source: %s", source)
                return source
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        try:
            # Fallback: list sources and find a monitor
            proc = subprocess.run(
                ["pactl", "list", "short", "sources"],
                capture_output=True, text=True, timeout=5,
            )
            for line in proc.stdout.strip().split("\n"):
                if ".monitor" in line:
                    parts = line.split("\t")
                    if len(parts) >= 2:
                        logger.info("Found audio monitor source: %s", parts[1])
                        return parts[1]
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        logger.warning("No PulseAudio monitor source found, audio disabled")
        return ""

    @property
    def available(self) -> bool:
        return bool(self._source)

    def start(self, on_audio_frame: Callable):
        """
        Start capturing audio.

        Args:
            on_audio_frame: Callback(opus_bytes, timestamp_ms) called from reader thread.
        """
        if not self._source:
            logger.warning("Audio capture not available (no monitor source)")
            return

        self._on_audio_frame = on_audio_frame
        self._running = True

        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "error",
            # PulseAudio input
            "-f", "pulse",
            "-i", self._source,
            # Encode to Opus
            "-c:a", "libopus",
            "-b:a", f"{self.bitrate_kbps}k",
            "-ar", str(self.sample_rate),
            "-ac", str(self.channels),
            "-application", "lowdelay",
            "-frame_duration", "20",  # 20ms frames for low latency
            # Output as OGG container (Opus needs a container for framing)
            "-f", "ogg",
            "pipe:1",
        ]

        logger.info("Starting audio capture: %s", " ".join(cmd))

        try:
            self._process = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
            )
        except FileNotFoundError:
            logger.error("FFmpeg not found, audio capture disabled")
            self._running = False
            return

        self._reader_thread = threading.Thread(
            target=self._read_audio,
            daemon=True,
            name="audio-reader",
        )
        self._reader_thread.start()

    def _read_audio(self):
        """Read encoded audio data from FFmpeg stdout."""
        try:
            while self._running and self._process and self._process.poll() is None:
                # Read in chunks matching roughly 20ms of Opus at our bitrate
                chunk_size = max(256, self.bitrate_kbps * 20 // 8)  # ~20ms worth
                data = self._process.stdout.read(chunk_size)
                if not data:
                    break

                timestamp_ms = int(time.time() * 1000)
                if self._on_audio_frame:
                    self._on_audio_frame(data, timestamp_ms)

        except Exception as e:
            if self._running:
                logger.error("Audio reader error: %s", e)

    def update_bitrate(self, bitrate_kbps: int):
        """Update audio bitrate (requires restart)."""
        if bitrate_kbps != self.bitrate_kbps:
            self.bitrate_kbps = bitrate_kbps
            if self._running:
                callback = self._on_audio_frame
                self.stop()
                self.start(callback)

    def stop(self):
        """Stop audio capture."""
        self._running = False
        if self._process:
            try:
                self._process.terminate()
                self._process.wait(timeout=3)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass
            self._process = None

        if self._reader_thread:
            self._reader_thread.join(timeout=3)
            self._reader_thread = None

        logger.info("Audio capture stopped")


def check_audio_available() -> bool:
    """Check if PulseAudio/PipeWire audio capture is available."""
    try:
        proc = subprocess.run(
            ["pactl", "get-default-sink"],
            capture_output=True, timeout=5,
        )
        return proc.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
