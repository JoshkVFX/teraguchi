"""Phase 3 D-05 / DISP-03 / DISP-05 — widget→server-physical-pixel math.

Wave 0 skeleton (Plan 03-01 Task 2). Implementation lands in Plan 03-04
(client viewer cursor-math rewrite). These tests are RED until Plan 03-04
refactors :meth:`client.viewer.RemoteViewer._widget_to_remote` to emit
a 4-tuple carrying the client-computed server physical pixels alongside
the legacy normalized floats.

The synthetic 4-corner test here is the CI analog of the D-08 DXS
hardware spike (Retina MBP + external 4K driving a 2×2560×1600 Rocky
NVIDIA Xorg server). Real-hardware verification stays in
``docs/release.md`` per Phase 1 D-05 (no self-hosted CI runners).
"""
import pytest


def test_widget_to_remote_returns_4_tuple_with_server_px():
    """D-05 — :meth:`_widget_to_remote` returns ``(rx_norm, ry_norm, server_x, server_y)``.

    Plan 03-04 rewrites the method to emit the 4-tuple; until then the
    import itself is the RED signal.
    """
    viewer = pytest.importorskip("client.viewer")  # noqa: F841
    pytest.skip("Wave 0 skeleton — implementation in Plan 03-04 (D-05)")


def test_dxs_topology_4_corner_clicks_land_within_1_px(fake_mss_monitor_list):
    """DISP-03 / D-08 synthetic fixture — 4-corner click test on 2×2560×1600 desktop.

    Simulates the Retina MBP (DPR 2.0) + external 4K (DPR 1.0) client
    clicking each of the 8 corner pixels (4 per server monitor) and
    asserts the computed server coord lands within 1 px of the expected
    corner. Real-hardware verification is the pre-phase D-08 spike.
    """
    pytest.skip("Wave 0 skeleton — implementation in Plan 03-04 (D-05/D-06)")
