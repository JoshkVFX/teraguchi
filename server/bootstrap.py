"""Bootstrap helpers — TLS context + system dependency checks.

Extracted from server/main.py (Plan 01-11 cleanup). Pure helpers with no
module-global dependencies; they can live outside main.py without
affecting the CLI entrypoint or the handle_client dispatch.
"""
from __future__ import annotations

import logging
import os
import ssl

from server.platform_backends import IS_MACOS


logger = logging.getLogger("teraguchi.server.bootstrap")


def check_system_dependencies() -> None:
    """Warn about missing system dependencies. Non-fatal — a missing tool
    just disables the corresponding feature (e.g. no ffmpeg → no video
    encoding; no xclip/xsel → no clipboard sync)."""
    import shutil
    if not shutil.which("ffmpeg"):
        logger.warning("Missing system dependency: ffmpeg — Video encoding will not work")

    if IS_MACOS:
        # Audio / clipboard / input are all supplied by native Cocoa
        # frameworks on macOS; none of the Linux CLI deps apply.
        return

    if not shutil.which("pactl"):
        logger.warning("Missing system dependency: pactl (PulseAudio) — Audio capture will not work")

    if not shutil.which("xclip") and not shutil.which("xsel"):
        logger.warning("Missing clipboard tool (xclip or xsel) — clipboard sync disabled")

    if not os.path.exists("/dev/uinput"):
        logger.warning("/dev/uinput not found — input injection may fail. Run: sudo modprobe uinput")


def create_tls_context(cert_file: str, key_file: str) -> ssl.SSLContext:
    """Build the server-side TLS context. TLS 1.2 minimum (see STAB-02)."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert_file, key_file)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    return ctx
