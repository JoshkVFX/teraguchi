"""Phase 3 D-13 / D-14 / D-16 — macOS clipboard PNG image path.

Wave 0 skeleton (Plan 03-01 Task 2). Implementation lands in Plan 03-06
as extensions to :class:`server.mac_clipboard.MacClipboardSync`:

* ``get_clipboard_image()`` / ``set_clipboard_image(bytes)`` via
  NSPasteboard's ``NSPasteboardTypePNG`` type pair
* Magic-byte + size-cap validation mirroring the Linux path

Mocks NSPasteboard at the PyObjC boundary per the Phase 2 mock-at-
IOKit-boundary discipline.
"""
import pytest


def test_set_clipboard_image_writes_nspasteboard_png(fixture_png, monkeypatch):
    """D-13 — ``set_clipboard_image`` calls ``pb.setData_forType_(NSPasteboardTypePNG)``."""
    pytest.importorskip("server.mac_clipboard")
    pytest.skip("Wave 0 skeleton — implementation in Plan 03-06 (D-13)")


def test_get_clipboard_image_reads_nspasteboard_png(fixture_png, monkeypatch):
    """D-13 — ``get_clipboard_image`` returns bytes from mocked NSData payload."""
    pytest.importorskip("server.mac_clipboard")
    pytest.skip("Wave 0 skeleton — implementation in Plan 03-06 (D-13)")


def test_get_clipboard_image_rejects_magic_mismatch(monkeypatch):
    """D-16 — inbound non-PNG NSPasteboard payload rejected on receive."""
    pytest.importorskip("server.mac_clipboard")
    pytest.skip("Wave 0 skeleton — implementation in Plan 03-06 (D-16)")
