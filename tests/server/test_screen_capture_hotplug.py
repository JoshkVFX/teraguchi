"""Phase 3 D-02 / D-09 / D-12 — Linux screen-capture hot-plug detection.

Plan 03-03 Task 1. The shallow count+WxH signature is upgraded to a full
``(id, width, height, x, y)`` tuple so monitor reorder and reposition
also trigger the change signal (mirrors the D-11 Mac upgrade).
"""
import pytest


def _fake_monitors_v1():
    return [
        {"left": 0, "top": 0, "width": 5120, "height": 1600},
        {"left": 0, "top": 0, "width": 2560, "height": 1600},
        {"left": 2560, "top": 0, "width": 2560, "height": 1600},
    ]


def _fake_monitors_repositioned():
    # Same sizes, but the secondary monitor moved from x=2560 to x=3000.
    return [
        {"left": 0, "top": 0, "width": 5120, "height": 1600},
        {"left": 0, "top": 0, "width": 2560, "height": 1600},
        {"left": 3000, "top": 0, "width": 2560, "height": 1600},
    ]


def _fake_monitors_count_added():
    return [
        {"left": 0, "top": 0, "width": 7680, "height": 1600},
        {"left": 0, "top": 0, "width": 2560, "height": 1600},
        {"left": 2560, "top": 0, "width": 2560, "height": 1600},
        {"left": 5120, "top": 0, "width": 2560, "height": 1600},
    ]


@pytest.fixture
def capture(monkeypatch):
    """Minimal ScreenCapture for hot-plug tests — mocks mss at the boundary."""

    class _FakeSct:
        def __init__(self, monitors):
            self.monitors = monitors

        def close(self):
            pass

        def grab(self, monitor):
            raise AssertionError("grab not expected in hot-plug tests")

    import mss
    state = {"monitors": _fake_monitors_v1()}

    def _mss_factory():
        return _FakeSct(list(state["monitors"]))

    monkeypatch.setattr(mss, "mss", _mss_factory)

    import server.screen_capture as sc_mod
    monkeypatch.setattr(sc_mod, "detect_nvfbc", lambda: False)
    monkeypatch.setattr(sc_mod, "detect_monitors_xrandr", lambda: [])
    monkeypatch.setattr(sc_mod, "_HAS_NVFBC_BACKEND", False)
    monkeypatch.setattr(sc_mod, "_HAS_XLIB_DAMAGE", False)

    cap = sc_mod.ScreenCapture(monitor_index=0)
    # Expose the mutable monitor slot so tests can swap topologies.
    cap.__mss_state = state  # type: ignore[attr-defined]
    return cap


def test_detect_hotplug_catches_count_change(capture):
    """D-12 — monitor added → detect_hotplug returns True."""
    capture.__mss_state["monitors"] = _fake_monitors_count_added()
    assert capture.detect_hotplug() is True


def test_detect_hotplug_catches_position_change(capture):
    """D-09 — same WxH but monitor repositioned → detect_hotplug catches the move.

    The legacy shallow signature (count + WxH only) missed this. Full
    tuple signature + xrandr-query triangulation catches reposition.
    """
    capture.__mss_state["monitors"] = _fake_monitors_repositioned()
    assert capture.detect_hotplug() is True


def test_detect_hotplug_stable_when_nothing_changes(capture):
    """D-09 — unchanged monitor layout → detect_hotplug returns False."""
    # Same topology as init; hot-plug sentinel should not fire.
    assert capture.detect_hotplug() is False


def test_detect_hotplug_full_tuple_signature_includes_id_and_position(capture, monkeypatch):
    """D-09 — signature is (id, width, height, x, y) per monitor, not just (w, h).

    Verifies the implementation inspects the positional axes by seeding
    list_monitors with a position that would be silently equal under the
    old (w, h)-only signature but differs under the full tuple.
    """
    # Baseline: run detect_hotplug once with a no-op change so the internal
    # cached signature is refreshed.
    assert capture.detect_hotplug() is False
    # Now flip only the x position on the second physical monitor.
    capture.__mss_state["monitors"] = _fake_monitors_repositioned()
    assert capture.detect_hotplug() is True
