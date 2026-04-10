"""
Audio player for Teraguchi client.

Receives raw PCM s16le audio from the server and plays via Qt QAudioSink.
Keeps latency low by using a small buffer and dropping old data if behind.
"""

import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from PySide6.QtMultimedia import QAudioFormat, QAudioSink, QMediaDevices
    from PySide6.QtCore import QIODevice, QByteArray
    QT_AUDIO_AVAILABLE = True
except ImportError:
    QT_AUDIO_AVAILABLE = False
    logger.warning("PySide6.QtMultimedia not available — audio playback disabled")


class AudioPlayer:
    """
    Plays raw PCM s16le audio from the Teraguchi server.

    Keeps latency low (~100ms) by using a small Qt audio buffer
    and skipping frames if the buffer gets too full.
    """

    # Target latency in milliseconds
    TARGET_LATENCY_MS = 100
    # Max buffered audio before we skip frames (ms)
    MAX_BUFFER_MS = 200

    def __init__(self, sample_rate: int = 48000, channels: int = 2):
        self.sample_rate = sample_rate
        self.channels = channels
        self._sink: Optional[QAudioSink] = None
        self._io_device: Optional[QIODevice] = None
        self._started = False
        self._frame_count = 0
        # Bytes per millisecond of audio
        self._bytes_per_ms = sample_rate * channels * 2 // 1000

    @property
    def available(self) -> bool:
        return QT_AUDIO_AVAILABLE

    def start(self):
        """Initialize Qt audio output."""
        if not QT_AUDIO_AVAILABLE:
            logger.warning("Audio player not available (no Qt Multimedia)")
            return

        fmt = QAudioFormat()
        fmt.setSampleRate(self.sample_rate)
        fmt.setChannelCount(self.channels)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)

        device = QMediaDevices.defaultAudioOutput()
        if device.isNull():
            logger.warning("No audio output device found")
            return

        logger.info("Audio output device: %s", device.description())

        self._sink = QAudioSink(device, fmt)
        # Small buffer for low latency
        buf_bytes = self._bytes_per_ms * self.TARGET_LATENCY_MS
        self._sink.setBufferSize(buf_bytes)
        self._io_device = self._sink.start()
        self._started = True
        actual_buf = self._sink.bufferSize()
        logger.info("Audio player started (%dHz, %dch, buffer=%d bytes / %dms)",
                     self.sample_rate, self.channels, actual_buf,
                     actual_buf // self._bytes_per_ms)

    def feed(self, codec: int, timestamp_ms: int, data: bytes):
        """Feed a raw PCM audio chunk from the server."""
        if not self._started or not self._io_device:
            return

        self._frame_count += 1

        # Check how much is already buffered
        if self._sink:
            buf_size = self._sink.bufferSize()
            free = self._sink.bytesFree()
            buffered = buf_size - free
            buffered_ms = buffered // self._bytes_per_ms

            # If too far behind, skip this frame to catch up
            if buffered_ms > self.MAX_BUFFER_MS:
                if self._frame_count % 100 == 0:
                    logger.debug("Audio buffer full (%dms), skipping", buffered_ms)
                return

        self._io_device.write(QByteArray(data))

    def stop(self):
        """Stop audio playback."""
        self._started = False
        if self._sink:
            self._sink.stop()
            self._sink = None
        self._io_device = None
        logger.info("Audio player stopped")
