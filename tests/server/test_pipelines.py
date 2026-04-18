"""STAB-04 + STAB-07 pipeline-queue regression tests.

These tests guard the send_queue bounded-queue + IDR-on-drop policy applied
to server/main.py::ClientSession. The bug they regress is a ~2s GOP stall
when a single P-frame is dropped without requesting an IDR.
"""
import asyncio

import pytest

from server.main import ClientSession


class _FakeRuntime:
    def __init__(self, encoder):
        self.encoder = encoder


@pytest.fixture
def session_with_fake_encoder(fake_ws, fake_encoder):
    cs = ClientSession(fake_ws)
    cs.runtime = _FakeRuntime(fake_encoder)
    cs.authenticated = True
    return cs


@pytest.mark.asyncio
async def test_send_queue_maxsize_is_four(session_with_fake_encoder):
    """STAB-04 guard: maxsize must be 4, not 30."""
    assert session_with_fake_encoder.send_queue.maxsize == 4


@pytest.mark.asyncio
async def test_enqueue_drops_oldest_on_full(session_with_fake_encoder):
    """Queue full -> drop OLDEST item, new item enters."""
    cs = session_with_fake_encoder
    for i in range(4):
        ok = await cs.enqueue(f"p-{i}".encode(), is_keyframe=False)
        assert ok, f"enqueue {i} should succeed while under maxsize"
    # 5th enqueue overflows
    ok = await cs.enqueue(b"p-4", is_keyframe=False)
    assert ok is False, "5th enqueue should report drop"
    # Queue should still have 4 items; the OLDEST (p-0) is gone, newest (p-4) is present
    items = []
    while not cs.send_queue.empty():
        items.append(cs.send_queue.get_nowait())
    assert b"p-4" in items, "newest frame should be present post-drop"
    assert b"p-0" not in items, "oldest frame should have been evicted"


@pytest.mark.asyncio
async def test_send_queue_idr_on_drop(session_with_fake_encoder):
    """STAB-04 core assertion: first drop of a streak requests exactly one IDR."""
    cs = session_with_fake_encoder
    # Fill queue (4 successes) then overflow 3 times
    for i in range(4):
        await cs.enqueue(f"p-{i}".encode(), is_keyframe=False)
    for i in range(3):
        await cs.enqueue(f"overflow-{i}".encode(), is_keyframe=False)
    # Exactly one IDR request across 3 drops (first-of-streak rule)
    assert cs.runtime.encoder.keyframe_requests == 1, (
        f"expected 1 IDR per drop streak, got {cs.runtime.encoder.keyframe_requests}"
    )


@pytest.mark.asyncio
async def test_send_queue_keyframe_resets_drop_counter(session_with_fake_encoder):
    """After a keyframe enqueue, the drop-streak counter resets -> next drop requests a fresh IDR."""
    cs = session_with_fake_encoder
    # Streak 1
    for i in range(4):
        await cs.enqueue(f"p-{i}".encode(), is_keyframe=False)
    await cs.enqueue(b"overflow", is_keyframe=False)
    assert cs.runtime.encoder.keyframe_requests == 1

    # Keyframe enqueue clears queue + resets counter
    await cs.enqueue(b"keyframe-data", is_keyframe=True)
    assert cs._drops_since_keyframe == 0

    # Streak 2 — fresh IDR request expected
    for i in range(4):
        await cs.enqueue(f"p2-{i}".encode(), is_keyframe=False)
    await cs.enqueue(b"overflow-2", is_keyframe=False)
    assert cs.runtime.encoder.keyframe_requests == 2
