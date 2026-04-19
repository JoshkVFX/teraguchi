"""9-checkpoint byte-equality pipeline harness. Wave 0 stub.

Downstream waves (2/3) fill in actual capture/encode/decode/display assertions.
Skeleton ensures the test file imports cleanly and CI can run it without errors.
"""
import json
import pathlib

import pytest

FIXTURE_DIR = pathlib.Path(__file__).parent / "fixtures"
RAMP_BIN = FIXTURE_DIR / "10bit_ramp.p010.bin"
REF_JSON = FIXTURE_DIR / "10bit_ramp.reference.ffprobe.json"

pytestmark = pytest.mark.ten_bit_smoke


@pytest.fixture(scope="module")
def reference_checkpoints():
    if not REF_JSON.exists():
        pytest.skip("reference JSON missing - Wave 0 did not land")
    return json.loads(REF_JSON.read_text())["checkpoints"]


@pytest.mark.xfail(reason="Wave 2 - Linux P010 capture not wired", strict=False)
def test_checkpoint_1_capture_surface_is_p010(reference_checkpoints):
    # noqa: F401 - import-only smoke that the capture module exists.
    from server import screen_capture  # noqa: F401
    assert reference_checkpoints["capture"]["expected_pix_fmt"] == "p010le"
    pytest.fail("Wave 2 owner wires NvFBC P010 surface and asserts format")


@pytest.mark.xfail(reason="Wave 2 - encoder input format wiring pending", strict=False)
def test_checkpoint_2_encoder_input_is_p010(reference_checkpoints):
    pytest.fail(
        "Wave 2 owner asserts FFmpeg command line uses -pix_fmt p010le AND "
        "VT CVPixelBufferCreate uses "
        "kCVPixelFormatType_420YpCbCr10BiPlanarVideoRange"
    )


@pytest.mark.xfail(reason="Wave 2 - encoder output ffprobe assertion pending", strict=False)
def test_checkpoint_3_encoder_output_profile_main10(reference_checkpoints):
    assert reference_checkpoints["encoder_output"]["ffprobe_pix_fmt"] == "yuv420p10le"
    pytest.fail("Wave 2 owner runs ffprobe on encoded sample")


@pytest.mark.xfail(reason="Wave 2 - NAL profile_idc parse pending", strict=False)
def test_checkpoint_4_wire_general_profile_idc_is_2(reference_checkpoints):
    assert reference_checkpoints["wire"]["h265_general_profile_idc"] == 2
    pytest.fail("Wave 2 owner parses VPS/SPS and asserts general_profile_idc == 2")


@pytest.mark.xfail(reason="Wave 3 - decoder AVFrame.format assertion pending", strict=False)
def test_checkpoint_5_decoder_output_format_is_p010():
    pytest.fail("Wave 3 owner asserts frame.format.name in ('p010le','yuv420p10le')")


@pytest.mark.xfail(reason="Wave 3 - decoder hwaccel stability pending", strict=False)
def test_checkpoint_6_decoder_hwaccel_is_videotoolbox():
    pytest.fail("Wave 3 owner asserts decoder.hw_backend == 'videotoolbox' on macOS")


@pytest.mark.xfail(reason="Wave 3 - QRhiWidget texture format assertion pending", strict=False)
def test_checkpoint_7_qrhi_texture_formats_are_r16_rg16():
    pytest.fail("Wave 3 owner asserts QRhiTexture format == R16 (Y) + RG16 (UV)")


@pytest.mark.gpu
@pytest.mark.skip(reason="Checkpoint 8 is manual-verified-once - see VALIDATION.md Manual-Only")
def test_checkpoint_8_metal_final_blit_preserves_10_bits():
    pass


@pytest.mark.skip(reason="Checkpoint 9 - macOS display state is log-only per D-01 cp.9")
def test_checkpoint_9_display_reference_mode_documented():
    pass
