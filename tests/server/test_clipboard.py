"""Server-side clipboard tests — Linux (xclip / xsel) path.

Wave 0 skeleton (Plan 03-01). Initial file created during Phase 3 Wave 0
scaffolding — the plan anticipated an existing file, but no prior phase
landed one (Phase 2 clipboard work stayed in ``server/clipboard.py`` and
``server/mac_clipboard.py`` without shipping unit tests). The single test
below stays skipped until Plan 06 (CLIP-01 / D-16) lands the text=False
bytes path.
"""
import pytest


# ═══════════════════════════════════════════════════════════════════════
# Phase 3 Wave 0 skeletons (Plan 03-01 Task 2)
# ═══════════════════════════════════════════════════════════════════════


def test_newline_preservation(monkeypatch):
    """CLIP-01 / D-16 — text=False bytes path preserves CRLF / LF / CR (Wave 0 RED).

    Plan 06 switches the ``subprocess.run`` call in
    :meth:`server.clipboard.ClipboardSync.get_clipboard` from
    ``text=True`` → ``text=False`` + explicit UTF-8 decode so the
    originating newline encoding survives the round-trip. Today's path
    lets Python's universal-newlines layer silently convert CRLF → LF,
    which breaks artists round-tripping Windows-origin clipboard text
    through a Mac client to a Rocky server.

    The detailed wiring (stub subprocess returning bytes of each newline
    form, assert decode preserves them) lives in Plan 06 where the
    ``text=False`` change actually lands.
    """
    pytest.skip("Wave 0 skeleton — implementation in Plan 06 (CLIP-01 / D-16)")
