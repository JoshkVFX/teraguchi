"""Phase 3 D-15 — 4-direction clipboard toggle policy gating.

Wave 0 skeleton (Plan 03-01 Task 2). Implementation lands in Plan 03-06
inside :mod:`server.session_runtime` — the clipboard dispatcher
short-circuits on direction-disabled so zero wire traffic leaves either
side when the toggle is OFF.

Pattern analog: Phase 2 D-10 per-bookmark swap-policy gating in
``server/modifier_dispatch.py`` (``tests/server/test_modifier_dispatch.py``).
Pitfall 7 race: a toggle flipped mid-sequence should apply to the NEXT
clipboard event, not mutate an in-flight one.
"""
import pytest


def test_toggle_s2c_off_short_circuits_broadcast():
    """D-15 — clipboard_text_s2c=False → server skips the broadcast entirely."""
    pytest.importorskip("server.session_runtime")
    pytest.skip("Wave 0 skeleton — implementation in Plan 03-06 (D-15)")


def test_toggle_c2s_image_off_drops_inbound():
    """D-15 — clipboard_image_c2s=False → inbound image dispatch silently dropped."""
    pytest.importorskip("server.session_runtime")
    pytest.skip("Wave 0 skeleton — implementation in Plan 03-06 (D-15)")


def test_toggle_change_applies_to_next_sequence():
    """Pitfall 7 — mid-sequence toggle flip applies at next sequence_id boundary."""
    pytest.importorskip("server.session_runtime")
    pytest.skip("Wave 0 skeleton — implementation in Plan 03-06 (D-15)")
