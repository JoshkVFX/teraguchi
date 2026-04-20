"""Phase 3 D-01 / D-04 — connect-dialog ModeSelector signal emission.

Wave 0 skeleton (Plan 03-01 Task 2). Implementation lands in Plan 03-02
as a new ``ModeSelector`` sub-widget inside ``client/connect_dialog.py``
(or ``client/main_window.py::ConnectionDialog``). Emits
``mode_changed(mode, picked_monitor_id, picked_monitor_name)`` on radio
change; pre-fills from the bookmark's last-used mode; feeds
:class:`MonitorSelector` in radio mode for the pick-one sub-selection
(D-04).

UI contract: Surface 1 in ``03-UI-SPEC.md`` (monitor-mode radios with
help copy + sub-selector when ``Pick one`` is chosen).
"""
import pytest


def test_mode_selector_emits_signal_on_radio_change():
    """D-01 — ModeSelector emits ``(mode, picked_id, picked_name)`` tuple."""
    pytest.importorskip("client.connect_dialog")
    pytest.skip("Wave 0 skeleton — implementation in Plan 03-02 (D-01)")


def test_mode_selector_prefills_from_bookmark():
    """D-01 — pre-fill works for all 3 modes (single / mirror_all / pick_one)."""
    pytest.importorskip("client.connect_dialog")
    pytest.skip("Wave 0 skeleton — implementation in Plan 03-02 (D-01)")


def test_pick_one_without_sub_selection_emits_minus_one():
    """D-04 — pick-one radio checked but no monitor picked → ``picked_id=-1``."""
    pytest.importorskip("client.connect_dialog")
    pytest.skip("Wave 0 skeleton — implementation in Plan 03-02 (D-04)")
