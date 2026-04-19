"""Monitor hot-plug loop — extracted from SessionRuntime.

D-11 extraction (Plan 01-10 Task 2). Every 5 seconds, poll the
``ScreenCapture.detect_hotplug()`` sentinel; if a change is detected,
broadcast the refreshed monitor list to every authenticated client and
restart the encoder so the new framebuffer geometry takes effect.

Behavior preserved exactly from the pre-extraction monolith's
``_monitor_hotplug_loop``. The encoder-restart call now goes through
``EncoderLifecycle.restart()`` (the original called
``_restart_encoder`` on SessionRuntime directly).
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict
from typing import TYPE_CHECKING, Optional

from common.messages import MonitorListMsg

if TYPE_CHECKING:
    # D-11 / Plan 01-11 Task 2: SessionRuntime moved to server/session_runtime.py
    from server.session_runtime import SessionRuntime


logger = logging.getLogger("teraguchi.server.monitor_hotplug")


class MonitorHotplug:
    """Polls the capture backend for monitor hot-plug events. One
    instance per SessionRuntime."""

    def __init__(self, runtime: "SessionRuntime") -> None:
        self._runtime = runtime
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def run(self) -> None:
        while self._running:
            await asyncio.sleep(5.0)
            runtime = self._runtime
            if runtime.capture and runtime.capture.detect_hotplug():
                monitors = [asdict(m) for m in runtime.capture.list_monitors()]
                msg_json = MonitorListMsg(monitors=monitors).to_json()
                for ws, cs in list(runtime.clients.items()):
                    if cs.authenticated:
                        try:
                            await cs.enqueue(msg_json)
                        except Exception:
                            pass
                if runtime.encoder:
                    runtime.encoder_lifecycle.restart()

    def start(self) -> None:
        self._running = True
        self._task = asyncio.ensure_future(self.run())

    def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
