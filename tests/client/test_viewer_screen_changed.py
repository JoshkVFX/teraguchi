"""Phase 3 D-06 + D-19 — viewer screenChanged slot recomputes caches.

Wave 0 skeleton (Plan 03-01 Task 2). Implementation lands in Plan 03-04:
:meth:`client.viewer.RemoteViewer._on_screen_changed` is connected to
:attr:`QWindow.screenChanged`; on signal, the slot recomputes the
scaling cache AND re-emits pen proximity if ``_pen_was_in_proximity``
(D-19 × D-06 cross-trigger) so Flame sees a fresh proximity-enter after
the viewer crosses between screens of different DPR.
"""
import pytest


def test_screen_changed_triggers_on_screen_changed_slot():
    """D-06 — QWindow.screenChanged signal → ``_on_screen_changed`` slot fires."""
    pytest.importorskip("client.viewer")
    pytest.skip("Wave 0 skeleton — implementation in Plan 03-04 (D-06)")


def test_on_screen_changed_recomputes_scaling_cache():
    """D-06 — slot invalidates the widget→server-px scaling cache."""
    pytest.importorskip("client.viewer")
    pytest.skip("Wave 0 skeleton — implementation in Plan 03-04 (D-06)")


def test_on_screen_changed_re_emits_pen_proximity():
    """D-06 × D-19 — slot re-emits PenProximityMsg when pen was in proximity pre-move."""
    pytest.importorskip("client.viewer")
    pytest.skip("Wave 0 skeleton — implementation in Plan 03-04 (D-06 + D-19)")
