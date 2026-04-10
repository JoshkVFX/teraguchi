"""
Multi-monitor selector widget for Teraguchi.

Replaces the single-select QComboBox with a checkable menu.
Users can select any combination of monitors — beats PCoIP's
all-or-one limitation.
"""

import logging
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QToolButton, QMenu, QWidgetAction, QCheckBox, QWidget, QHBoxLayout, QLabel

logger = logging.getLogger(__name__)


class MonitorSelector(QToolButton):
    """Toolbar button that shows a checkable menu of monitors.

    Emits selection_changed with:
      - list of selected monitor dicts (x, y, width, height, id, name)
      - empty list means "all monitors" (nothing specifically selected)
    """

    selection_changed = Signal(list)  # list of selected monitor dicts

    def __init__(self, parent=None):
        super().__init__(parent)
        self._monitors: list = []
        self._actions: list = []  # (QAction, monitor_dict) pairs

        self.setText("Monitors")
        self.setPopupMode(QToolButton.InstantPopup)
        self._menu = QMenu(self)
        self.setMenu(self._menu)
        self.setMinimumWidth(120)

    def update_monitors(self, monitors: list):
        """Update the monitor list from server. Preserves existing selections."""
        old_selected_ids = {m["id"] for _, m in self._actions
                           if _.isChecked()}

        self._menu.clear()
        self._actions.clear()
        self._monitors = monitors

        if not monitors:
            self.setText("No monitors")
            return

        for mon in monitors:
            mon_id = mon.get("id", 0)
            name = mon.get("name", f"Monitor {mon_id}")
            w = mon.get("width", 0)
            h = mon.get("height", 0)
            label = f"{name} ({w}x{h})"

            action = self._menu.addAction(label)
            action.setCheckable(True)
            # Restore previous selection, or check all by default
            if old_selected_ids:
                action.setChecked(mon_id in old_selected_ids)
            else:
                action.setChecked(True)
            action.toggled.connect(self._on_toggled)
            self._actions.append((action, mon))

        # Separator + quick actions
        self._menu.addSeparator()
        select_all = self._menu.addAction("Select All")
        select_all.triggered.connect(self._select_all)
        select_none = self._menu.addAction("Select None")
        select_none.triggered.connect(self._select_none)

        self._update_label()

    def _on_toggled(self, _checked):
        self._update_label()
        self._emit_selection()

    def _select_all(self):
        for action, _ in self._actions:
            action.blockSignals(True)
            action.setChecked(True)
            action.blockSignals(False)
        self._update_label()
        self._emit_selection()

    def _select_none(self):
        for action, _ in self._actions:
            action.blockSignals(True)
            action.setChecked(False)
            action.blockSignals(False)
        self._update_label()
        self._emit_selection()

    def _update_label(self):
        checked = [m for a, m in self._actions if a.isChecked()]
        total = len(self._actions)
        if len(checked) == 0:
            self.setText("No monitors")
        elif len(checked) == total:
            self.setText(f"All ({total})")
        elif len(checked) == 1:
            name = checked[0].get("name", "Monitor")
            self.setText(name)
        else:
            self.setText(f"{len(checked)} of {total}")

    def _emit_selection(self):
        checked = [m for a, m in self._actions if a.isChecked()]
        total = len(self._actions)

        if len(checked) == total or len(checked) == 0:
            # All selected or none = show everything (no crop)
            self.selection_changed.emit([])
        else:
            self.selection_changed.emit(checked)

    def get_selected(self) -> list:
        """Return currently selected monitor dicts."""
        checked = [m for a, m in self._actions if a.isChecked()]
        total = len(self._actions)
        if len(checked) == total or len(checked) == 0:
            return []
        return checked
