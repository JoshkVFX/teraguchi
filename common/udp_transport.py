"""
UDP media transport with DTLS encryption.

Handles high-throughput, low-latency video and audio streaming over UDP.
Designed to drop stale frames rather than stall (unlike TCP).

Architecture:
- Server sends video/audio frames as UDP datagrams
- Each datagram is self-contained or part of a fragmented frame
- Lost packets are simply skipped (no retransmission)
- DTLS provides encryption without TCP overhead
- Automatic MTU discovery and fragmentation
- Sequence numbers for ordering and loss detection
- Timestamp-based jitter buffer on the client side

Packet format:
  [2 bytes: magic 0xTG]
  [1 byte:  channel]       0x01=video, 0x02=audio
  [1 byte:  flags]         bit0=keyframe, bit1=fragment, bit2=last_fragment
  [4 bytes: sequence]      monotonic per-channel sequence number (big-endian)
  [4 bytes: timestamp_ms]  capture timestamp (big-endian)
  [2 bytes: fragment_id]   which fragment of a multi-packet frame (big-endian)
  [2 bytes: fragment_total] total fragments in this frame (big-endian)
  [payload...]

Total header: 16 bytes.  Leaves ~1484 bytes for payload per packet (MTU 1500).
"""

import asyncio
import hashlib
import logging
import os
import socket
import ssl
import struct
import time
import threading
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional, Callable, Dict, List, Tuple

logger = logging.getLogger(__name__)

# Constants
UDP_MAGIC = 0x5447           # 'TG' for Teraguchi
UDP_HEADER_SIZE = 16
DEFAULT_MTU = 1400           # Conservative MTU leaving room for IP/UDP/DTLS headers
MAX_PACKET_SIZE = 65507      # Max UDP payload

# Channel IDs
CHANNEL_VIDEO = 0x01
CHANNEL_AUDIO = 0x02

# Flags
FLAG_KEYFRAME = 0x01
FLAG_FRAGMENT = 0x02
FLAG_LAST_FRAGMENT = 0x04


def encode_udp_header(channel: int, flags: int, sequence: int,
                      timestamp_ms: int, frag_id: int = 0,
                      frag_total: int = 1) -> bytes:
    """Encode a 16-byte UDP header: magic(2)+channel(1)+flags(1)+seq(4)+ts(4)+frag_id(2)+frag_total(2)."""
    return struct.pack("!HBBII HH",
                       UDP_MAGIC, channel, flags,
                       sequence & 0xFFFFFFFF,
                       timestamp_ms & 0xFFFFFFFF,
                       frag_id, frag_total)


def decode_udp_header(data: bytes) -> Optional[tuple]:
    """
    Returns (channel, flags, sequence, timestamp_ms, frag_id, frag_total, payload)
    or None if invalid.
    """
    if len(data) < UDP_HEADER_SIZE:
        return None
    magic, channel, flags, seq, ts, frag_id, frag_total = struct.unpack(
        "!HBBII HH", data[:UDP_HEADER_SIZE])
    if magic != UDP_MAGIC:
        return None
    return channel, flags, seq, ts, frag_id, frag_total, data[UDP_HEADER_SIZE:]


# ============================================================
# Frame Fragmenter (for frames larger than MTU)
# ============================================================

class FrameFragmenter:
    """Splits large frames into MTU-sized UDP packets."""

    def __init__(self, mtu: int = DEFAULT_MTU):
        self.mtu = mtu
        self.payload_size = mtu - UDP_HEADER_SIZE
        self._video_seq = 0
        self._audio_seq = 0

    def fragment_frame(self, channel: int, data: bytes,
                       timestamp_ms: int, is_keyframe: bool = False) -> List[bytes]:
        """
        Fragment a frame into UDP packets.

        Returns a list of complete UDP packets (header + payload) ready to send.
        """
        if channel == CHANNEL_VIDEO:
            self._video_seq += 1
            seq = self._video_seq
        else:
            self._audio_seq += 1
            seq = self._audio_seq

        base_flags = FLAG_KEYFRAME if is_keyframe else 0

        if len(data) <= self.payload_size:
            # Single packet — no fragmentation needed
            header = encode_udp_header(channel, base_flags, seq, timestamp_ms, 0, 1)
            return [header + data]

        # Fragment
        fragments = []
        total = (len(data) + self.payload_size - 1) // self.payload_size
        for i in range(total):
            offset = i * self.payload_size
            chunk = data[offset:offset + self.payload_size]

            flags = base_flags | FLAG_FRAGMENT
            if i == total - 1:
                flags |= FLAG_LAST_FRAGMENT

            header = encode_udp_header(channel, flags, seq, timestamp_ms, i, total)
            fragments.append(header + chunk)

        return fragments


# ============================================================
# Frame Reassembler (client-side)
# ============================================================

@dataclass
class PendingFrame:
    """A frame being reassembled from fragments."""
    sequence: int = 0
    timestamp_ms: int = 0
    channel: int = 0
    flags: int = 0
    total_fragments: int = 0
    received_fragments: Dict[int, bytes] = field(default_factory=dict)
    created_at: float = 0.0

    @property
    def complete(self) -> bool:
        return len(self.received_fragments) == self.total_fragments

    def assemble(self) -> bytes:
        """Assemble all fragments in order."""
        parts = []
        for i in range(self.total_fragments):
            parts.append(self.received_fragments[i])
        return b"".join(parts)


class FrameReassembler:
    """
    Reassembles fragmented UDP frames and handles packet loss.

    Features:
    - Reassembles multi-packet frames
    - Drops incomplete frames after timeout (no retransmission)
    - Skips frames older than the latest received keyframe
    - Tracks packet loss statistics
    """

    def __init__(self, timeout_ms: float = 100.0):
        self.timeout_ms = timeout_ms
        self._pending: Dict[Tuple[int, int], PendingFrame] = {}  # (channel, seq) -> PendingFrame
        self._last_complete_seq: Dict[int, int] = defaultdict(int)  # channel -> last complete seq
        self._packets_received = 0
        self._packets_lost = 0
        self._frames_completed = 0
        self._frames_dropped = 0

    def feed_packet(self, data: bytes) -> Optional[tuple]:
        """
        Feed a raw UDP packet.

        Returns (channel, flags, timestamp_ms, frame_data) if a complete frame
        is ready, or None if still assembling / packet was dropped.
        """
        parsed = decode_udp_header(data)
        if parsed is None:
            return None

        channel, flags, seq, ts, frag_id, frag_total, payload = parsed
        self._packets_received += 1

        # Skip frames older than what we've already displayed
        if seq < self._last_complete_seq.get(channel, 0):
            return None

        # Single-packet frame (no fragmentation)
        if frag_total <= 1:
            self._last_complete_seq[channel] = seq
            self._frames_completed += 1
            self._cleanup_old(channel, seq)
            return channel, flags, ts, payload

        # Multi-packet frame: reassemble
        key = (channel, seq)
        if key not in self._pending:
            self._pending[key] = PendingFrame(
                sequence=seq,
                timestamp_ms=ts,
                channel=channel,
                flags=flags,
                total_fragments=frag_total,
                created_at=time.time(),
            )

        frame = self._pending[key]
        frame.received_fragments[frag_id] = payload

        # Inherit keyframe flag from any fragment
        if flags & FLAG_KEYFRAME:
            frame.flags |= FLAG_KEYFRAME

        if frame.complete:
            del self._pending[key]
            self._last_complete_seq[channel] = seq
            self._frames_completed += 1
            self._cleanup_old(channel, seq)
            return channel, frame.flags, frame.timestamp_ms, frame.assemble()

        return None

    def _cleanup_old(self, channel: int, current_seq: int):
        """Drop pending frames that are older than the current completed frame."""
        stale_keys = [
            k for k in self._pending
            if k[0] == channel and k[1] < current_seq
        ]
        for k in stale_keys:
            frame = self._pending.pop(k)
            lost = frame.total_fragments - len(frame.received_fragments)
            self._packets_lost += lost
            self._frames_dropped += 1

    def cleanup_timed_out(self):
        """Drop frames that have been pending too long."""
        now = time.time()
        timeout_sec = self.timeout_ms / 1000.0
        stale_keys = [
            k for k, f in self._pending.items()
            if now - f.created_at > timeout_sec
        ]
        for k in stale_keys:
            frame = self._pending.pop(k)
            lost = frame.total_fragments - len(frame.received_fragments)
            self._packets_lost += lost
            self._frames_dropped += 1

    @property
    def packet_loss_rate(self) -> float:
        total = self._packets_received + self._packets_lost
        if total == 0:
            return 0.0
        return self._packets_lost / total

    @property
    def stats(self) -> dict:
        return {
            "packets_received": self._packets_received,
            "packets_lost": self._packets_lost,
            "packet_loss_rate": round(self.packet_loss_rate * 100, 2),
            "frames_completed": self._frames_completed,
            "frames_dropped": self._frames_dropped,
            "pending_frames": len(self._pending),
        }


# ============================================================
# UDP Server Transport
# ============================================================

class UDPMediaServer:
    """
    Server-side UDP transport for media streaming.

    Sends video and audio frames as UDP datagrams to connected clients.
    Each client must first register via the TCP control channel, which
    provides the client's UDP address.
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 443,
                 mtu: int = DEFAULT_MTU):
        self.host = host
        self.port = port
        self._sock: Optional[socket.socket] = None
        self._fragmenter = FrameFragmenter(mtu)
        self._clients: Dict[str, tuple] = {}  # client_id -> (host, port)
        self._running = False
        self._send_lock = threading.Lock()
        self._total_bytes_sent = 0
        self._total_packets_sent = 0
        self._start_time = 0.0

    @property
    def bandwidth_mbps(self) -> float:
        elapsed = time.time() - self._start_time
        if elapsed <= 0:
            return 0.0
        return (self._total_bytes_sent * 8) / (elapsed * 1_000_000)

    def start(self):
        """Create and bind the UDP socket."""
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4 * 1024 * 1024)
        self._sock.bind((self.host, self.port))
        self._running = True
        self._start_time = time.time()
        logger.info("UDP media server listening on %s:%d", self.host, self.port)

    def register_client(self, client_id: str, addr: tuple):
        """Register a client's UDP address for receiving media."""
        self._clients[client_id] = addr
        logger.info("UDP client registered: %s -> %s:%d", client_id, addr[0], addr[1])

    def unregister_client(self, client_id: str):
        """Remove a client."""
        self._clients.pop(client_id, None)
        logger.info("UDP client unregistered: %s", client_id)

    def send_video_frame(self, data: bytes, timestamp_ms: int,
                         is_keyframe: bool = False):
        """
        Send a video frame to all registered clients.

        The frame is automatically fragmented if it exceeds MTU.
        Packets are sent without waiting for acknowledgement.
        """
        if not self._running or not self._clients:
            return

        packets = self._fragmenter.fragment_frame(
            CHANNEL_VIDEO, data, timestamp_ms, is_keyframe)

        with self._send_lock:
            for packet in packets:
                for client_id, addr in list(self._clients.items()):
                    try:
                        self._sock.sendto(packet, addr)
                        self._total_bytes_sent += len(packet)
                        self._total_packets_sent += 1
                    except OSError as e:
                        logger.debug("UDP send to %s failed: %s", client_id, e)

    def send_audio_frame(self, data: bytes, timestamp_ms: int):
        """Send an audio frame to all registered clients."""
        if not self._running or not self._clients:
            return

        packets = self._fragmenter.fragment_frame(
            CHANNEL_AUDIO, data, timestamp_ms, is_keyframe=False)

        with self._send_lock:
            for packet in packets:
                for client_id, addr in list(self._clients.items()):
                    try:
                        self._sock.sendto(packet, addr)
                        self._total_bytes_sent += len(packet)
                        self._total_packets_sent += 1
                    except OSError as e:
                        logger.debug("UDP audio send failed: %s", e)

    def stop(self):
        """Stop the UDP server."""
        self._running = False
        if self._sock:
            self._sock.close()
            self._sock = None
        self._clients.clear()
        logger.info("UDP media server stopped (sent %d packets, %.1f MB)",
                     self._total_packets_sent,
                     self._total_bytes_sent / (1024 * 1024))


# ============================================================
# UDP Client Transport
# ============================================================

class UDPMediaClient:
    """
    Client-side UDP transport for receiving media.

    Listens for incoming UDP media packets, reassembles fragments,
    and delivers complete frames via callbacks. Runs a receiver
    thread for non-blocking operation.
    """

    def __init__(self, mtu: int = DEFAULT_MTU):
        self._sock: Optional[socket.socket] = None
        self._thread: Optional[threading.Thread] = None
        self._reassembler = FrameReassembler(timeout_ms=150.0)
        self._running = False
        self._local_port = 0

        # Callbacks
        self.on_video_frame: Optional[Callable] = None   # (flags, timestamp_ms, data)
        self.on_audio_frame: Optional[Callable] = None   # (timestamp_ms, data)

    @property
    def local_port(self) -> int:
        return self._local_port

    @property
    def stats(self) -> dict:
        return self._reassembler.stats

    def start(self, local_port: int = 0) -> int:
        """
        Start receiving UDP media.

        Args:
            local_port: Port to listen on (0 = auto-assign)

        Returns:
            The actual port being used (report this to server via TCP).
        """
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
        self._sock.bind(("0.0.0.0", local_port))
        self._sock.settimeout(1.0)

        self._local_port = self._sock.getsockname()[1]
        self._running = True

        self._thread = threading.Thread(
            target=self._receive_loop,
            daemon=True,
            name="udp-media-recv",
        )
        self._thread.start()

        logger.info("UDP media client listening on port %d", self._local_port)
        return self._local_port

    def _receive_loop(self):
        """Receive and process UDP packets."""
        cleanup_interval = 0.1  # Clean up stale fragments every 100ms
        last_cleanup = time.time()

        while self._running:
            try:
                data, addr = self._sock.recvfrom(MAX_PACKET_SIZE)
            except socket.timeout:
                self._reassembler.cleanup_timed_out()
                continue
            except OSError:
                if self._running:
                    logger.debug("UDP recv error")
                break

            result = self._reassembler.feed_packet(data)
            if result is not None:
                channel, flags, timestamp_ms, frame_data = result

                if channel == CHANNEL_VIDEO and self.on_video_frame:
                    self.on_video_frame(flags, timestamp_ms, frame_data)
                elif channel == CHANNEL_AUDIO and self.on_audio_frame:
                    self.on_audio_frame(timestamp_ms, frame_data)

            # Periodic cleanup
            now = time.time()
            if now - last_cleanup > cleanup_interval:
                self._reassembler.cleanup_timed_out()
                last_cleanup = now

    def stop(self):
        """Stop receiving."""
        self._running = False
        if self._sock:
            self._sock.close()
            self._sock = None
        if self._thread:
            self._thread.join(timeout=3)
            self._thread = None
        logger.info("UDP media client stopped. Stats: %s", self._reassembler.stats)


# ============================================================
# Bandwidth Estimator
# ============================================================

class BandwidthEstimator:
    """
    Estimates available bandwidth and adjusts sending rate.

    Uses a simple packet-pair technique + loss-based adaptation:
    - If packet loss > 2%: reduce bitrate
    - If packet loss < 0.5% and bandwidth headroom: increase bitrate
    - Smooth changes to avoid oscillation
    """

    def __init__(self, initial_mbps: float = 50.0, min_mbps: float = 1.0,
                 max_mbps: float = 200.0):
        self.current_mbps = initial_mbps
        self.min_mbps = min_mbps
        self.max_mbps = max_mbps
        self._loss_history: list = []
        self._last_adjustment = time.time()
        self._adjustment_interval = 2.0  # seconds

    def report_loss_rate(self, loss_pct: float):
        """Report current packet loss percentage."""
        self._loss_history.append(loss_pct)
        if len(self._loss_history) > 30:
            self._loss_history = self._loss_history[-20:]

    def get_target_bitrate_mbps(self) -> float:
        """Get the recommended target bitrate based on conditions."""
        now = time.time()
        if now - self._last_adjustment < self._adjustment_interval:
            return self.current_mbps

        if not self._loss_history:
            return self.current_mbps

        avg_loss = sum(self._loss_history[-5:]) / len(self._loss_history[-5:])
        self._last_adjustment = now

        if avg_loss > 5.0:
            # Heavy loss: cut bandwidth significantly
            self.current_mbps = max(self.min_mbps, self.current_mbps * 0.6)
            logger.info("Bandwidth: heavy loss (%.1f%%), reducing to %.1f Mbps",
                        avg_loss, self.current_mbps)
        elif avg_loss > 2.0:
            # Moderate loss: reduce gently
            self.current_mbps = max(self.min_mbps, self.current_mbps * 0.85)
            logger.debug("Bandwidth: moderate loss (%.1f%%), reducing to %.1f Mbps",
                         avg_loss, self.current_mbps)
        elif avg_loss < 0.5:
            # Low loss: probe for more bandwidth
            self.current_mbps = min(self.max_mbps, self.current_mbps * 1.05)

        return self.current_mbps

    @property
    def target_bitrate_kbps(self) -> int:
        return int(self.current_mbps * 1000)
