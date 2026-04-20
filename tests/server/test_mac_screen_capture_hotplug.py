"""Phase 3 D-11 / D-12 — macOS SCK push hot-plug detection.

Wave 0 skeleton (Plan 03-01 Task 2). Implementation lands in Plan 03-03:
:meth:`server.mac_screen_capture.MacScreenCapture.detect_hotplug` gains
the full ``(displayID, width, height, x, y)`` signature AND subscribes
to ScreenCaptureKit's :class:`SCStreamDelegate` display-change callback
so the handler fires on-change instead of only on the 5 s poll cadence.
The poll loop in ``server/monitor_hotplug.py`` stays as safety net.

Mocks ScreenCaptureKit at the PyObjC boundary per the Phase 2 mock-at-
IOKit-boundary discipline — no real Mac display hardware required.
"""
import pytest


def test_detect_hotplug_full_tuple_signature(monkeypatch):
    """D-11 — SCK display add/remove triggers detect_hotplug(True).

    Full tuple signature catches same-size swaps and repositioning that
    today's shallow count+WxH check misses (Cintiq Pro 24 + Retina spike
    stress).
    """
    pytest.importorskip("server.mac_screen_capture")
    pytest.skip("Wave 0 skeleton — implementation in Plan 03-03 (D-11)")


def test_hotplug_pending_flag_fires_on_next_poll(monkeypatch):
    """D-11 — SCStreamDelegate sets ``_hotplug_pending``; next poll fires without 5 s delay."""
    pytest.importorskip("server.mac_screen_capture")
    pytest.skip("Wave 0 skeleton — implementation in Plan 03-03 (D-11)")
