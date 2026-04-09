"""
Server-side file transfer handler.

Receives files from the client in chunks and writes them to the
user's home directory (~/Desktop by default, configurable).
"""

import base64
import hashlib
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Max file size: 2 GB
MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024
# Max chunk size: 512 KB (base64 encoded in JSON)
MAX_CHUNK_SIZE = 512 * 1024


class FileReceiver:
    """Handles incoming file transfers from a client."""

    def __init__(self, home_dir: str, uid: int = 0, gid: int = 0):
        self._home = Path(home_dir)
        self._uid = uid
        self._gid = gid
        self._transfers: dict[str, "_Transfer"] = {}

        # Default upload dir: ~/Desktop, fallback to ~/
        self._upload_dir = self._home / "Desktop"
        if not self._upload_dir.is_dir():
            self._upload_dir = self._home

    def handle_message(self, msg: dict) -> Optional[dict]:
        """Process a file transfer message. Returns a response dict or None."""
        msg_type = msg.get("type")

        if msg_type == "file_offer":
            return self._handle_offer(msg)
        elif msg_type == "file_chunk":
            return self._handle_chunk(msg)
        elif msg_type == "file_done":
            return self._handle_done(msg)
        elif msg_type == "file_cancel":
            return self._handle_cancel(msg)
        return None

    def _handle_offer(self, msg: dict) -> dict:
        transfer_id = msg.get("transfer_id", "")
        filename = msg.get("filename", "")
        file_size = msg.get("file_size", 0)
        checksum = msg.get("checksum", "")

        # Validate
        if not filename or not transfer_id:
            return {"type": "file_cancel", "transfer_id": transfer_id,
                    "reason": "Missing filename or transfer_id"}

        if file_size > MAX_FILE_SIZE:
            return {"type": "file_cancel", "transfer_id": transfer_id,
                    "reason": f"File too large ({file_size} bytes, max {MAX_FILE_SIZE})"}

        # Sanitize filename — strip path components, prevent traversal
        safe_name = Path(filename).name
        if not safe_name or safe_name.startswith('.'):
            safe_name = f"upload_{transfer_id[:8]}"

        # Resolve final destination, avoiding overwrites
        dest = self._upload_dir / safe_name
        if dest.exists():
            stem = dest.stem
            suffix = dest.suffix
            counter = 1
            while dest.exists():
                dest = self._upload_dir / f"{stem}_{counter}{suffix}"
                counter += 1

        # Create temp file for writing
        try:
            tmp_fd, tmp_path = tempfile.mkstemp(
                dir=str(self._upload_dir), prefix=f".tg_upload_")
            os.close(tmp_fd)
        except OSError as e:
            return {"type": "file_cancel", "transfer_id": transfer_id,
                    "reason": f"Cannot create temp file: {e}"}

        self._transfers[transfer_id] = _Transfer(
            transfer_id=transfer_id,
            filename=safe_name,
            file_size=file_size,
            expected_checksum=checksum,
            dest_path=dest,
            tmp_path=Path(tmp_path),
            received=0,
        )

        logger.info("File offer accepted: %s (%d bytes) → %s",
                     safe_name, file_size, dest)

        return {"type": "file_accept", "transfer_id": transfer_id,
                "dest_path": str(dest)}

    def _handle_chunk(self, msg: dict) -> Optional[dict]:
        transfer_id = msg.get("transfer_id", "")
        t = self._transfers.get(transfer_id)
        if not t:
            return {"type": "file_cancel", "transfer_id": transfer_id,
                    "reason": "Unknown transfer"}

        data_b64 = msg.get("data", "")
        try:
            data = base64.b64decode(data_b64)
        except Exception:
            self._cleanup_transfer(transfer_id)
            return {"type": "file_cancel", "transfer_id": transfer_id,
                    "reason": "Invalid base64 data"}

        if len(data) > MAX_CHUNK_SIZE:
            self._cleanup_transfer(transfer_id)
            return {"type": "file_cancel", "transfer_id": transfer_id,
                    "reason": "Chunk too large"}

        try:
            with open(t.tmp_path, "ab") as f:
                f.write(data)
            t.received += len(data)
            t.hasher.update(data)
        except OSError as e:
            self._cleanup_transfer(transfer_id)
            return {"type": "file_cancel", "transfer_id": transfer_id,
                    "reason": f"Write error: {e}"}

        return None  # No response needed for chunks

    def _handle_done(self, msg: dict) -> dict:
        transfer_id = msg.get("transfer_id", "")
        t = self._transfers.get(transfer_id)
        if not t:
            return {"type": "file_cancel", "transfer_id": transfer_id,
                    "reason": "Unknown transfer"}

        # Verify checksum if provided
        actual_checksum = t.hasher.hexdigest()
        if t.expected_checksum and actual_checksum != t.expected_checksum:
            self._cleanup_transfer(transfer_id)
            return {"type": "file_ack", "transfer_id": transfer_id,
                    "success": False,
                    "error": f"Checksum mismatch (expected {t.expected_checksum}, got {actual_checksum})"}

        # Move temp file to final destination
        try:
            os.rename(str(t.tmp_path), str(t.dest_path))
            # Set ownership to the session user
            if self._uid > 0:
                os.chown(str(t.dest_path), self._uid, self._gid)
            os.chmod(str(t.dest_path), 0o644)
        except OSError as e:
            self._cleanup_transfer(transfer_id)
            return {"type": "file_ack", "transfer_id": transfer_id,
                    "success": False, "error": f"Failed to finalize: {e}"}

        logger.info("File transfer complete: %s (%d bytes) → %s",
                     t.filename, t.received, t.dest_path)

        del self._transfers[transfer_id]
        return {"type": "file_ack", "transfer_id": transfer_id,
                "success": True, "dest_path": str(t.dest_path),
                "bytes_received": t.received}

    def _handle_cancel(self, msg: dict) -> None:
        transfer_id = msg.get("transfer_id", "")
        self._cleanup_transfer(transfer_id)
        logger.info("File transfer cancelled: %s", transfer_id)

    def _cleanup_transfer(self, transfer_id: str):
        t = self._transfers.pop(transfer_id, None)
        if t and t.tmp_path.exists():
            try:
                t.tmp_path.unlink()
            except OSError:
                pass


class _Transfer:
    __slots__ = ('transfer_id', 'filename', 'file_size', 'expected_checksum',
                 'dest_path', 'tmp_path', 'received', 'hasher')

    def __init__(self, transfer_id, filename, file_size, expected_checksum,
                 dest_path, tmp_path, received):
        self.transfer_id = transfer_id
        self.filename = filename
        self.file_size = file_size
        self.expected_checksum = expected_checksum
        self.dest_path = dest_path
        self.tmp_path = tmp_path
        self.received = received
        self.hasher = hashlib.sha256()
