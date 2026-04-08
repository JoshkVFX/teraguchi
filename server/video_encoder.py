"""
Video encoder using FFmpeg subprocess with GPU-accelerated encoding.

Supports:
- H.264 (libx264) software + NVENC/VAAPI/AMF hardware acceleration
- H.265 (libx265) software + NVENC/VAAPI/AMF hardware acceleration
- AV1 (SVT-AV1 software, NVENC AV1 hardware)
- YUV 4:4:4 chroma (software codecs + NVENC)
- Lossless mode
- Adaptive quality based on the sharpness <-> temporal stability slider
- Frame-by-frame encoding with pipe I/O for low latency

Hardware encoder priority: NVENC > VAAPI > AMF > Software
The encoder auto-detects available hardware and selects the best option.
"""

import io
import logging
import os
import signal
import struct
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Optional, Callable, List, Dict

from common.messages import QualitySettings, ChromaSubsampling, VideoCodec

logger = logging.getLogger(__name__)


# ============================================================
# Hardware Encoder Detection
# ============================================================

@dataclass
class HWEncoder:
    """Describes a hardware encoder capability."""
    name: str           # e.g. "h264_nvenc"
    codec: str          # "h264", "h265", "av1"
    backend: str        # "nvenc", "vaapi", "amf", "software"
    supports_444: bool  # Can do YUV 4:4:4
    supports_lossless: bool
    priority: int       # Lower = preferred


# Encoder definitions ordered by priority
ENCODER_DEFS = [
    # NVENC (NVIDIA)
    HWEncoder("h264_nvenc",  "h264", "nvenc", supports_444=True,  supports_lossless=True,  priority=10),
    HWEncoder("hevc_nvenc",  "h265", "nvenc", supports_444=True,  supports_lossless=True,  priority=10),
    HWEncoder("av1_nvenc",   "av1",  "nvenc", supports_444=False, supports_lossless=False, priority=10),
    # VAAPI (Intel/AMD on Linux)
    HWEncoder("h264_vaapi",  "h264", "vaapi", supports_444=False, supports_lossless=False, priority=20),
    HWEncoder("hevc_vaapi",  "h265", "vaapi", supports_444=False, supports_lossless=False, priority=20),
    HWEncoder("av1_vaapi",   "av1",  "vaapi", supports_444=False, supports_lossless=False, priority=20),
    # AMF (AMD on Windows/Linux)
    HWEncoder("h264_amf",    "h264", "amf",   supports_444=False, supports_lossless=False, priority=30),
    HWEncoder("hevc_amf",    "h265", "amf",   supports_444=False, supports_lossless=False, priority=30),
    # Software fallbacks
    HWEncoder("libx264",     "h264", "software", supports_444=True,  supports_lossless=True,  priority=100),
    HWEncoder("libx265",     "h265", "software", supports_444=True,  supports_lossless=True,  priority=100),
    HWEncoder("libsvtav1",   "av1",  "software", supports_444=False, supports_lossless=False, priority=100),
]


def detect_encoders() -> Dict[str, List[HWEncoder]]:
    """
    Detect available FFmpeg encoders, grouped by codec.

    Returns: {"h264": [HWEncoder, ...], "h265": [...], "av1": [...]}
    """
    available = {"h264": [], "h265": [], "av1": []}

    try:
        proc = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=5,
        )
        output = proc.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return available

    for enc_def in ENCODER_DEFS:
        if enc_def.name in output:
            available[enc_def.codec].append(enc_def)

    # Sort each list by priority
    for codec in available:
        available[codec].sort(key=lambda e: e.priority)

    return available


def select_best_encoder(codec: str, available: Dict[str, List[HWEncoder]],
                        need_444: bool = False, need_lossless: bool = False) -> Optional[HWEncoder]:
    """
    Select the best available encoder for the given codec and requirements.

    Prefers hardware encoders. If 4:4:4 or lossless is required and no
    hardware encoder supports it, falls back to software.
    """
    candidates = available.get(codec, [])
    if not candidates:
        return None

    for enc in candidates:
        if need_444 and not enc.supports_444:
            continue
        if need_lossless and not enc.supports_lossless:
            continue
        return enc

    # If nothing matches requirements, return first available
    # (caller will handle the fallback to 4:2:0 or lossy)
    return candidates[0] if candidates else None


# ============================================================
# Video Encoder
# ============================================================

class VideoEncoder:
    """
    FFmpeg-based video encoder with hardware acceleration support.

    Priority: NVENC > VAAPI > AMF > libx264/libx265/libsvtav1
    Encodes raw BGRA frames from screen capture into a compressed stream.
    """

    def __init__(self, width: int, height: int, settings: QualitySettings,
                 available_encoders: Optional[Dict[str, List[HWEncoder]]] = None):
        self.width = width
        self.height = height
        self.settings = settings
        self._available = available_encoders if available_encoders is not None else detect_encoders()
        self._active_encoder: Optional[HWEncoder] = None
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
    def active_encoder_name(self) -> str:
        return self._active_encoder.name if self._active_encoder else "none"

    @property
    def active_backend(self) -> str:
        return self._active_encoder.backend if self._active_encoder else "none"

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
        """Start the encoder."""
        self._on_encoded_frame = on_encoded_frame
        self._running = True
        self._start_time = time.time()
        self._start_ffmpeg()

    def _select_encoder(self) -> HWEncoder:
        """Select the best encoder for current settings."""
        codec = self.settings.codec.lower()
        if codec not in ("h264", "h265", "av1"):
            codec = "h264"

        need_444 = self.settings.effective_chroma() == ChromaSubsampling.YUV444
        need_lossless = self.settings.force_lossless

        enc = select_best_encoder(codec, self._available, need_444, need_lossless)
        if enc is None:
            # Absolute fallback
            enc = HWEncoder("libx264", "h264", "software",
                            supports_444=True, supports_lossless=True, priority=100)

        logger.info("Selected encoder: %s (backend=%s, 444=%s, lossless=%s)",
                     enc.name, enc.backend, enc.supports_444, enc.supports_lossless)
        return enc

    def _build_ffmpeg_cmd(self) -> list:
        """Build the FFmpeg command line based on current settings and best encoder."""
        s = self.settings
        self._active_encoder = self._select_encoder()
        enc = self._active_encoder
        fps = s.effective_fps()

        # Determine pixel format
        chroma = s.effective_chroma()
        if chroma == ChromaSubsampling.YUV444:
            if enc.supports_444:
                pix_fmt_out = "yuv444p"
            else:
                # Hardware encoder doesn't support 4:4:4 — downgrade
                pix_fmt_out = "yuv420p"
                logger.warning("Encoder %s doesn't support YUV444, falling back to YUV420", enc.name)
        elif chroma == ChromaSubsampling.YUV422:
            pix_fmt_out = "yuv422p"
        else:
            pix_fmt_out = "yuv420p"

        cmd = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel", "error",
        ]

        # VAAPI needs hardware device init
        if enc.backend == "vaapi":
            drm_device = self._find_vaapi_device()
            cmd.extend(["-vaapi_device", drm_device])

        # Input: raw BGRA frames from pipe
        cmd.extend([
            "-f", "rawvideo",
            "-pixel_format", "bgra",
            "-video_size", f"{self.width}x{self.height}",
            "-framerate", str(fps),
            "-i", "pipe:0",
        ])

        # VAAPI needs format upload filter
        if enc.backend == "vaapi":
            cmd.extend([
                "-vf", f"format=nv12,hwupload",
            ])
            pix_fmt_out = None  # Don't set pix_fmt for VAAPI

        # Encoder-specific arguments
        if enc.backend == "nvenc":
            cmd.extend(self._nvenc_args(enc, fps, pix_fmt_out))
        elif enc.backend == "vaapi":
            cmd.extend(self._vaapi_args(enc, fps))
        elif enc.backend == "amf":
            cmd.extend(self._amf_args(enc, fps, pix_fmt_out))
        elif enc.codec == "av1":
            cmd.extend(self._svtav1_args(fps, pix_fmt_out))
        elif enc.codec == "h265":
            cmd.extend(self._h265_sw_args(fps, pix_fmt_out))
        else:
            cmd.extend(self._h264_sw_args(fps, pix_fmt_out))

        # Output format
        if enc.codec == "av1":
            cmd.extend(["-f", "ivf", "pipe:1"])
        elif enc.codec == "h265":
            cmd.extend(["-f", "hevc", "pipe:1"])
        else:
            cmd.extend(["-f", "h264", "pipe:1"])

        return cmd

    def _find_vaapi_device(self) -> str:
        """Find the VAAPI DRM render node."""
        for path in ["/dev/dri/renderD128", "/dev/dri/renderD129"]:
            if os.path.exists(path):
                return path
        return "/dev/dri/renderD128"

    # ---- NVENC (NVIDIA) ----

    def _nvenc_args(self, enc: HWEncoder, fps: int, pix_fmt: Optional[str]) -> list:
        s = self.settings
        args = ["-c:v", enc.name]

        if pix_fmt:
            args.extend(["-pix_fmt", pix_fmt])

        # NVENC preset: p1 (fastest) to p7 (best quality)
        if s.quality_bias < 0.3:
            args.extend(["-preset", "p1"])
        elif s.quality_bias < 0.6:
            args.extend(["-preset", "p4"])
        elif s.quality_bias < 0.8:
            args.extend(["-preset", "p5"])
        else:
            args.extend(["-preset", "p7"])

        args.extend(["-tune", "ll"])  # Low-latency tune

        if s.force_lossless and enc.supports_lossless:
            args.extend(["-rc", "lossless"])
            if enc.codec == "h264" and pix_fmt == "yuv444p":
                args.extend(["-profile:v", "high444p"])
        else:
            # Constant quality mode
            crf = s.effective_crf()
            args.extend(["-rc", "constqp", "-qp", str(crf)])

            if enc.codec == "h264":
                if pix_fmt == "yuv444p":
                    args.extend(["-profile:v", "high444p"])
                else:
                    args.extend(["-profile:v", "high"])
            elif enc.codec == "h265":
                if pix_fmt == "yuv444p":
                    args.extend(["-profile:v", "rext"])

        # Low-latency settings
        args.extend([
            "-g", str(fps * 2),   # Keyframe every 2 seconds
            "-bf", "0",           # No B-frames
            "-zerolatency", "1",
            "-rc-lookahead", "0",
            "-delay", "0",
        ])

        # Bitrate cap
        max_bitrate = int(s.max_bandwidth_mbps * 1000)
        args.extend(["-maxrate", f"{max_bitrate}k", "-bufsize", f"{max_bitrate}k"])

        return args

    # ---- VAAPI (Intel/AMD Linux) ----

    def _vaapi_args(self, enc: HWEncoder, fps: int) -> list:
        s = self.settings
        args = ["-c:v", enc.name]

        # VAAPI uses global_quality for CQ mode
        qp = s.effective_crf()
        args.extend(["-global_quality", str(qp)])

        # GOP and latency
        args.extend([
            "-g", str(fps * 2),
            "-bf", "0",
        ])

        if enc.codec == "h264":
            args.extend(["-profile:v", "high"])
        elif enc.codec == "h265":
            args.extend(["-profile:v", "main"])

        max_bitrate = int(s.max_bandwidth_mbps * 1000)
        args.extend(["-maxrate", f"{max_bitrate}k", "-bufsize", f"{max_bitrate}k"])

        return args

    # ---- AMF (AMD) ----

    def _amf_args(self, enc: HWEncoder, fps: int, pix_fmt: Optional[str]) -> list:
        s = self.settings
        args = ["-c:v", enc.name]

        if pix_fmt:
            args.extend(["-pix_fmt", pix_fmt])

        # AMF quality preset
        if s.quality_bias < 0.5:
            args.extend(["-quality", "speed"])
        else:
            args.extend(["-quality", "quality"])

        # Rate control
        qp = s.effective_crf()
        args.extend(["-rc", "cqp", "-qp_i", str(qp), "-qp_p", str(qp)])

        args.extend([
            "-g", str(fps * 2),
            "-bf", "0",
        ])

        max_bitrate = int(s.max_bandwidth_mbps * 1000)
        args.extend(["-maxrate", f"{max_bitrate}k", "-bufsize", f"{max_bitrate}k"])

        return args

    # ---- Software H.264 (libx264) ----

    def _h264_sw_args(self, fps: int, pix_fmt: str) -> list:
        s = self.settings
        crf = s.effective_crf()
        preset = s.effective_preset()

        args = [
            "-c:v", "libx264",
            "-preset", preset,
            "-tune", "zerolatency",
            "-pix_fmt", pix_fmt,
        ]

        if s.force_lossless:
            args.extend(["-qp", "0", "-profile:v", "high444"])
        else:
            args.extend(["-crf", str(crf)])
            if pix_fmt == "yuv444p":
                args.extend(["-profile:v", "high444"])
            elif pix_fmt == "yuv422p":
                args.extend(["-profile:v", "high422"])
            else:
                args.extend(["-profile:v", "high"])

        args.extend([
            "-g", str(fps * 2),
            "-bf", "0",
            "-rc-lookahead", "0",
            "-flags", "+cgop",
            "-sc_threshold", "0",
        ])

        if s.quality_bias > 0.6:
            args.extend(["-aq-mode", "2", "-aq-strength", "1.2"])
        else:
            args.extend(["-aq-mode", "1", "-aq-strength", "0.8"])

        max_bitrate = int(s.max_bandwidth_mbps * 1000)
        args.extend(["-maxrate", f"{max_bitrate}k", "-bufsize", f"{max_bitrate}k"])

        return args

    # ---- Software H.265 (libx265) ----

    def _h265_sw_args(self, fps: int, pix_fmt: str) -> list:
        s = self.settings
        crf = s.effective_crf()
        preset = s.effective_preset()

        args = [
            "-c:v", "libx265",
            "-preset", preset,
            "-pix_fmt", pix_fmt,
        ]

        if s.force_lossless:
            args.extend(["-x265-params", "lossless=1"])
        else:
            args.extend(["-crf", str(crf)])

        x265_params = [
            f"keyint={fps * 2}",
            "bframes=0",
            "rc-lookahead=0",
            "scenecut=0",
            "no-open-gop=1",
        ]
        if s.quality_bias > 0.6:
            x265_params.append("aq-mode=2")
        else:
            x265_params.append("aq-mode=1")

        args.extend(["-x265-params", ":".join(x265_params)])

        max_bitrate = int(s.max_bandwidth_mbps * 1000)
        args.extend(["-maxrate", f"{max_bitrate}k", "-bufsize", f"{max_bitrate}k"])

        return args

    # ---- Software AV1 (SVT-AV1) ----

    def _svtav1_args(self, fps: int, pix_fmt: str) -> list:
        s = self.settings

        args = [
            "-c:v", "libsvtav1",
            "-pix_fmt", pix_fmt if pix_fmt != "yuv444p" else "yuv420p",  # SVT-AV1 doesn't support 444
        ]

        crf = s.effective_crf()
        args.extend(["-crf", str(crf)])

        # SVT-AV1 preset: 0 (slowest) to 13 (fastest)
        # For real-time, we need 8+ (fast presets)
        if s.quality_bias < 0.3:
            svt_preset = 12
        elif s.quality_bias < 0.6:
            svt_preset = 10
        elif s.quality_bias < 0.8:
            svt_preset = 8
        else:
            svt_preset = 6

        args.extend(["-preset", str(svt_preset)])

        # Low-latency: single tile row, no look-ahead
        args.extend([
            "-svtav1-params",
            f"tile-rows=0:tile-columns=0:lookahead=0:scd=0:keyint={fps * 2}",
        ])

        args.extend(["-g", str(fps * 2)])

        max_bitrate = int(s.max_bandwidth_mbps * 1000)
        args.extend(["-maxrate", f"{max_bitrate}k", "-bufsize", f"{max_bitrate}k"])

        return args

    # ---- FFmpeg process management ----

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

        self._reader_thread = threading.Thread(
            target=self._read_output,
            daemon=True,
            name="encoder-reader",
        )
        self._reader_thread.start()

    def _read_output(self):
        """Read encoded data from FFmpeg stdout."""
        enc = self._active_encoder
        if enc is None:
            logger.error("No active encoder set — cannot read output")
            return

        if enc.codec == "av1":
            self._read_ivf_output()
        elif enc.codec == "h265":
            self._read_hevc_output()
        else:
            self._read_h264_output()

    def _read_h264_output(self):
        """Read H.264 NAL units delimited by start codes."""
        buf = bytearray()
        START_CODE = b'\x00\x00\x00\x01'

        try:
            while self._running and self._process and self._process.poll() is None:
                chunk = self._process.stdout.read(65536)
                if not chunk:
                    break
                buf.extend(chunk)

                while True:
                    idx = buf.find(START_CODE, 4)
                    if idx < 0:
                        break

                    nal_data = bytes(buf[:idx])
                    buf = buf[idx:]

                    if len(nal_data) > 4:
                        is_keyframe = self._is_h264_keyframe(nal_data)
                        self._total_bytes += len(nal_data)
                        if self._on_encoded_frame:
                            self._on_encoded_frame(nal_data, is_keyframe)

        except Exception as e:
            if self._running:
                logger.error("H264 reader error: %s", e)

    def _read_hevc_output(self):
        """Read H.265/HEVC NAL units delimited by start codes."""
        buf = bytearray()
        START_CODE = b'\x00\x00\x00\x01'

        try:
            while self._running and self._process and self._process.poll() is None:
                chunk = self._process.stdout.read(65536)
                if not chunk:
                    break
                buf.extend(chunk)

                while True:
                    idx = buf.find(START_CODE, 4)
                    if idx < 0:
                        break

                    nal_data = bytes(buf[:idx])
                    buf = buf[idx:]

                    if len(nal_data) > 4:
                        is_keyframe = self._is_hevc_keyframe(nal_data)
                        self._total_bytes += len(nal_data)
                        if self._on_encoded_frame:
                            self._on_encoded_frame(nal_data, is_keyframe)

        except Exception as e:
            if self._running:
                logger.error("HEVC reader error: %s", e)

    def _read_ivf_output(self):
        """Read AV1 frames from IVF container."""
        try:
            # Read IVF file header (32 bytes)
            header = self._process.stdout.read(32)
            if not header or len(header) < 32:
                return

            while self._running and self._process and self._process.poll() is None:
                # IVF frame header: 12 bytes (4 size + 8 timestamp)
                frame_hdr = self._process.stdout.read(12)
                if not frame_hdr or len(frame_hdr) < 12:
                    break

                frame_size = struct.unpack("<I", frame_hdr[:4])[0]
                if frame_size <= 0 or frame_size > 10 * 1024 * 1024:
                    break

                frame_data = self._process.stdout.read(frame_size)
                if not frame_data or len(frame_data) < frame_size:
                    break

                # AV1 keyframe detection: check OBU header
                is_keyframe = self._is_av1_keyframe(frame_data)
                self._total_bytes += len(frame_data)
                if self._on_encoded_frame:
                    self._on_encoded_frame(frame_data, is_keyframe)

        except Exception as e:
            if self._running:
                logger.error("AV1/IVF reader error: %s", e)

    @staticmethod
    def _is_h264_keyframe(nal_data: bytes) -> bool:
        if len(nal_data) < 5:
            return False
        offset = 4 if nal_data[:4] == b'\x00\x00\x00\x01' else 3
        if offset >= len(nal_data):
            return False
        nal_type = nal_data[offset] & 0x1F
        return nal_type == 5  # IDR slice

    @staticmethod
    def _is_hevc_keyframe(nal_data: bytes) -> bool:
        if len(nal_data) < 5:
            return False
        offset = 4 if nal_data[:4] == b'\x00\x00\x00\x01' else 3
        if offset >= len(nal_data):
            return False
        # HEVC NAL type is bits 1-6 of first byte
        nal_type = (nal_data[offset] >> 1) & 0x3F
        # IDR types: 19 (IDR_W_RADL), 20 (IDR_N_LP)
        return nal_type in (19, 20)

    @staticmethod
    def _is_av1_keyframe(frame_data: bytes) -> bool:
        if len(frame_data) < 2:
            return False
        # AV1 OBU: first byte is obu_type (bits 3-6) and other flags
        # For a keyframe, the sequence header OBU is followed by a key frame OBU
        # Simple heuristic: check first OBU type
        obu_type = (frame_data[0] >> 3) & 0x0F
        # OBU_SEQUENCE_HEADER = 1 usually precedes key frames
        # OBU_FRAME = 6, OBU_FRAME_HEADER = 3
        if obu_type == 1:  # Sequence header = start of a keyframe group
            return True
        if obu_type in (3, 6) and len(frame_data) > 2:
            # Check frame_type in frame header: 0 = KEY_FRAME
            # The show_existing_frame flag is bit 0 of the uncompressed header
            # This is a simplified check
            has_size_field = (frame_data[0] >> 1) & 1
            idx = 2 if has_size_field else 1
            if idx < len(frame_data):
                frame_type = (frame_data[idx] >> 5) & 0x03
                return frame_type == 0
        return False

    def feed_frame(self, bgra_data: bytes):
        """Feed a raw BGRA frame to the encoder."""
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
        """Update encoder settings. Restarts FFmpeg if needed."""
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
        """Force the encoder to emit a keyframe by restarting the FFmpeg process."""
        if not self._running or not self._on_encoded_frame:
            return
        logger.info("Keyframe requested — restarting encoder")
        callback = self._on_encoded_frame
        self.stop()
        self._running = True
        self._start_time = time.time()
        self._start_ffmpeg()
        self._on_encoded_frame = callback

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

        logger.info("Encoder stopped (encoded %d frames, backend=%s)",
                     self._frame_count, self.active_backend)


class JpegFallbackEncoder:
    """Simple JPEG encoder for environments without FFmpeg."""

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

    Returns dict with encoder info for UI/logging.
    """
    available = detect_encoders()

    result = {
        "available": False,
        "h264": len(available.get("h264", [])) > 0,
        "h265": len(available.get("h265", [])) > 0,
        "av1": len(available.get("av1", [])) > 0,
        "h264_444": False,
        "encoders": {},
        "hw_backends": set(),
    }

    # Check FFmpeg itself
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
        result["available"] = True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return result

    for codec, encoders in available.items():
        result["encoders"][codec] = [
            {"name": e.name, "backend": e.backend,
             "supports_444": e.supports_444, "supports_lossless": e.supports_lossless}
            for e in encoders
        ]
        for e in encoders:
            if e.backend != "software":
                result["hw_backends"].add(e.backend)
            if e.supports_444:
                result["h264_444"] = True

    result["hw_backends"] = list(result["hw_backends"])
    return result
