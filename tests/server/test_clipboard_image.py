"""Phase 3 D-13 / D-14 / D-16 — Linux clipboard PNG image path.

Wave 0 skeleton (Plan 03-01 Task 2). Implementation lands in Plan 03-06
as extensions to :class:`server.clipboard.ClipboardSync`:

* ``get_clipboard_image()`` / ``set_clipboard_image(bytes)`` via
  ``xclip -t image/png`` subprocess pair
* ``validate_png_payload(bytes)`` enforces the 8-byte PNG magic signature
  ``\\x89PNG\\r\\n\\x1a\\n``, the 64 MB decoded-size cap (D-14), and a
  ``PIL.Image.verify()`` round-trip (D-16)

Malformed payloads are dropped with a structlog warning; never injected
into the system clipboard (threat T-03-03 defense-in-depth mirror of
D-17's chunk bounds).
"""
import pytest


def test_validate_png_payload_accepts_valid_png(fixture_png):
    """D-16 — 8-byte PNG magic signature accepted."""
    pytest.importorskip("server.clipboard")
    pytest.skip("Wave 0 skeleton — implementation in Plan 03-06 (D-16)")


def test_validate_png_payload_rejects_magic_mismatch():
    """D-16 — non-PNG payloads rejected with structlog warning."""
    pytest.importorskip("server.clipboard")
    pytest.skip("Wave 0 skeleton — implementation in Plan 03-06 (D-16)")


def test_validate_png_payload_rejects_oversize():
    """D-14 — 64 MB + 1 byte payload rejected by size cap."""
    pytest.importorskip("server.clipboard")
    pytest.skip("Wave 0 skeleton — implementation in Plan 03-06 (D-14)")


def test_validate_png_payload_rejects_corrupt_internals():
    """D-16 — PIL.Image.verify() failure path rejects corrupt-but-magic-OK bytes."""
    pytest.importorskip("server.clipboard")
    pytest.skip("Wave 0 skeleton — implementation in Plan 03-06 (D-16)")
