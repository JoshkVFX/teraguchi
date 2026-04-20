"""Phase 3 D-02 / D-09 — capture-mode negotiation integration test.

Wave 0 skeleton (Plan 03-01 Task 2). Implementation lands in Plan 03-03:
in-process loopback exercises the pick-one capture-mode handshake end to
end — client sends ClientHelloMsg with ``capture_mode="pick_one"`` +
``picked_monitor_id=N``; server applies the GPU crop pre-encode; fallback
path fires a toast when the picked id is invalid.

Mirrors ``tests/integration/test_auth_flow.py`` handshake-flow pattern.
"""
import pytest


def test_pick_one_mode_crops_to_selected_monitor():
    """D-02 — pick-one + valid monitor_id → server crops capture to that rect."""
    pytest.skip("Wave 0 skeleton — implementation in Plan 03-03 (D-02)")


def test_pick_fallback_to_primary_on_invalid_id():
    """D-09 — pick-one + invalid monitor_id → server falls back to primary + toast."""
    pytest.skip("Wave 0 skeleton — implementation in Plan 03-03 (D-09 fallback)")
