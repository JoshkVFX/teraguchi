"""D-09 / INPUT-08 - mac_pen_injector.py with IOHIDUserDevice mocked.

Mirrors the tests/server/test_video_encoder_mock.py D-02 mock-at-subprocess
pattern applied to the IOKit (IOHIDUserDeviceCreate /
IOHIDUserDeviceHandleReport) boundary. Module-under-test lands in Wave 4
(plan 02-10), gated on the D-08 IOHIDUserDevice spike outcome.

Wave 0 role: provide the file + collection-stable xfail skeleton so Wave 4
executors can extend without re-inventing test shape. If the D-08 spike
fails, INPUT-08 is re-scoped per D-07 "document + ship" and these tests
stay skipped.

Do NOT:
- Require a real IOHIDUserDevice on the test runner.
- Depend on actual hardware (Wacom tablet) - those are Wave 6 manual tests.
"""
from __future__ import annotations

import pytest

# PyObjC ("objc") is only available on macOS. Wave 4 will apply
# pytest.importorskip("objc") at module level once the real module lands.
# Wave 0 leaves imports INSIDE each test body so the 5 xfail skeletons are
# always collected (Linux + macOS) for the Task 2 acceptance count.


@pytest.mark.xfail(
    reason="Wave 4 - mac_pen_injector.py lands in 02-10, gated on D-08 spike",
    strict=False,
)
def test_injector_instantiates_without_real_iokit():
    """Constructor must not require live IOKit bindings."""
    from server.mac_pen_injector import MacPenInjector  # noqa: F401
    pytest.fail("Wave 4 (02-10) wires the MacPenInjector constructor test")


@pytest.mark.xfail(
    reason="Wave 4 - mac_pen_injector.py lands in 02-10, gated on D-08 spike",
    strict=False,
)
def test_creates_iohid_user_device_on_start():
    """start() must call IOHIDUserDeviceCreate via the mocked boundary."""
    from server.mac_pen_injector import MacPenInjector  # noqa: F401
    pytest.fail(
        "Wave 4 (02-10) monkeypatches server.mac_pen_injector."
        "IOHIDUserDeviceCreate and asserts start() invokes it with the "
        "Wacom HID descriptor"
    )


@pytest.mark.xfail(
    reason="Wave 4 - mac_pen_injector.py lands in 02-10, gated on D-08 spike",
    strict=False,
)
def test_handle_report_passes_through_mock():
    """A pen event must reach IOHIDUserDeviceHandleReport via the mock."""
    from server.mac_pen_injector import MacPenInjector  # noqa: F401
    pytest.fail(
        "Wave 4 (02-10) asserts a pen_event triggers exactly one "
        "IOHIDUserDeviceHandleReport call with the packed report bytes"
    )


@pytest.mark.xfail(
    reason="Wave 4 - mac_pen_injector.py lands in 02-10, gated on D-08 spike",
    strict=False,
)
def test_stop_releases_device():
    """stop() must release the IOHIDUserDevice cleanly."""
    from server.mac_pen_injector import MacPenInjector  # noqa: F401
    pytest.fail(
        "Wave 4 (02-10) asserts IOObjectRelease (or CFRelease) fires on "
        "stop() without raising"
    )


@pytest.mark.xfail(
    reason="Wave 4 - mac_pen_injector.py lands in 02-10, gated on D-08 spike",
    strict=False,
)
def test_pressure_roundtrips_through_handle_report():
    """A 0.0..1.0 pressure float must round-trip to the 0..8191 HID value."""
    from server.mac_pen_injector import MacPenInjector  # noqa: F401
    pytest.fail(
        "Wave 4 (02-10) asserts pressure=0.5 packs to ~4095 in the "
        "report bytes captured by the IOHIDUserDeviceHandleReport mock"
    )
