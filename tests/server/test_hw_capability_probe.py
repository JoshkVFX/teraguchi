"""D-03 / VIDEO-03 / VIDEO-05 - hw capability probe with subprocess mocked.

Mirrors the tests/server/test_video_encoder_mock.py D-02 mock-at-subprocess
pattern applied to the nvidia-smi + VT trial-encode boundary used by the
Wave 1 (02-04) capability_probe.py to determine supports_main10 /
supports_422 / supports_444 / supports_mss_fallback flags for the
ServerHelloMsg capability handshake.

Wave 0 role: 4 xfail skeletons so Wave 1 executors extend without
inventing test shape. Real module lands in Wave 1 (plan 02-04).

Do NOT:
- Invoke real nvidia-smi, ffmpeg, or VT APIs.
- Depend on a specific GPU being present on the runner.
"""
from __future__ import annotations

import pytest


@pytest.mark.xfail(
    reason="Wave 1 - capability_probe.py lands in 02-04", strict=False
)
def test_probe_detects_turing_main10():
    """Turing (T4/RTX20xx) NVENC must report supports_main10=True,
    supports_422=False."""
    from server.capability_probe import probe_nvenc_capabilities  # noqa: F401
    pytest.fail(
        "Wave 1 (02-04) monkeypatches subprocess.run to return "
        "'NVIDIA GeForce RTX 2080\\n' and asserts main10=True, "
        "chroma_422=False"
    )


@pytest.mark.xfail(
    reason="Wave 1 - capability_probe.py lands in 02-04", strict=False
)
def test_probe_detects_blackwell_422():
    """Blackwell (RTX50xx) NVENC must report supports_422=True."""
    from server.capability_probe import probe_nvenc_capabilities  # noqa: F401
    pytest.fail(
        "Wave 1 (02-04) monkeypatches subprocess.run to return "
        "'NVIDIA GeForce RTX 5090\\n' and asserts main10=True, "
        "chroma_422=True"
    )


@pytest.mark.xfail(
    reason="Wave 1 - capability_probe.py lands in 02-04", strict=False
)
def test_probe_detects_apple_silicon_main10():
    """Apple Silicon VT must report supports_main10=True via the VT trial."""
    from server.capability_probe import probe_videotoolbox_capabilities  # noqa: F401
    pytest.fail(
        "Wave 1 (02-04) mocks VTCopySupportedPropertyDictionary at the "
        "PyObjC boundary and asserts main10=True on M1+"
    )


@pytest.mark.xfail(
    reason="Wave 1 - capability_probe.py lands in 02-04", strict=False
)
def test_probe_marks_mss_fallback_degraded():
    """mss-software-capture fallback must surface as degraded in the
    color_negotiated_state string."""
    from server.capability_probe import probe_capture_backend  # noqa: F401
    pytest.fail(
        "Wave 1 (02-04) asserts mss fallback yields "
        "color_negotiated_state == 'degraded'"
    )
