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


def test_key_event_extended_with_caps_num_scroll_lock_bits():
    """D-14 — Caps / Num / Scroll Lock state bits on every KeyEvent.

    Client sends lock-state with every keystroke; server auto-corrects
    its virtual display's lock state on mismatch. Zero round-trip cost;
    state re-converges on the next keystroke. Phase 2 promotes KEY_EVENT
    from a raw dict to a ``@dataclass`` with the three lock-state bits
    as new fields (default False = Phase 1 wire compat).
    """
    from common.messages import KeyEventMsg, MsgType, parse_message
    msg = KeyEventMsg(
        scan_code=30, pressed=True,
        caps_lock_on=True, num_lock_on=False, scroll_lock_on=False,
    )
    parsed = parse_message(msg.to_json())
    assert parsed["type"] == MsgType.KEY_EVENT
    assert parsed["scan_code"] == 30
    assert parsed["pressed"] is True
    assert parsed["caps_lock_on"] is True
    assert parsed["num_lock_on"] is False
    assert parsed["scroll_lock_on"] is False


def test_server_hello_extended_with_color_caps():
    """D-03 — ServerHelloMsg advertises a nested ServerColorCaps block.

    Server capability-probe writes main10 / chroma_422 / chroma_444 +
    a negotiated_state badge. ``asdict`` recurses into the nested
    dataclass so the wire format is ``color_caps: {main10, chroma_422,
    chroma_444, advertised_pix_fmt, negotiated_state}``.

    Per threat T-02-06 (info-disclosure), ServerHelloMsg is sent POST-auth,
    so the capability fingerprint is not emitted on pre-auth endpoints.
    """
    from common.messages import (
        MsgType, ServerColorCaps, ServerHelloMsg, parse_message,
    )
    caps = ServerColorCaps(
        main10=True, chroma_422=False, chroma_444=False,
        negotiated_state="confirmed",
    )
    hello = ServerHelloMsg(server_name="teraguchi-srv", color_caps=caps)
    parsed = parse_message(hello.to_json())
    assert parsed["type"] == MsgType.SERVER_HELLO
    assert parsed["server_name"] == "teraguchi-srv"
    assert parsed["color_caps"]["main10"] is True
    assert parsed["color_caps"]["chroma_422"] is False
    assert parsed["color_caps"]["chroma_444"] is False
    assert parsed["color_caps"]["negotiated_state"] == "confirmed"


def test_color_caps_dataclass_defaults_false():
    """D-03 — ServerColorCaps() default instance surfaces as 'not_supported'.

    Capability-probe failure path — the server refuses to advertise
    10-bit / 4:2:2 / 4:4:4 when hardware can't honestly deliver, and the
    client health overlay renders the ``negotiated_state`` badge so
    artists see state at a glance (no silent fallback).
    """
    from common.messages import ServerColorCaps
    caps = ServerColorCaps()
    assert caps.main10 is False
    assert caps.chroma_422 is False
    assert caps.chroma_444 is False
    assert caps.advertised_pix_fmt == "p010le"
    assert caps.negotiated_state == "not_supported"


def test_unknown_msgtype_still_rejected_like_phase1():
    """Phase 1 parse_message contract preserved.

    tests/common/test_messages.py::test_parse_message_unknown_type_passes_through
    establishes that parse_message is a thin ``json.loads`` — unknown
    type values flow through as plain dicts with no KeyError. Phase 2
    additions MUST not tighten this contract (upstream dispatcher is
    responsible for unknown-type handling, not the parser).
    """
    from common.messages import parse_message
    result = parse_message('{"type": "phase2_bogus_type_xyz"}')
    assert result["type"] == "phase2_bogus_type_xyz"
