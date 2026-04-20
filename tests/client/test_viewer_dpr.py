"""Phase 3 D-06 — per-screen devicePixelRatio lookup.

Wave 0 skeleton (Plan 03-01 Task 2). Implementation lands in Plan 03-04
as :meth:`client.viewer.RemoteViewer._current_screen_dpr` — looks up the
DPR of the QScreen the viewer widget is currently on via
``windowHandle().screen().devicePixelRatio()``, falling back to the
widget's ``devicePixelRatioF()`` when ``windowHandle()`` is None
(pre-show / offscreen cases).

Fixes the PITFALLS #5 "cursor lands a bit left of where I click" class
of bug on mixed-DPI Mac clients (Cintiq Pro 24 + Retina).
"""
import pytest


def test_current_screen_dpr_uses_widget_screen(mock_nsscreen):
    """D-06 — viewer on external 4K (screen[1]) returns 1.0, not primary's 2.0."""
    pytest.importorskip("client.viewer")
    pytest.skip("Wave 0 skeleton — implementation in Plan 03-04 (D-06)")


def test_current_screen_dpr_falls_back_when_windowhandle_none():
    """D-06 — graceful fallback via ``devicePixelRatioF()`` pre-show."""
    pytest.importorskip("client.viewer")
    pytest.skip("Wave 0 skeleton — implementation in Plan 03-04 (D-06)")
