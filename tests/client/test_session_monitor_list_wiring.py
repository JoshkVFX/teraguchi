"""Plan 03-05 / D-09 — session-side MonitorListMsg handling.

When a MonitorListMsg arrives with a degradations entry keyed by this
session's client_token, the session should:
  - Instantiate RemapBanner (lazily, on first monitor_list with degradations)
  - Call banner.show_for_case("pick_missing", picked_name=<previous_pick>)
  - Call show_monitor_switched_toast(viewer, monitor_name=<previous_pick>)
  - Call toolbar.update_capture_mode(degraded=True) (if toolbar wired)

All wiring happens via queued Qt signals bridged through _Bridge so
the asyncio I/O thread never touches Qt widgets directly.
"""
from __future__ import annotations

import os

import pytest

pytest.importorskip("PySide6.QtWidgets")


@pytest.fixture(scope="module")
def qapp():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app


def test_session_on_monitor_list_degradation_triggers_banner_and_toast(qapp):
    """When a MonitorListMsg degradations entry matches our session's
    client_token, the banner + toast surface fires.

    We stub the Session class surface because the full Session needs
    Qt + asyncio + websocket bindings. The handler logic we're testing
    lives in client/session.py::_on_monitor_list — verify the wiring
    calls the right helpers by monkeypatching them.
    """
    # Set up a minimal fake Session-like harness: the handler we want
    # to test reads self.viewer, self.toolbar, self._client_token,
    # self._monitor_mode, self.remap_banner, self._last_monitor_count.
    import client.session as session_mod
    import client.toasts as toasts_mod
    import client.remap_banner as banner_mod

    from PySide6.QtWidgets import QWidget
    viewer = QWidget()
    viewer.resize(1200, 800)

    # Collect calls to the banner + toast helpers via monkeypatch.
    banner_calls: list = []
    toast_calls: list = []

    class _SpyBanner:
        def __init__(self, parent):
            self._parent = parent

        def show_for_case(self, case, picked_name=""):
            banner_calls.append((case, picked_name))

    def _spy_toast(parent, monitor_name):
        toast_calls.append(("monitor_switched", monitor_name))

    # Patch at the module level — client/session.py does late imports
    # inside _on_monitor_list.
    orig_banner = banner_mod.RemapBanner
    orig_toast = toasts_mod.show_monitor_switched_toast
    banner_mod.RemapBanner = _SpyBanner
    toasts_mod.show_monitor_switched_toast = _spy_toast

    try:
        # Build the minimal session surface the handler touches.
        from types import SimpleNamespace
        session = SimpleNamespace()
        session.viewer = viewer
        session.toolbar = None
        session.remap_banner = None
        session._client_token = "sid-A"
        session._monitor_mode = "pick_one"
        session._last_monitor_count = None

        # Invoke the handler the way _Bridge.monitor_list.emit would.
        msg = {
            "type": "monitor_list",
            "monitors": [{"id": 1, "name": "DP-1"}],
            "degradations": [{
                "client_token": "sid-A",
                "previous_pick": "DP-2",
                "now_showing": "DP-1",
            }],
        }
        # Bind the handler function — use the class method via the
        # unbound descriptor (it reads self.* attributes).
        handler = session_mod.Session._on_monitor_list_with_degradations
        handler(session, msg)

        # Banner fired with pick_missing case and previous_pick name.
        assert banner_calls == [("pick_missing", "DP-2")]
        # Toast fired with monitor_name=previous_pick (Surface 9 copy).
        assert toast_calls == [("monitor_switched", "DP-2")]
    finally:
        banner_mod.RemapBanner = orig_banner
        toasts_mod.show_monitor_switched_toast = orig_toast


def test_session_on_monitor_list_no_match_no_banner(qapp):
    """If the MonitorListMsg degradations entry is for a different
    client_token, this session does NOT show a banner or toast."""
    import client.session as session_mod
    import client.toasts as toasts_mod
    import client.remap_banner as banner_mod

    from PySide6.QtWidgets import QWidget
    viewer = QWidget()
    viewer.resize(1200, 800)

    banner_calls: list = []
    toast_calls: list = []

    class _SpyBanner:
        def __init__(self, parent):
            self._parent = parent

        def show_for_case(self, case, picked_name=""):
            banner_calls.append((case, picked_name))

    def _spy_toast(parent, monitor_name):
        toast_calls.append(("monitor_switched", monitor_name))

    orig_banner = banner_mod.RemapBanner
    orig_toast = toasts_mod.show_monitor_switched_toast
    banner_mod.RemapBanner = _SpyBanner
    toasts_mod.show_monitor_switched_toast = _spy_toast

    try:
        from types import SimpleNamespace
        session = SimpleNamespace()
        session.viewer = viewer
        session.toolbar = None
        session.remap_banner = None
        session._client_token = "sid-A"
        session._monitor_mode = "mirror_all"
        session._last_monitor_count = 2  # previous count

        # Degradation is for a DIFFERENT session.
        msg = {
            "type": "monitor_list",
            "monitors": [{"id": 1, "name": "DP-1"}],
            "degradations": [{
                "client_token": "sid-B",
                "previous_pick": "DP-2",
                "now_showing": "DP-1",
            }],
        }
        handler = session_mod.Session._on_monitor_list_with_degradations
        handler(session, msg)

        # No pick_missing banner (we're not degraded).
        pick_cases = [c for (c, _) in banner_calls if c == "pick_missing"]
        assert pick_cases == []
        # No monitor-switched toast (wasn't us).
        assert toast_calls == []
    finally:
        banner_mod.RemapBanner = orig_banner
        toasts_mod.show_monitor_switched_toast = orig_toast


def test_session_on_monitor_list_mirror_remove_banner(qapp):
    """mirror_all + monitor count decreases → mirror_remove banner fires
    (we weren't degraded, but the topology changed)."""
    import client.session as session_mod
    import client.remap_banner as banner_mod

    from PySide6.QtWidgets import QWidget
    viewer = QWidget()
    viewer.resize(1200, 800)

    banner_calls: list = []

    class _SpyBanner:
        def __init__(self, parent):
            self._parent = parent

        def show_for_case(self, case, picked_name=""):
            banner_calls.append((case, picked_name))

    orig_banner = banner_mod.RemapBanner
    banner_mod.RemapBanner = _SpyBanner

    try:
        from types import SimpleNamespace
        session = SimpleNamespace()
        session.viewer = viewer
        session.toolbar = None
        session.remap_banner = None
        session._client_token = "sid-A"
        session._monitor_mode = "mirror_all"
        session._last_monitor_count = 2

        # 1 monitor now; we had 2. No degradation for us.
        msg = {
            "type": "monitor_list",
            "monitors": [{"id": 1, "name": "DP-1"}],
            "degradations": [],
        }
        handler = session_mod.Session._on_monitor_list_with_degradations
        handler(session, msg)

        # mirror_remove banner should have been shown.
        cases = [c for (c, _) in banner_calls]
        assert "mirror_remove" in cases
        # _last_monitor_count updated.
        assert session._last_monitor_count == 1
    finally:
        banner_mod.RemapBanner = orig_banner
