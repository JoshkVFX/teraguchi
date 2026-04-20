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
        # Phase 3 D-11 — cadence tightened from 5s to 1s so the push-
        # complement check (MacScreenCapture._hotplug_pending on macOS)
        # has a fast safety net. The 1s poll still covers the case where
        # the NSWorkspace notification is missed (sleep/wake, runloop
        # suspension). Linux keeps the same poll cadence; the cost is
        # one extra mss.mss() probe per 4s on a topology that never
        # changes, which is negligible.
        while self._running:
            await asyncio.sleep(1.0)
            runtime = self._runtime
            if not runtime.capture:
                continue
            pending = getattr(runtime.capture, "_hotplug_pending", False)
            if pending or runtime.capture.detect_hotplug():
                if pending:
                    # Clear the push flag; the delegate will re-set it on
                    # the next display configuration change.
                    try:
                        runtime.capture._hotplug_pending = False
                    except Exception:
                        pass
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
                # Phase 3 D-02 + D-09 prep — re-apply per-session crop
                # after geometry change so the new topology takes effect
                # on the next frame. Plan 05 builds the fall-back-to-
                # primary broadcast on top of this site (apply_capture_mode
                # returning False flips capture_mode_degraded=True; the
                # banner toast reads that flag).
                apply_capture_mode = getattr(
                    runtime, "apply_capture_mode", None,
                )
                if apply_capture_mode is not None:
                    for ws, cs in list(runtime.clients.items()):
                        if not getattr(cs, "authenticated", False):
                            continue
                        mode = getattr(cs, "capture_mode", "mirror_all")
                        if mode == "mirror_all":
                            continue
                        try:
                            apply_capture_mode(
                                cs,
                                mode,
                                getattr(cs, "picked_monitor_id", -1),
                                getattr(cs, "picked_monitor_name", ""),
                            )
                        except Exception as e:
                            logger.debug(
                                "hotplug.reapply_capture_mode_failed err=%s", e,
                            )

    def start(self) -> None:
        self._running = True
        self._task = asyncio.ensure_future(self.run())

    def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
