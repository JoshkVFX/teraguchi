"""Wave 0 - Phase 2 common/messages.py extensions wire round-trip scaffold.

Mirrors the tests/common/test_messages.py round-trip idiom for the 5 new
message/dataclass surfaces Wave 1 (02-02) lands:

  - KeyResetModifiersMsg  (D-11 release-all-modifiers triggers)
  - TextCommitMsg         (D-15 IME commit string passthrough)
  - PenProximityMsg       (D-19 proximity-event recovery)
  - Extended KeyEventMsg  (D-14 caps/num/scroll-lock bits)
  - Extended ServerHelloMsg (D-03 color_caps dataclass for
                             supports_main10/422/444 + negotiated_state)

Wave 0 role: skeleton only. Each test imports the target symbol inside
the test body so the 7 xfail entries are always collected, matching the
Task 2 acceptance count of exactly 7. Real assertions ship with Wave 1.
"""
from __future__ import annotations

import pytest


def test_key_reset_modifiers_roundtrip():
    """D-11 — release-all-modifiers wire format.

    Client dispatches this on four triggers: focusOut, reconnect, server-
    periodic safety, F9 panic. Reason field is log-only (T-02-04 disposition
    — server always dispatches the same idempotent reset regardless).
    """
    from common.messages import KeyResetModifiersMsg, MsgType, parse_message
    msg = KeyResetModifiersMsg(reason="focus_out")
    parsed = parse_message(msg.to_json())
    assert parsed["type"] == MsgType.KEY_RESET_MODIFIERS
    assert parsed["reason"] == "focus_out"


def test_text_commit_roundtrip():
    """D-15 — IME / dead-key commit string passthrough.

    Layout-independent Unicode commit; server injects via xdotool type
    (Linux) or CGEventKeyboardSetUnicodeString (macOS) — NOT as synthesized
    keycodes which would mangle dead-key composition.
    """
    from common.messages import MsgType, TextCommitMsg, parse_message
    # Japanese hiragana — exercises the Unicode passthrough contract
    msg = TextCommitMsg(text="あ")
    parsed = parse_message(msg.to_json())
    assert parsed["type"] == MsgType.TEXT_COMMIT
    assert parsed["text"] == "あ"


def test_pen_proximity_roundtrip():
    """D-19 — proximity-event recovery on focusIn / showEvent.

    Idempotent on the server side (PenFSM tolerates duplicate enters).
    """
    from common.messages import MsgType, PenProximityMsg, parse_message
    msg = PenProximityMsg(in_proximity=True, pen_type="eraser")
    parsed = parse_message(msg.to_json())
    assert parsed["type"] == MsgType.PEN_PROXIMITY
    assert parsed["in_proximity"] is True
    assert parsed["pen_type"] == "eraser"


@pytest.mark.xfail(reason="Wave 1 - 02-02 extended KeyEvent bits", strict=False)
def test_key_event_extended_with_caps_num_scroll_lock_bits():
    from common.messages import KeyEventMsg, parse_message  # noqa: F401
    pytest.fail(
        "Wave 1 (02-02) promotes KeyEvent to a @dataclass and asserts "
        "caps_lock_on / num_lock_on / scroll_lock_on bits round-trip"
    )


@pytest.mark.xfail(reason="Wave 1 - 02-02 extended ServerHello color caps", strict=False)
def test_server_hello_extended_with_color_caps():
    from common.messages import ServerHelloMsg, parse_message  # noqa: F401
    pytest.fail(
        "Wave 1 (02-02) asserts ServerHelloMsg exposes supports_main10, "
        "supports_422, supports_444 and color_negotiated_state"
    )


@pytest.mark.xfail(reason="Wave 1 - 02-02 ColorCaps dataclass defaults", strict=False)
def test_color_caps_dataclass_defaults_false():
    from common.messages import ColorCaps  # noqa: F401
    pytest.fail(
        "Wave 1 (02-02) asserts ColorCaps() defaults all booleans to False "
        "so capability-probe failure surfaces as 'not_supported'"
    )


@pytest.mark.xfail(reason="Wave 1 - 02-02 parser invariant preserved", strict=False)
def test_unknown_msgtype_still_rejected_like_phase1():
    from common.messages import parse_message  # noqa: F401
    pytest.fail(
        "Wave 1 (02-02) asserts parse_message preserves the Phase 1 "
        "pass-through contract for unknown msg types (no KeyError)"
    )
