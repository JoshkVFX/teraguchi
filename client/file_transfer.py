"""
Client-side file transfer — send files to the remote server.

Supports drag-and-drop onto the viewer and manual file picker.
Files are chunked, checksummed, and sent over the existing WebSocket.
"""

import base64
import hashlib
import logging
import os
import uuid
from pathlib import Path
from typing import Optional, Callable

from PySide6.QtCore import QObject, Signal, QThread

logger = logging.getLogger(__name__)

CHUNK_SIZE = 256 * 1024  # 256 KB per chunk


class FileSender(QObject):
    """Sends a file to the server in chunks over the WebSocket."""

    progress = Signal(str, int, int)    # transfer_id, bytes_sent, total
    finished = Signal(str, bool, str)   # transfer_id, success, message
    chunk_ready = Signal(dict)          # JSON message to send

    def __init__(self, parent=None):
        super().__init__(parent)
        self._active: dict[str, "_SendJob"] = {}

    def send_file(self, file_path: str) -> str:
        """Start sending a file. Returns transfer_id."""
        path = Path(file_path)
        if not path.is_file():
            logger.error("Not a file: %s", file_path)
            return ""

        transfer_id = uuid.uuid4().hex[:12]
        file_size = path.stat().st_size

        # Compute checksum
        hasher = hashlib.sha256()
        with open(path, "rb") as f:
            while True:
                chunk = f.read(CHUNK_SIZE)
                if not chunk:
                    break
                hasher.update(chunk)
        checksum = hasher.hexdigest()

        job = _SendJob(
            transfer_id=transfer_id,
            path=path,
            file_size=file_size,
            checksum=checksum,
            offset=0,
        )
        self._active[transfer_id] = job

        # Send offer
        self.chunk_ready.emit({
            "type": "file_offer",
            "transfer_id": transfer_id,
            "filename": path.name,
            "file_size": file_size,
            "checksum": checksum,
        })

        logger.info("Offering file: %s (%d bytes, id=%s)", path.name, file_size, transfer_id)
        return transfer_id

    def handle_response(self, msg: dict):
        """Handle server responses (file_accept, file_ack, file_cancel)."""
        msg_type = msg.get("type")
        transfer_id = msg.get("transfer_id", "")
        job = self._active.get(transfer_id)

        if msg_type == "file_accept":
            if job:
                logger.info("Server accepted file: %s → %s",
                           job.path.name, msg.get("dest_path", ""))
                self._send_chunks(job)

        elif msg_type == "file_ack":
            success = msg.get("success", False)
            error = msg.get("error", "")
            dest = msg.get("dest_path", "")
            if job:
                del self._active[transfer_id]
            if success:
                logger.info("File transfer complete: %s → %s", transfer_id, dest)
                self.finished.emit(transfer_id, True, dest)
            else:
                logger.error("File transfer failed: %s — %s", transfer_id, error)
                self.finished.emit(transfer_id, False, error)

        elif msg_type == "file_cancel":
            reason = msg.get("reason", "cancelled")
            if job:
                del self._active[transfer_id]
            logger.warning("File transfer cancelled: %s — %s", transfer_id, reason)
            self.finished.emit(transfer_id, False, reason)

    def _send_chunks(self, job: "_SendJob"):
        """Read and send all chunks for a file."""
        try:
            with open(job.path, "rb") as f:
                while True:
                    chunk = f.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    self.chunk_ready.emit({
                        "type": "file_chunk",
                        "transfer_id": job.transfer_id,
                        "data": base64.b64encode(chunk).decode("ascii"),
                    })
                    job.offset += len(chunk)
                    self.progress.emit(job.transfer_id, job.offset, job.file_size)

            # Send done
            self.chunk_ready.emit({
                "type": "file_done",
                "transfer_id": job.transfer_id,
            })
            logger.info("All chunks sent for %s (%d bytes)", job.path.name, job.offset)

        except OSError as e:
            logger.error("Error reading file %s: %s", job.path, e)
            self.chunk_ready.emit({
                "type": "file_cancel",
                "transfer_id": job.transfer_id,
            })
            self.finished.emit(job.transfer_id, False, str(e))

    def send_files(self, file_paths: list[str]) -> list[str]:
        """Send multiple files. Returns list of transfer IDs."""
        return [self.send_file(p) for p in file_paths if p]


class _SendJob:
    __slots__ = ('transfer_id', 'path', 'file_size', 'checksum', 'offset')

    def __init__(self, transfer_id, path, file_size, checksum, offset):
        self.transfer_id = transfer_id
        self.path = path
        self.file_size = file_size
        self.checksum = checksum
        self.offset = offset
