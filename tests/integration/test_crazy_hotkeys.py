"""INPUT-04 - 'crazy Flame hotkey combos' in-process loopback. Wave 0 stub.

Wave 5 (02-11) wires the synthetic input generator + Xvfb fixture + server
loopback. This file exists in Wave 0 so CI collects it cleanly and Wave 5
executors can extend rather than invent test shape.
"""
import pytest

pytestmark = pytest.mark.asyncio


@pytest.mark.flame_critical
@pytest.mark.xfail(reason="Wave 5 - in-process loopback not wired", strict=False)
async def test_ctrl_shift_alt_p_roundtrips_to_server():
    pytest.fail(
        "Wave 5 (02-11) drives ClientSession with synthetic Ctrl+Shift+Alt+P "
        "and asserts server-side scan_codes"
    )


@pytest.mark.flame_critical
@pytest.mark.xfail(reason="Wave 5 - Cmd<->Ctrl swap test not wired", strict=False)
async def test_cmd_s_on_linux_bookmark_injects_as_ctrl_s():
    pytest.fail(
        "Wave 5 (02-11) asserts swap_cmd_ctrl=True rewrites Cmd+S to Ctrl+S "
        "in the injected event"
    )


@pytest.mark.flame_critical
@pytest.mark.xfail(reason="Wave 5 - dead-key TextCommit not wired", strict=False)
async def test_german_umlaut_deadkey_commits_as_textcommit():
    pytest.fail(
        "Wave 5 (02-11) asserts DE dead-key sequence becomes a TextCommitMsg, "
        "not synthesized keys"
    )
