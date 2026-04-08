"""
Audio capture module for Linux.

Captures system audio via PulseAudio/PipeWire monitor source
and encodes it as Opus for efficient streaming.

Falls back to no audio if PulseAudio is not available.
"""

import logging
import os
import pwd
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

    def __init__(self, bitrate_kbps: int = 128, sample_rate: int = 48000,
                 channels: int = 2, uid: int = 0, gid: int = 0):
        self.bitrate_kbps = bitrate_kbps
        self.sample_rate = sample_rate
        self.channels = channels
        self._uid = uid
        self._gid = gid
        self._process: Optional[subprocess.Popen] = None
        self._reader_thread: Optional[threading.Thread] = None
        self._running = False
        self._on_audio_frame: Optional[Callable] = None
        self._pulse_env = self._make_pulse_env()
        self._source = self._find_monitor_source()

    def _make_pulse_env(self) -> dict:
        """Build environment for accessing the user's PulseAudio."""
        env = os.environ.copy()
        uid = self._uid or os.getuid()
        env["PULSE_RUNTIME_PATH"] = f"/run/user/{uid}/pulse"
        env["XDG_RUNTIME_DIR"] = f"/run/user/{uid}"
        if self._uid:
            try:
                pw = pwd.getpwuid(self._uid)
                env["HOME"] = pw.pw_dir
                env["USER"] = pw.pw_name
            except KeyError:
                pass
        return env

    def _demote(self):
        """Drop privileges to the target user (preexec_fn)."""
        if self._uid and os.getuid() == 0:
            os.setgid(self._gid)
            os.initgroups(pwd.getpwuid(self._uid).pw_name, self._gid)
            os.setuid(self._uid)

    def _find_monitor_source(self) -> str:
        """Find the PulseAudio monitor source for capturing system audio."""
        demote = self._demote if self._uid else None
        try:
            proc = subprocess.run(
                ["pactl", "get-default-sink"],
                capture_output=True, text=True, timeout=5,
                env=self._pulse_env, preexec_fn=demote,
            )
            if proc.returncode == 0:
                sink = proc.stdout.strip()
                source = f"{sink}.monitor"
                logger.info("Found audio monitor source: %s", source)
                return source
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        try:
            proc = subprocess.run(
                ["pactl", "list", "short", "sources"],
                capture_output=True, text=True, timeout=5,
                env=self._pulse_env, preexec_fn=demote,
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
            # Output raw PCM for simplest client-side playback
            "-c:a", "pcm_s16le",
            "-ar", str(self.sample_rate),
            "-ac", str(self.channels),
            "-f", "s16le",
            "pipe:1",
        ]

        logger.info("Starting audio capture: %s", " ".join(cmd))

        try:
            demote = self._demote if self._uid else None
            self._process = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
                env=self._pulse_env,
                preexec_fn=demote,
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
                chunk_size = self.sample_rate * self.channels * 2 * 20 // 1000  # 20ms of PCM
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


def check_audio_available(uid: int = 0, gid: int = 0) -> bool:
    """Check if PulseAudio/PipeWire audio capture is available."""
    env = os.environ.copy()
    check_uid = uid or os.getuid()
    env["PULSE_RUNTIME_PATH"] = f"/run/user/{check_uid}/pulse"
    env["XDG_RUNTIME_DIR"] = f"/run/user/{check_uid}"

    def demote():
        if uid and os.getuid() == 0:
            os.setgid(gid)
            os.initgroups(pwd.getpwuid(uid).pw_name, gid)
            os.setuid(uid)

    try:
        proc = subprocess.run(
            ["pactl", "get-default-sink"],
            capture_output=True, timeout=5,
            env=env, preexec_fn=demote if uid else None,
        )
        return proc.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
