"""
Machine pool management — tracks Flame workstations, health, and assignments.

Maintains a registry of available machines, probes their health,
and assigns users to machines based on pool mode (dedicated/floating).
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

HEALTH_INTERVAL = 15.0     # seconds between health probes
HEALTH_FAIL_THRESHOLD = 3  # consecutive failures to mark unhealthy
HEALTH_OK_THRESHOLD = 2    # consecutive successes to mark healthy


class PoolMode(str, Enum):
    FLOATING = "floating"
    DEDICATED = "dedicated"


@dataclass
class Machine:
    """A Teragucci server in the pool."""
    name: str = ""
    host: str = ""
    port: int = 4443
    pool: str = "floating"
    assigned_user: str = ""       # For dedicated: permanent user
    gpu: str = ""
    priority: int = 10            # Lower = preferred
    tags: list = field(default_factory=list)

    # Runtime state (not from config)
    healthy: bool = False
    active_sessions: list = field(default_factory=list)
    last_probe: float = 0.0
    consecutive_ok: int = 0
    consecutive_fail: int = 0
    load_avg: float = 0.0
    uptime_s: int = 0

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "host": self.host,
            "port": self.port,
            "pool": self.pool,
            "gpu": self.gpu,
            "priority": self.priority,
            "tags": self.tags,
            "healthy": self.healthy,
            "active_sessions": self.active_sessions,
            "load_avg": self.load_avg,
        }


class MachinePool:
    """Manages the fleet of Teragucci servers."""

    def __init__(self, machines_config: list[dict]):
        self._machines: dict[str, Machine] = {}
        for cfg in machines_config:
            m = Machine(**{k: v for k, v in cfg.items()
                          if k in Machine.__dataclass_fields__})
            self._machines[m.name] = m
        self._probe_task: Optional[asyncio.Task] = None
        logger.info("Pool initialized: %d machines", len(self._machines))

    @property
    def machines(self) -> dict[str, Machine]:
        return self._machines

    def start_health_probes(self):
        """Start background health check loop."""
        if self._probe_task is None:
            self._probe_task = asyncio.ensure_future(self._probe_loop())

    def stop(self):
        if self._probe_task:
            self._probe_task.cancel()
            self._probe_task = None

    async def _probe_loop(self):
        """Periodically probe all machines."""
        while True:
            try:
                await self._probe_all()
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.error("Probe loop error: %s", e)
            await asyncio.sleep(HEALTH_INTERVAL)

    async def _probe_all(self):
        """Probe all machines concurrently."""
        tasks = [self._probe_one(m) for m in self._machines.values()]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _probe_one(self, machine: Machine):
        """Probe a single machine's /status endpoint."""
        url = f"https://{machine.host}:{machine.port}/status"
        try:
            async with aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(ssl=False)
            ) as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        machine.active_sessions = data.get("active_sessions", [])
                        machine.load_avg = data.get("load_avg", [0])[0] if data.get("load_avg") else 0
                        machine.uptime_s = data.get("uptime_s", 0)
                        machine.consecutive_ok += 1
                        machine.consecutive_fail = 0
                        if machine.consecutive_ok >= HEALTH_OK_THRESHOLD:
                            if not machine.healthy:
                                logger.info("Machine %s is now healthy", machine.name)
                            machine.healthy = True
                    else:
                        raise Exception(f"HTTP {resp.status}")
        except Exception as e:
            machine.consecutive_fail += 1
            machine.consecutive_ok = 0
            if machine.consecutive_fail >= HEALTH_FAIL_THRESHOLD:
                if machine.healthy:
                    logger.warning("Machine %s is now unhealthy: %s", machine.name, e)
                machine.healthy = False
        machine.last_probe = time.time()

    def assign(self, username: str, groups: list[str]) -> Optional[Machine]:
        """
        Assign a machine to a user.

        Priority:
        1. Dedicated machine for this user
        2. Existing active session (reconnect)
        3. Available floating machine (sorted by priority)
        """
        # 1. Check dedicated assignments
        for m in self._machines.values():
            if m.pool == "dedicated" and m.assigned_user == username:
                if m.healthy:
                    logger.info("Dedicated assignment: %s → %s", username, m.name)
                    return m
                else:
                    logger.warning("Dedicated machine %s unhealthy for %s", m.name, username)
                    return None

        # 2. Check for existing session (reconnect)
        for m in self._machines.values():
            if m.healthy and username in m.active_sessions:
                logger.info("Reconnect: %s → %s", username, m.name)
                return m

        # 3. Find available floating machine
        is_admin = "teragucci-admins" in groups
        available = [
            m for m in self._machines.values()
            if m.healthy and m.pool == "floating" and len(m.active_sessions) == 0
        ]
        if not available:
            # Try machines with sessions if admin (can share)
            if is_admin:
                available = [
                    m for m in self._machines.values()
                    if m.healthy and m.pool == "floating"
                ]
            if not available:
                logger.warning("No machines available for %s", username)
                return None

        # Sort by priority (lower = better), then by session count
        available.sort(key=lambda m: (len(m.active_sessions), m.priority))
        chosen = available[0]
        logger.info("Assigned floating: %s → %s (priority=%d)",
                    username, chosen.name, chosen.priority)
        return chosen

    def get_status(self) -> list[dict]:
        """Get status of all machines."""
        return [m.to_dict() for m in self._machines.values()]

    def release(self, username: str, machine_name: str):
        """Release a machine assignment (for session tracking)."""
        m = self._machines.get(machine_name)
        if m and username in m.active_sessions:
            m.active_sessions.remove(username)
            logger.info("Released: %s from %s", username, machine_name)
