"""Phase 3 D-02 / D-09 / D-12 — Linux screen-capture hot-plug detection.

Wave 0 skeleton (Plan 03-01 Task 2). Implementation lands in Plan 03-03
which upgrades :meth:`server.screen_capture.ScreenCapture.detect_hotplug`
from the shallow count+WxH signature to the full
``(displayID, width, height, x, y)`` tuple so monitor reorder and
same-size swaps also trigger the change signal (mirrors the D-11 Mac
upgrade).

Mocks mss.mss() at the OS boundary per Phase 1 D-02 — no real X server
required. Closes CONCERNS.md §"Platform Parity Gaps" on the Linux side.
"""
import pytest


def test_detect_hotplug_catches_count_change(fake_mss_monitor_list, monkeypatch):
    """D-12 — monitor added/removed → detect_hotplug returns True + MonitorListMsg populated."""
    pytest.importorskip("server.screen_capture")
    pytest.skip("Wave 0 skeleton — implementation in Plan 03-03 (D-09/D-12)")


def test_detect_hotplug_catches_position_change(fake_mss_monitor_list, monkeypatch):
    """D-09 — same WxH but monitor repositioned → detect_hotplug catches the move.

    Today's shallow signature misses this (count unchanged, WxH unchanged)
    and drives the "cursor jumps to wrong monitor after xrandr reorder"
    class of bug. Plan 03-03 upgrades the tuple signature.
    """
    pytest.importorskip("server.screen_capture")
    pytest.skip("Wave 0 skeleton — implementation in Plan 03-03 (D-09)")
