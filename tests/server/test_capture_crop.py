"""Phase 3 D-02 — server-side GPU crop preserving 10-bit fidelity.

Wave 0 skeleton (Plan 03-01 Task 2). Implementation lands in Plan 03-03
as :meth:`server.screen_capture.ScreenCapture.capture_raw_bgra_with_crop`:

* ``crop=None`` → full virtual-desktop frame (mirror_all path, bandwidth
  baseline unchanged)
* ``crop=(x, y, w, h)`` → GPU-cropped frame for single / pick-one modes
  so only the chosen pixels hit the encoder

For the NvFBC 10-bit P010 path, the crop MUST operate on Y and UV planes
separately (UV is half-resolution on both axes). The ten_bit_smoke test
extends the Phase 2 P010 ramp fixture to prove the crop doesn't silently
downgrade to 8-bit.
"""
import pytest


def test_capture_crop_none_returns_full_frame():
    """D-02 — ``crop=None`` preserves the legacy full-virtual-desktop path."""
    pytest.importorskip("server.screen_capture")
    pytest.skip("Wave 0 skeleton — implementation in Plan 03-03 (D-02)")


def test_capture_crop_returns_expected_dimensions():
    """D-02 — ``crop=(0, 0, 640, 480)`` yields 640×480×4 BGRA bytes."""
    pytest.importorskip("server.screen_capture")
    pytest.skip("Wave 0 skeleton — implementation in Plan 03-03 (D-02)")


@pytest.mark.ten_bit_smoke
def test_capture_crop_preserves_10bit_p010():
    """D-02 — crop on a P010 fixture preserves 10-bit fidelity (no silent 8-bit downgrade).

    Extends Phase 2 9-checkpoint pipeline fixture — crop operates on Y and
    UV planes separately so the YUV420P10LE layout is preserved.
    """
    pytest.importorskip("server.screen_capture")
    pytest.skip("Wave 0 skeleton — implementation in Plan 03-03 (D-02 + Phase 2 color gate)")
