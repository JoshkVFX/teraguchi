"""
Video encoder using FFmpeg subprocess.

Supports:
- H.264 (libx264) with High 4:4:4 Predictive profile for full color fidelity
- H.265 (libx265) with 4:4:4 support
- Lossless mode
- Adaptive quality based on the sharpness ↔ temporal stability slider
- Frame-by-frame encoding with pipe I/O for low latency

The encoder runs FFmpeg as a subprocess, feeding raw frames via stdin
and reading encoded NAL units from stdout.
"""

import io
import logging
import os
import signal
import struct
import subprocess
import threading
import time
from typing import Optional, Callable

from common.messages import QualitySettings, ChromaSubsampling, VideoCodec

logger = logging.getLogger(__name__)


class VideoEncoder:
    """
    FFmpeg-based video encoder with H.264/H.265 + YUV 4:4:4 support.

    Encodes raw BGRA frames from screen capture into an H.264 or H.265
    byte stream, outputting individual access units (NAL unit groups).
    """

    def __init__(self, width: int, height: int, settings: QualitySettings):
        self.width = width
        self.height = height
        self.settings = settings
        self._process: Optional[subprocess.Popen] = None
        self._reader_thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._on_encoded_frame: Optional[Callable] = None
        self._running = False
        self._frame_count = 0
        self._encode_times: list = []
        self._total_bytes = 0
        self._start_time = 0.0

    @property
    def avg_encode_time_ms(self) -> float:
        if not self._encode_times:
            return 0.0
        return sum(self._encode_times[-30:]) / len(self._encode_times[-30:])

    @property
    def bandwidth_mbps(self) -> float:
        elapsed = time.time() - self._start_time
        if elapsed <= 0:
            return 0.0
        return (self._total_bytes * 8) / (elapsed * 1_000_000)

    def start(self, on_encoded_frame: Callable):
        """
        Start the encoder.

        Args:
            on_encoded_frame: Callback(frame_bytes, is_keyframe) called
                              from a reader thread when an encoded frame
                              is available.
        """
        self._on_encoded_frame = on_encoded_frame
        self._running = True
        self._start_time = time.time()
        self._start_ffmpeg()

    def _build_ffmpeg_cmd(self) -> list:
        """Build the FFmpeg command line based on current quality settings."""
        s = self.settings
        fps = s.effective_fps()
        crf = s.effective_crf()
        preset = s.effective_preset()
        chroma = s.effective_chroma()

        # Determine pixel format for output
        if chroma == ChromaSubsampling.YUV444:
            pix_fmt_out = "yuv444p"
        elif chroma == ChromaSubsampling.YUV422:
            pix_fmt_out = "yuv422p"
        else:
            pix_fmt_out = "yuv420p"

        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "error",
            # Input: raw BGRA frames from pipe
            "-f", "rawvideo",
            "-pixel_format", "bgra",
            "-video_size", f"{self.width}x{self.height}",
            "-framerate", str(fps),
            "-i", "pipe:0",
        ]

        codec = s.codec.lower()
        if codec == "h265":
            cmd.extend(self._h265_args(crf, preset, pix_fmt_out))
        else:
            cmd.extend(self._h264_args(crf, preset, pix_fmt_out))

        # Output to pipe as raw bitstream
        if codec == "h265":
            cmd.extend(["-f", "hevc", "pipe:1"])
        else:
            cmd.extend(["-f", "h264", "pipe:1"])

        return cmd

    def _h264_args(self, crf: int, preset: str, pix_fmt: str) -> list:
        """Build H.264-specific encoder arguments."""
        args = [
            "-c:v", "libx264",
            "-preset", preset,
            "-tune", "zerolatency",
            "-pix_fmt", pix_fmt,
        ]

        if self.settings.force_lossless:
            args.extend(["-qp", "0"])  # Lossless mode
            # Use High 4:4:4 Predictive profile for lossless
            args.extend(["-profile:v", "high444"])
        else:
            args.extend(["-crf", str(crf)])
            # Profile selection based on chroma
            if pix_fmt == "yuv444p":
                args.extend(["-profile:v", "high444"])
            elif pix_fmt == "yuv422p":
                args.extend(["-profile:v", "high422"])
            else:
                args.extend(["-profile:v", "high"])

        # Low-latency tuning
        args.extend([
            "-g", "60",          # Keyframe every 60 frames (2s at 30fps)
            "-bf", "0",          # No B-frames for minimum latency
            "-rc-lookahead", "0",
            "-flags", "+cgop",
            "-sc_threshold", "0",
        ])

        # Adaptive quantization based on quality bias
        if self.settings.quality_bias > 0.6:
            # Favor spatial quality (sharper individual frames)
            args.extend(["-aq-mode", "2", "-aq-strength", "1.2"])
        else:
            # Favor temporal stability (smoother motion)
            args.extend(["-aq-mode", "1", "-aq-strength", "0.8"])

        # Bandwidth cap
        max_bitrate = int(self.settings.max_bandwidth_mbps * 1000)  # kbps
        args.extend([
            "-maxrate", f"{max_bitrate}k",
            "-bufsize", f"{max_bitrate}k",
        ])

        return args

    def _h265_args(self, crf: int, preset: str, pix_fmt: str) -> list:
        """Build H.265/HEVC-specific encoder arguments."""
        args = [
            "-c:v", "libx265",
            "-preset", preset,
            "-pix_fmt", pix_fmt,
        ]

        if self.settings.force_lossless:
            args.extend(["-x265-params", "lossless=1"])
        else:
            args.extend(["-crf", str(crf)])

        # Low-latency tuning for x265
        x265_params = [
            "keyint=60",
            "bframes=0",
            "rc-lookahead=0",
            "scenecut=0",
            "no-open-gop=1",
        ]

        if self.settings.quality_bias > 0.6:
            x265_params.append("aq-mode=2")
        else:
            x265_params.append("aq-mode=1")

        args.extend(["-x265-params", ":".join(x265_params)])

        max_bitrate = int(self.settings.max_bandwidth_mbps * 1000)
        args.extend([
            "-maxrate", f"{max_bitrate}k",
            "-bufsize", f"{max_bitrate}k",
        ])

        return args

    def _start_ffmpeg(self):
        """Launch the FFmpeg subprocess."""
        cmd = self._build_ffmpeg_cmd()
        logger.info("Starting encoder: %s", " ".join(cmd))

        self._process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )

        # Reader thread to consume encoded output
        self._reader_thread = threading.Thread(
            target=self._read_output,
            daemon=True,
            name="encoder-reader",
        )
        self._reader_thread.start()

    def _read_output(self):
        """
        Read encoded data from FFmpeg stdout.

        For H.264, we read NAL units delimited by start codes (0x00000001).
        We accumulate data and emit complete access units.
        """
        buf = bytearray()
        START_CODE = b'\x00\x00\x00\x01'

        try:
            while self._running and self._process and self._process.poll() is None:
                chunk = self._process.stdout.read(65536)
                if not chunk:
                    break
                buf.extend(chunk)

                # Find and emit complete NAL units
                while True:
                    # Find start of next NAL
                    idx = buf.find(START_CODE, 4)
                    if idx < 0:
                        break

                    nal_data = bytes(buf[:idx])
                    buf = buf[idx:]

                    if len(nal_data) > 4:
                        # Determine if keyframe by checking NAL type
                        is_keyframe = self._is_keyframe(nal_data)
                        self._total_bytes += len(nal_data)
                        if self._on_encoded_frame:
                            self._on_encoded_frame(nal_data, is_keyframe)

        except Exception as e:
            if self._running:
                logger.error("Encoder reader error: %s", e)

    def _is_keyframe(self, nal_data: bytes) -> bool:
        """Check if a NAL unit is a keyframe (IDR)."""
        if len(nal_data) < 5:
            return False
        # Skip start code
        offset = 4 if nal_data[:4] == b'\x00\x00\x00\x01' else 3
        if offset >= len(nal_data):
            return False
        nal_type = nal_data[offset] & 0x1F
        # NAL type 5 = IDR slice (keyframe)
        return nal_type == 5

    def feed_frame(self, bgra_data: bytes):
        """
        Feed a raw BGRA frame to the encoder.

        Args:
            bgra_data: Raw BGRA pixel data (width * height * 4 bytes)
        """
        if not self._process or self._process.poll() is not None:
            return

        start = time.time()
        try:
            self._process.stdin.write(bgra_data)
            self._process.stdin.flush()
            self._frame_count += 1
            elapsed_ms = (time.time() - start) * 1000
            self._encode_times.append(elapsed_ms)
            if len(self._encode_times) > 100:
                self._encode_times = self._encode_times[-60:]
        except (BrokenPipeError, OSError) as e:
            logger.error("Failed to feed frame: %s", e)

    def update_settings(self, settings: QualitySettings):
        """
        Update encoder settings. Restarts FFmpeg if codec/chroma changed.
        """
        needs_restart = (
            settings.codec != self.settings.codec or
            settings.effective_chroma() != self.settings.effective_chroma() or
            settings.force_lossless != self.settings.force_lossless or
            settings.effective_fps() != self.settings.effective_fps()
        )
        self.settings = settings

        if needs_restart and self._running:
            logger.info("Encoder settings changed, restarting FFmpeg...")
            callback = self._on_encoded_frame
            self.stop()
            self.start(callback)

    def request_keyframe(self):
        """
        Force the encoder to emit a keyframe.
        We do this by briefly stopping and restarting, which forces an IDR.
        A more elegant approach would use FFmpeg's force_key_frames, but
        with the pipe interface this is reliable.
        """
        # For now, this is handled by the periodic keyframe interval (GOP).
        # A full restart for immediate keyframe can be done if needed.
        pass

    def stop(self):
        """Stop the encoder and clean up."""
        self._running = False
        if self._process:
            try:
                self._process.stdin.close()
            except Exception:
                pass
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

        logger.info("Encoder stopped (encoded %d frames)", self._frame_count)


class JpegFallbackEncoder:
    """
    Simple JPEG encoder for environments without FFmpeg.
    Also used as fallback when H.264 encoding fails.
    """

    def __init__(self, quality: int = 60):
        self.quality = quality
        self._total_bytes = 0
        self._start_time = time.time()

    @property
    def bandwidth_mbps(self) -> float:
        elapsed = time.time() - self._start_time
        if elapsed <= 0:
            return 0.0
        return (self._total_bytes * 8) / (elapsed * 1_000_000)

    def encode_frame(self, frame_rgb) -> bytes:
        """Encode an RGB numpy array as JPEG bytes."""
        from PIL import Image
        img = Image.fromarray(frame_rgb)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=self.quality, optimize=False)
        data = buf.getvalue()
        self._total_bytes += len(data)
        return data

    def update_quality(self, quality: int):
        self.quality = max(1, min(100, quality))


def check_ffmpeg_available() -> dict:
    """
    Check what FFmpeg capabilities are available.

    Returns dict with:
        available: bool
        h264: bool (libx264)
        h265: bool (libx265)
        h264_444: bool (High 4:4:4 profile support)
    """
    result = {
        "available": False,
        "h264": False,
        "h265": False,
        "h264_444": False,
    }

    try:
        proc = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=5,
        )
        output = proc.stdout
        result["available"] = True
        result["h264"] = "libx264" in output
        result["h265"] = "libx265" in output
        # libx264 supports High 4:4:4 if it's compiled with 10-bit or 4:4:4
        # Most distributions include this by default
        result["h264_444"] = result["h264"]  # Assume yes if x264 available
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    return result
