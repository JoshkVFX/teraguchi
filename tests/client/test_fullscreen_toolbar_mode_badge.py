"""Phase 3 D-01 / D-03 — fullscreen-toolbar mode badge rendering.

Wave 0 skeleton (Plan 03-01 Task 2). Implementation lands in Plan 03-02
as a new ``ModeBadge`` widget in ``client/fullscreen_toolbar.py`` + an
analogous slot in the main-window top bar.

UI contract: Surface 2 (mode badge live session) + Surface 3 (grayed
mode widget during session). Badge shows ``Mode: {single | mirror |
pick: {name}}`` and switches to WARNING underline + "pick → primary"
copy when the picked monitor vanishes (D-09 fallback).
"""
import pytest


def test_mode_badge_renders_live_session_template():
    """D-01 — badge text matches ``Mode: {single|mirror|pick: {name}}``."""
    pytest.importorskip("client.fullscreen_toolbar")
    pytest.skip("Wave 0 skeleton — implementation in Plan 03-02 (D-01)")


def test_mode_badge_tooltip_matches_grayed_copy():
    """D-03 — tooltip renders the grayed-widget-during-session message."""
    pytest.importorskip("client.fullscreen_toolbar")
    pytest.skip("Wave 0 skeleton — implementation in Plan 03-02 (D-03)")


def test_mode_badge_degraded_state_uses_warning_underline():
    """D-09 — degraded badge shows WARNING underline + 'pick → primary' copy."""
    pytest.importorskip("client.fullscreen_toolbar")
    pytest.skip("Wave 0 skeleton — implementation in Plan 03-02 (D-09 fallback)")
