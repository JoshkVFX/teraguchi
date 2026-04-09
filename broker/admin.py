"""
Broker Admin HTTP API — manages machine assignments via REST + web UI.

Runs on a separate port from the WebSocket broker. Authenticates via
PAM Basic Auth and requires teragucci-admins group membership.
"""

import asyncio
import base64
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

import yaml
from aiohttp import web

logger = logging.getLogger(__name__)


AUTH_CACHE_TTL = 300  # 5 minutes — cache PAM auth to avoid pam_sss rate limits


class AdminServer:
    """HTTP admin API for the Teragucci broker."""

    def __init__(self, pool, ipa, config_path: str, admin_group: str = "teragucci-admins"):
        self._pool = pool
        self._ipa = ipa
        self._config_path = config_path
        self._admin_group = admin_group
        self._lock = asyncio.Lock()
        self._runner: Optional[web.AppRunner] = None
        self._group_cache: dict = {}
        self._auth_cache: dict = {}  # "user:hash" → expiry timestamp

    def _authenticate(self, request: web.Request) -> Optional[str]:
        """Validate Basic Auth via PAM (with cache), return username or None."""
        import hashlib
        import time

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Basic "):
            return None

        try:
            decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
            username, password = decoded.split(":", 1)
        except Exception:
            return None

        # Check auth cache to avoid PAM rate limiting
        cache_key = hashlib.sha256(f"{username}:{password}".encode()).hexdigest()
        cached = self._auth_cache.get(cache_key)
        if cached and cached > time.time():
            return username

        try:
            from server.pam_auth import PAMAuthenticator
            pam = PAMAuthenticator()
            if not pam.authenticate(username, password):
                return None
        except Exception as e:
            logger.error("PAM auth error: %s", e)
            return None

        # Check admin group
        groups = self._ipa.get_user_groups_cached(username, self._group_cache, ttl=60)
        if self._admin_group not in groups:
            logger.warning("Admin UI: %s not in %s", username, self._admin_group)
            return None

        # Cache successful auth
        self._auth_cache[cache_key] = time.time() + AUTH_CACHE_TTL
        return username

    @web.middleware
    async def auth_middleware(self, request: web.Request, handler):
        # Skip auth for static files and the login check
        if request.path == "/api/ping":
            return await handler(request)

        username = self._authenticate(request)
        if not username:
            return web.Response(
                status=401,
                headers={"WWW-Authenticate": 'Basic realm="Teragucci Admin"'},
                text="Authentication required",
            )
        request["username"] = username
        return await handler(request)

    # ── API Routes ──────────────────────────────────

    async def handle_index(self, request: web.Request):
        """Serve the admin UI."""
        static_dir = Path(__file__).parent / "static"
        index = static_dir / "index.html"
        if index.exists():
            return web.FileResponse(index)
        return web.Response(text="Admin UI not found", status=404)

    async def handle_get_machines(self, request: web.Request):
        """GET /api/machines — all machines with health and assignment info."""
        return web.json_response(self._pool.get_status())

    async def handle_get_assignments(self, request: web.Request):
        """GET /api/assignments — current user→machines map."""
        result = {}
        for user, names in self._pool._user_machines.items():
            result[user] = sorted(names)
        return web.json_response(result)

    async def handle_put_assignments(self, request: web.Request):
        """PUT /api/assignments — replace the full assignment map."""
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON"}, status=400)

        if not isinstance(data, dict):
            return web.json_response({"error": "Expected object"}, status=400)

        # Validate: values must be lists of strings
        for user, machines in data.items():
            if not isinstance(machines, list):
                return web.json_response(
                    {"error": f"Value for {user} must be a list"}, status=400)
            for m in machines:
                if m not in self._pool.machines:
                    return web.json_response(
                        {"error": f"Unknown machine: {m}"}, status=400)

        async with self._lock:
            self._save_assignments(data)
            self._pool.update_assignments(data)

        logger.info("Assignments updated by %s: %s", request.get("username"), data)
        return web.json_response({"ok": True})

    async def handle_set_user(self, request: web.Request):
        """POST /api/assignments/{user} — set machines for one user."""
        user = request.match_info["user"]
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON"}, status=400)

        machines = data.get("machines", [])
        if not isinstance(machines, list):
            return web.json_response({"error": "machines must be a list"}, status=400)

        for m in machines:
            if m not in self._pool.machines:
                return web.json_response({"error": f"Unknown machine: {m}"}, status=400)

        async with self._lock:
            # Read current assignments, update one user, save
            current = {u: sorted(names) for u, names in self._pool._user_machines.items()}
            if machines:
                current[user] = machines
            else:
                current.pop(user, None)
            self._save_assignments(current)
            self._pool.update_assignments(current)

        action = "assigned" if machines else "removed"
        logger.info("User %s %s by %s: %s", user, action, request.get("username"), machines)
        return web.json_response({"ok": True})

    async def handle_delete_user(self, request: web.Request):
        """DELETE /api/assignments/{user} — remove user's assignment."""
        user = request.match_info["user"]

        async with self._lock:
            current = {u: sorted(names) for u, names in self._pool._user_machines.items()}
            if user not in current:
                return web.json_response({"error": f"User {user} has no assignment"}, status=404)
            del current[user]
            self._save_assignments(current)
            self._pool.update_assignments(current)

        logger.info("Assignment removed for %s by %s", user, request.get("username"))
        return web.json_response({"ok": True})

    # ── Persistence ─────────────────────────────────

    def _save_assignments(self, assignments: dict):
        """Atomic write: update only the assignments key in broker.yml."""
        config = {}
        if os.path.exists(self._config_path):
            with open(self._config_path) as f:
                config = yaml.safe_load(f) or {}

        config["assignments"] = assignments

        # Atomic write: write to temp file, then rename
        config_dir = os.path.dirname(self._config_path)
        fd, tmp_path = tempfile.mkstemp(dir=config_dir, suffix=".yml")
        try:
            with os.fdopen(fd, "w") as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False)
            os.replace(tmp_path, self._config_path)
        except Exception:
            os.unlink(tmp_path)
            raise

    # ── Server Lifecycle ────────────────────────────

    async def start(self, host: str = "0.0.0.0", port: int = 8080,
                    tls_context=None):
        """Start the admin HTTP server."""
        app = web.Application(middlewares=[self.auth_middleware])

        app.router.add_get("/", self.handle_index)
        app.router.add_get("/api/machines", self.handle_get_machines)
        app.router.add_get("/api/assignments", self.handle_get_assignments)
        app.router.add_put("/api/assignments", self.handle_put_assignments)
        app.router.add_post("/api/assignments/{user}", self.handle_set_user)
        app.router.add_delete("/api/assignments/{user}", self.handle_delete_user)

        # Serve static files
        static_dir = Path(__file__).parent / "static"
        if static_dir.exists():
            app.router.add_static("/static/", static_dir)

        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, host, port, ssl_context=tls_context)
        await site.start()
        logger.info("Admin UI running on %s:%d", host, port)

    async def stop(self):
        if self._runner:
            await self._runner.cleanup()
