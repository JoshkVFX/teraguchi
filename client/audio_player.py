"""
Audio player for Teragucci client.

Receives raw PCM s16le audio from the server and plays via Qt QAudioSink.
"""

import logging
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
    Plays raw PCM s16le audio from the Teragucci server.

    The server captures system audio via PulseAudio and sends raw
    PCM (signed 16-bit little-endian, 48kHz, stereo) chunks.
    """

    def __init__(self, sample_rate: int = 48000, channels: int = 2):
        self.sample_rate = sample_rate
        self.channels = channels
        self._sink: Optional[QAudioSink] = None
        self._io_device: Optional[QIODevice] = None
        self._started = False
        self._frame_count = 0

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
        self._sink.setBufferSize(self.sample_rate * self.channels * 2)  # 1s buffer
        self._io_device = self._sink.start()
        self._started = True
        logger.info("Audio player started (%dHz, %dch, s16le)", self.sample_rate, self.channels)

    def feed(self, codec: int, timestamp_ms: int, data: bytes):
        """
        Feed a raw PCM audio chunk from the server.

        Data is s16le, 48kHz, stereo — written directly to QAudioSink.
        """
        if not self._started or not self._io_device:
            return

        self._frame_count += 1
        if self._frame_count <= 3:
            logger.info("Audio frame %d: %d bytes", self._frame_count, len(data))

        self._io_device.write(QByteArray(data))

    def stop(self):
        """Stop audio playback."""
        self._started = False
        if self._sink:
            self._sink.stop()
            self._sink = None
        self._io_device = None
        logger.info("Audio player stopped")
