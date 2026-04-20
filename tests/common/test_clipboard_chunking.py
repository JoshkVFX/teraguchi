"""Phase 3 D-17 — ClipboardChunkAssembler (chunked clipboard transport).

Wave 0 skeleton (Plan 03-01 Task 2). Implementation lands in Plan 03-06
as ``common/clipboard_chunks.py`` — the assembler buffers incoming
ClipboardChunkMsg frames by ``sequence_id`` and emits a reassembled
payload when all chunks for a sequence arrive.

The wire-shape contract for :class:`ClipboardChunkMsg` ships in Plan
03-01 Task 1 (``common/messages.py``). These tests are RED until the
assembler module exists.

Threat T-03-03 (DoS via maxint ``total_chunks``) requires the assembler
to bound the chunk count at 256; the out-of-range test below locks that
contract.
"""
import pytest


def test_assembler_in_order_returns_full_payload():
    """D-17 — in-order chunk assembly emits full payload on the last chunk."""
    pytest.importorskip("common.clipboard_chunks")
    pytest.skip("Wave 0 skeleton — implementation in Plan 03-06 (D-17)")


def test_assembler_handles_out_of_order_chunks():
    """D-17 — chunk order-independence (JSON control channel may reorder)."""
    pytest.importorskip("common.clipboard_chunks")
    pytest.skip("Wave 0 skeleton — implementation in Plan 03-06 (D-17)")


def test_assembler_idempotent_duplicate_chunk_index():
    """D-17 — duplicate ``chunk_index`` for a sequence is an idempotent ignore."""
    pytest.importorskip("common.clipboard_chunks")
    pytest.skip("Wave 0 skeleton — implementation in Plan 03-06 (D-17)")


def test_assembler_drops_out_of_range_chunk_index():
    """Threat T-03-03 — chunk_index outside [0, total_chunks) is dropped."""
    pytest.importorskip("common.clipboard_chunks")
    pytest.skip("Wave 0 skeleton — implementation in Plan 03-06 (D-17, T-03-03)")


def test_assembler_is_stale_after_timeout():
    """D-17 — :meth:`ClipboardChunkAssembler.is_stale` trims orphan sequences.

    Stops an attacker from pinning memory by sending chunk 0 of 256 and
    never completing the sequence. Timeout constant lives in the
    assembler module (CHUNK_TIMEOUT_S).
    """
    pytest.importorskip("common.clipboard_chunks")
    pytest.skip("Wave 0 skeleton — implementation in Plan 03-06 (D-17)")
