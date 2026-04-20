"""Phase 3 D-09 / D-12 — in-process loopback monitor-hotplug integration.

Wave 0 skeleton (Plan 03-01 Task 2). Implementation lands in Plan 03-03:
uses the P1 D-03 in-process loopback pattern
(``tests/integration/test_reconnect.py`` lines 36-99) to drive the
server monitor-hotplug handler and assert the client receives a fresh
MonitorListMsg while the FSM stays in ``streaming``.

Covers two sub-scenarios:
1. Mid-session hotplug triggers MonitorListMsg broadcast; session
   survives without FSM transition.
2. Pick-one + picked monitor vanishes → server auto-fallback to primary
   + INFO toast emission on client; banner (Surface 5) shown.
"""
import pytest


def test_mid_session_hotplug_session_survives():
    """D-09 — server fires hotplug → client MonitorListMsg received; FSM stays streaming."""
    pytest.skip("Wave 0 skeleton — implementation in Plan 03-03 (D-09/D-12)")


def test_pick_vanish_fallback_banner_and_toast():
    """D-09 — picked monitor vanishes → server fallback + INFO toast + remap banner."""
    pytest.skip("Wave 0 skeleton — implementation in Plan 03-03 (D-09 fallback)")
