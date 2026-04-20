"""Phase 3 CLIP-01 / D-16 / D-17 — large text clipboard integration.

Wave 0 skeleton (Plan 03-01 Task 2). Implementation lands in Plan 03-06:
in-process loopback exercises the >1 MB text round-trip via
:class:`ClipboardChunkMsg` chunking, asserting byte-equality AND that
native newline encoding (CRLF / LF / CR) is preserved — never silently
normalized.

Covers the PCoIP feature-parity ask "artist pastes a 2 MB Flame render
log into a Slack message and it doesn't corrupt."
"""
import pytest


def test_large_text_round_trip_byte_equal():
    """CLIP-01 — >1 MB UTF-8 text survives chunked round-trip byte-equal."""
    pytest.skip("Wave 0 skeleton — implementation in Plan 03-06 (CLIP-01)")


@pytest.mark.parametrize("newline", ["\r\n", "\n", "\r"])
def test_newline_encoding_preserved(newline):
    """D-16 — sender's native newline encoding (CRLF / LF / CR) round-trips verbatim."""
    pytest.skip("Wave 0 skeleton — implementation in Plan 03-06 (D-16)")
