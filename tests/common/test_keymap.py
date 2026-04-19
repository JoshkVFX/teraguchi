"""STAB-01 — Qt key → Linux evdev scan code table coverage.

Target-read divergence note:
``qt_key_to_linux_scancode(qt_key: int) -> int`` takes only a single integer Qt
key code. There is NO modifier bitmask argument — modifier keys are themselves
entries in the table (Shift, Ctrl, Alt, Meta) and the server layer issues them
as separate scancode events. So the "chord" tests verify that each modifier
has its own scancode and that a letter scancode is unchanged by what the
caller does alongside it.

Unmapped keys return 0 per the docstring contract.
"""
import pytest

from common.keymap import QT_KEY_TO_LINUX, qt_key_to_linux_scancode

# PySide6 key codes — use integer literals to keep this test PySide6-free.
# Values match `Qt.Key_*` enum integers.
QT_KEY_A = 0x41
QT_KEY_Z = 0x5A
QT_KEY_0 = 0x30
QT_KEY_9 = 0x39
QT_KEY_F1 = 0x01000030
QT_KEY_F12 = 0x0100003B
QT_KEY_SHIFT = 0x01000020
QT_KEY_CTRL = 0x01000021
QT_KEY_ALT = 0x01000023
QT_KEY_META = 0x01000022
QT_KEY_SPACE = 0x20
QT_KEY_RETURN = 0x01000004
QT_KEY_ESCAPE = 0x01000001


# ─── Letters ──────────────────────────────────────────────────────────────


def test_letters_a_through_z_all_map_to_positive_scancode():
    """Every ASCII letter must have a valid positive scancode — this is the
    bread-and-butter Flame-session keystroke path."""
    for code in range(QT_KEY_A, QT_KEY_Z + 1):
        sc = qt_key_to_linux_scancode(code)
        assert isinstance(sc, int) and sc > 0, f"key 0x{code:X} → {sc}"


@pytest.mark.parametrize("qt_key,expected_scancode", [
    (0x41, 30),   # A → KEY_A
    (0x5A, 44),   # Z → KEY_Z
    (0x51, 16),   # Q → KEY_Q
    (0x50, 25),   # P → KEY_P
])
def test_letter_scancodes_match_evdev_table(qt_key, expected_scancode):
    """Spot-check: scancodes match the Linux ``KEY_*`` numeric constants."""
    assert qt_key_to_linux_scancode(qt_key) == expected_scancode


# ─── Digits ───────────────────────────────────────────────────────────────


def test_digits_0_through_9_all_map_to_positive_scancode():
    for code in range(QT_KEY_0, QT_KEY_9 + 1):
        sc = qt_key_to_linux_scancode(code)
        assert isinstance(sc, int) and sc > 0, f"key 0x{code:X} → {sc}"


# ─── Function keys ────────────────────────────────────────────────────────


def test_function_keys_f1_through_f12_all_have_scancodes():
    """Flame's F-key hotkeys are load-bearing (muscle memory)."""
    for code in range(QT_KEY_F1, QT_KEY_F12 + 1):
        sc = qt_key_to_linux_scancode(code)
        assert isinstance(sc, int) and sc > 0, f"F-key 0x{code:X} → {sc}"


# ─── Modifier chord path ──────────────────────────────────────────────────
# The real signature takes only one arg — modifiers are sent as their own
# scancode events by the injection layer. These tests lock in that each
# modifier has its own valid scancode AND that a letter scancode is stable
# (i.e. pressing the modifier doesn't somehow affect the letter mapping).


def test_all_four_modifiers_have_distinct_scancodes():
    """Ctrl / Shift / Alt / Meta must all map to distinct KEY_* codes — no
    silent aliasing on the Flame modifier-chord path."""
    shift = qt_key_to_linux_scancode(QT_KEY_SHIFT)
    ctrl = qt_key_to_linux_scancode(QT_KEY_CTRL)
    alt = qt_key_to_linux_scancode(QT_KEY_ALT)
    meta = qt_key_to_linux_scancode(QT_KEY_META)
    assert shift == 42   # KEY_LEFTSHIFT
    assert ctrl == 29    # KEY_LEFTCTRL
    assert alt == 56     # KEY_LEFTALT
    assert meta == 125   # KEY_LEFTMETA
    assert len({shift, ctrl, alt, meta}) == 4


def test_ctrl_shift_alt_p_stability():
    """The canonical Ctrl+Shift+Alt+P smoke chord — verify each component of
    the chord maps to its documented KEY_* code, and the letter scancode is
    independent of the modifier stack (signature takes one arg)."""
    assert qt_key_to_linux_scancode(QT_KEY_CTRL) == 29
    assert qt_key_to_linux_scancode(QT_KEY_SHIFT) == 42
    assert qt_key_to_linux_scancode(QT_KEY_ALT) == 56
    p_scancode = qt_key_to_linux_scancode(0x50)   # KEY_P
    assert p_scancode == 25
    # Calling it again with no modifiers must return the same answer — guard
    # against any future stateful side effect in the lookup.
    assert qt_key_to_linux_scancode(0x50) == 25


# ─── Symbols + navigation ─────────────────────────────────────────────────


@pytest.mark.parametrize("qt_key,expected", [
    (QT_KEY_SPACE, 57),     # KEY_SPACE
    (QT_KEY_RETURN, 28),    # KEY_ENTER
    (QT_KEY_ESCAPE, 1),     # KEY_ESC
    (0x01000003, 14),       # Key_Backspace → KEY_BACKSPACE
    (0x01000007, 111),      # Key_Delete → KEY_DELETE
])
def test_nav_and_symbol_keys_map_correctly(qt_key, expected):
    assert qt_key_to_linux_scancode(qt_key) == expected


# ─── Negative path ────────────────────────────────────────────────────────


def test_unknown_key_returns_zero():
    """Per the docstring contract — unmapped keys return 0, not KeyError."""
    assert qt_key_to_linux_scancode(0xDEADBEEF) == 0


def test_table_contains_full_ascii_letter_range():
    """Guard: the QT_KEY_TO_LINUX dict must cover every letter — a regression
    here would silently eat a Flame keystroke."""
    missing = [0x41 + i for i in range(26) if (0x41 + i) not in QT_KEY_TO_LINUX]
    assert missing == [], f"letters missing from table: {missing}"


# =============================================================================
# Phase 2 Wave 1 (02-03) — D-12 exhaustive Qt × modifier × {linux, mac} matrix.
# Plan 02-03 fills in QT_KEY_TO_MAC_VK + qt_key_to_mac_vk() + FLAME_CRITICAL_CHORDS.
# =============================================================================


@pytest.mark.skip(reason="Wave 1 - QT_KEY_TO_MAC_VK table lands in 02-03")
def test_qt_key_to_mac_vk_letter_a_returns_kvk_ansi_a():
    from common.keymap import qt_key_to_mac_vk  # noqa: F401
    assert qt_key_to_mac_vk(0x41) == 0x00  # kVK_ANSI_A


@pytest.mark.skip(reason="Wave 1 - FLAME_CRITICAL_CHORDS constant lands in 02-03")
def test_flame_critical_chords_exist():
    from common.keymap import FLAME_CRITICAL_CHORDS  # noqa: F401
    assert len(FLAME_CRITICAL_CHORDS) >= 20


@pytest.mark.skip(reason="Wave 1 - swap_cmd_ctrl helper lands in 02-03")
def test_swap_cmd_ctrl_for_linux_dest_inverts_cmd_to_ctrl():
    from common.keymap import swap_cmd_ctrl_for_linux_dest  # noqa: F401
    # Qt Meta (0x01000022) should become Qt Control (0x01000021) when dest=linux
    out_key, out_mods = swap_cmd_ctrl_for_linux_dest(0x01000022, 0)
    assert out_key == 0x01000021
