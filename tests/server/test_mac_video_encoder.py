"""D-04 / VIDEO-04 - mac_video_encoder.py with VTCompressionSession mocked.

Mirrors the tests/server/test_video_encoder_mock.py D-02 mock-at-subprocess
pattern, except the boundary is VideoToolbox (PyObjC) rather than ffmpeg
subprocess. Module-under-test lands in Wave 2 (plan 02-05).

Wave 0 role: provide the file + collection-stable xfail skeleton so Wave 2
executors can extend the test shape without inventing it mid-plan.

Do NOT:
- Require a real VideoToolbox runtime on the test runner.
- Assert on emitted encoded-frame bytes.
- Instantiate server.mac_video_encoder before Wave 2 lands it.
"""
from __future__ import annotations

import pytest

# PyObjC ("objc") is only available on macOS. Wave 2 (02-05) will apply a
# pytest.importorskip("objc") at module level once the real module lands,
# but in Wave 0 we leave imports INSIDE each test body so the 5 xfail
# skeletons are always collected (Linux + macOS) for the Task 2 acceptance
# count (pytest --co -q lists exactly 5 tests).


@pytest.mark.xfail(
    reason="Wave 2 - mac_video_encoder.py lands in 02-05", strict=False
)
def test_encoder_instantiates_without_real_vt():
    """Constructor must not require a live VTCompressionSession."""
    from server.mac_video_encoder import MacVideoEncoder  # noqa: F401
    pytest.fail("Wave 2 (02-05) wires the MacVideoEncoder constructor test")


@pytest.mark.xfail(
    reason="Wave 2 - mac_video_encoder.py lands in 02-05", strict=False
)
def test_encoder_start_creates_vt_session():
    """start() must call VTCompressionSessionCreate via the mocked boundary."""
    from server.mac_video_encoder import MacVideoEncoder  # noqa: F401
    pytest.fail(
        "Wave 2 (02-05) monkeypatches VT.VTCompressionSessionCreate and "
        "asserts start() invokes it exactly once with Main10 profile"
    )


@pytest.mark.xfail(
    reason="Wave 2 - mac_video_encoder.py lands in 02-05", strict=False
)
def test_encoder_request_keyframe_is_callable():
    """request_keyframe() must not crash when invoked on a mocked session."""
    from server.mac_video_encoder import MacVideoEncoder  # noqa: F401
    pytest.fail(
        "Wave 2 (02-05) asserts VTCompressionSessionEncodeFrame is called "
        "with the force-keyframe properties dict"
    )


@pytest.mark.xfail(
    reason="Wave 2 - mac_video_encoder.py lands in 02-05", strict=False
)
def test_encoder_stop_invalidates_session():
    """stop() must call VTCompressionSessionInvalidate on teardown."""
    from server.mac_video_encoder import MacVideoEncoder  # noqa: F401
    pytest.fail(
        "Wave 2 (02-05) asserts VTCompressionSessionInvalidate + release "
        "are called on stop"
    )


@pytest.mark.xfail(
    reason="Wave 2 - mac_video_encoder.py lands in 02-05", strict=False
)
def test_encoder_feed_frame_encodes_cvpixelbuffer():
    """feed_frame() must wrap the raw bytes into a CVPixelBuffer + submit."""
    from server.mac_video_encoder import MacVideoEncoder  # noqa: F401
    pytest.fail(
        "Wave 2 (02-05) asserts CVPixelBufferCreate is called with "
        "kCVPixelFormatType_420YpCbCr10BiPlanarVideoRange and the sample "
        "is submitted via VTCompressionSessionEncodeFrame"
    )
