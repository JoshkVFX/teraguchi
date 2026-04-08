"""
Audio player for Teragucci client.

Receives OGG/Opus chunks from the server, decodes with PyAV,
and plays PCM audio via Qt's QAudioSink.
"""

import io
import logging
import threading
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from PySide6.QtMultimedia import QAudioFormat, QAudioSink, QMediaDevices
    from PySide6.QtCore import QBuffer, QIODevice, QByteArray
    QT_AUDIO_AVAILABLE = True
except ImportError:
    QT_AUDIO_AVAILABLE = False
    logger.warning("PySide6.QtMultimedia not available — audio playback disabled")

try:
    import av
    PYAV_AVAILABLE = True
except ImportError:
    PYAV_AVAILABLE = False
    logger.warning("PyAV not available — audio decode disabled")


class AudioPlayer:
    """
    Decodes Opus audio from server and plays via Qt audio output.

    The server sends raw OGG/Opus bytestream chunks. We accumulate them
    in a ring buffer and decode with PyAV, then write PCM to QAudioSink.
    """

    def __init__(self, sample_rate: int = 48000, channels: int = 2):
        self.sample_rate = sample_rate
        self.channels = channels
        self._sink: Optional[QAudioSink] = None
        self._io_device: Optional[QIODevice] = None
        self._decoder_thread: Optional[threading.Thread] = None
        self._running = False
        self._ogg_buffer = io.BytesIO()
        self._lock = threading.Lock()
        self._started = False

    @property
    def available(self) -> bool:
        return QT_AUDIO_AVAILABLE and PYAV_AVAILABLE

    def start(self):
        """Initialize Qt audio output."""
        if not self.available:
            logger.warning("Audio player not available")
            return

        fmt = QAudioFormat()
        fmt.setSampleRate(self.sample_rate)
        fmt.setChannelCount(self.channels)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)

        device = QMediaDevices.defaultAudioOutput()
        if not device.isNull():
            logger.info("Audio output device: %s", device.description())
        else:
            logger.warning("No audio output device found")
            return

        self._sink = QAudioSink(device, fmt)
        self._sink.setBufferSize(self.sample_rate * self.channels * 2)  # 1s buffer
        self._io_device = self._sink.start()
        self._started = True
        logger.info("Audio player started (%dHz, %dch)", self.sample_rate, self.channels)

    def feed(self, codec: int, timestamp_ms: int, data: bytes):
        """
        Feed an audio chunk from the server.

        The server sends OGG/Opus container chunks. We decode them
        with PyAV and write raw PCM to the audio output.
        """
        if not self._started or not self._io_device:
            return

        try:
            # Decode OGG/Opus chunk with PyAV
            container = av.open(io.BytesIO(data), format='ogg')
            for frame in container.decode(audio=0):
                # Resample to s16 interleaved
                resampler = av.AudioResampler(
                    format='s16',
                    layout='stereo' if self.channels == 2 else 'mono',
                    rate=self.sample_rate,
                )
                resampled = resampler.resample(frame)
                for out_frame in resampled:
                    pcm = bytes(out_frame.planes[0])
                    self._io_device.write(QByteArray(pcm))
            container.close()
        except av.error.InvalidDataError:
            pass  # Incomplete OGG page, will work with next chunk
        except Exception as e:
            if self._started:
                logger.debug("Audio decode error: %s", e)

    def stop(self):
        """Stop audio playback."""
        self._started = False
        if self._sink:
            self._sink.stop()
            self._sink = None
        self._io_device = None
        logger.info("Audio player stopped")
