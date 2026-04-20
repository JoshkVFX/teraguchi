"""Phase 3 CLIP-02 / D-13 / D-14 / D-16 / D-17 — PNG image clipboard integration.

Wave 0 skeleton (Plan 03-01 Task 2). Implementation lands in Plan 03-06:
in-process loopback exercises the PNG image clipboard round-trip end to
end — client copy → server paste → client paste, asserting
``sha256(in) == sha256(out)``. Alpha channel and chunked transport
(>1 MB PNG) are also covered.
"""
import pytest


def test_png_round_trip_sha256_match(fixture_png):
    """CLIP-02 — sha256(in) == sha256(out) after full client↔server round-trip."""
    pytest.skip("Wave 0 skeleton — implementation in Plan 03-06 (CLIP-02)")


def test_png_alpha_channel_preserved():
    """D-13 — RGBA PNG (alpha channel) survives round-trip intact."""
    pytest.skip("Wave 0 skeleton — implementation in Plan 03-06 (D-13)")


def test_png_chunked_transport_reassembles():
    """D-17 — >1 MB PNG splits into ClipboardChunkMsg frames + reassembles correctly."""
    pytest.skip("Wave 0 skeleton — implementation in Plan 03-06 (D-17)")
