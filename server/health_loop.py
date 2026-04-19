"""Health ping loop — extracted from server/main.py::SessionRuntime.

D-11 extraction (Plan 01-10). Every 2 seconds, broadcast a HealthPong
stamped with the server-side FSM state (STAB-06 / Plan 01-08 inversion:
server originates the pong, client originates HealthPing) plus the
HealthStats JSON to every authenticated client. Behavior preserved
exactly from the pre-extraction monolith.
"""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Optional

from common.messages import HealthPong

if TYPE_CHECKING:
    from server.main import SessionRuntime


logger = logging.getLogger("teraguchi.server.health_loop")


class HealthLoop:
    """Every 2 s: build HealthPong + HealthStats for every auth'd client.

    The direction-inversion (server emits pong, not ping) landed in Plan
    01-08 so the server — the authoritative FSM — can stamp
    ``server_state`` on every beat. This loop is the hook OBS-03 (Plan
    17) will eventually extend with state-disagreement metrics.
    """

    def __init__(self, runtime: "SessionRuntime") -> None:
        self._runtime = runtime
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def run(self) -> None:
        while self._running:
            await asyncio.sleep(2.0)
            if not self._runtime.clients:
                continue
            seq = self._runtime.health.next_ping_sequence()
            stats_json = self._runtime.health.get_stats().to_json()
            for ws, cs in list(self._runtime.clients.items()):
                if cs.authenticated:
                    try:
                        # STAB-06 / Plan 01-08: server emits HealthPong
                        # stamped with server_state. Client originates
                        # HealthPing. See server/main.py
                        # ::SessionRuntime.handle_input for the inverse
                        # ingress path (HEALTH_PING → record + pair-check).
                        pong = HealthPong(
                            sequence=seq,
                            server_state=cs.fsm.current_state.id,
                        )
                        await cs.enqueue(pong.to_json())
                        await cs.enqueue(stats_json)
                    except Exception:
                        pass

    def start(self) -> None:
        self._running = True
        self._task = asyncio.ensure_future(self.run())

    def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
