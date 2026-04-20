"""Phase 3 D-15 / C-07 — ClipboardToggleButton QMenu signal emission.

Wave 0 skeleton (Plan 03-01 Task 2). Implementation lands in Plan 03-06
as ``client/clipboard_toggle_menu.py`` — a QToolButton + QMenu widget
with four QWidgetAction checkboxes (text c2s / text s2c / image c2s /
image s2c). Emits a 4-key dict on any checkbox change; changes take
effect at the next clipboard event (no apply/cancel button).

UI contract: Surface 7 in ``03-UI-SPEC.md`` (accessible name
``Clipboard direction``; rows 3/4 nested under 1/2 with disabled-state
tooltips).
"""
import pytest


def test_clipboard_toggle_button_emits_dict_on_change():
    """D-15 — ClipboardToggleButton emits a 4-key dict on any toggle change."""
    pytest.importorskip("client.clipboard_toggle_menu")
    pytest.skip("Wave 0 skeleton — implementation in Plan 03-06 (D-15)")


def test_clipboard_toggle_defaults_all_on():
    """D-15 / D-16 — default state has all 4 directions ON (secure default)."""
    pytest.importorskip("client.clipboard_toggle_menu")
    pytest.skip("Wave 0 skeleton — implementation in Plan 03-06 (D-16)")


def test_clipboard_toggle_row_3_disabled_when_row_1_off():
    """Surface 7 — unchecking row 1 (text c2s) disables row 3 (image c2s)."""
    pytest.importorskip("client.clipboard_toggle_menu")
    pytest.skip("Wave 0 skeleton — implementation in Plan 03-06 (Surface 7)")
