"""
Broker Admin HTTP API — manages machine assignments via REST + web UI.

Served on the same port as the broker WebSocket server via the
process_request hook. Authenticates via LDAP Basic Auth and requires
teragucci-admins group membership.
"""

import asyncio
import base64
import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

AUTH_CACHE_TTL = 300  # 5 minutes

# Admin URL paths — anything starting with these is handled by the admin server
ADMIN_PATHS = ("/", "/api/", "/static/")


class AdminServer:
    """HTTP admin API for the Teragucci broker, served via websockets process_request."""

    def __init__(self, pool, ipa, config_path: str, admin_group: str = "teragucci-admins",
                 assignments_path: Optional[str] = None):
        self._pool = pool
        self._ipa = ipa
        self._config_path = config_path
        self._assignments_path = assignments_path or config_path
        self._admin_group = admin_group
        self._lock = asyncio.Lock()
        self._group_cache: dict = {}
        self._auth_cache: dict = {}

    # ── Auth ─────────────────────────────────────────

    def _authenticate_headers(self, headers) -> Optional[str]:
        """Validate Basic Auth from request headers, return username or None."""
        auth_header = headers.get("Authorization", "")
        if not auth_header.startswith("Basic "):
            return None

        try:
            decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
            username, password = decoded.split(":", 1)
        except Exception:
            return None

        cache_key = hashlib.sha256(f"{username}:{password}".encode()).hexdigest()
        cached = self._auth_cache.get(cache_key)
        if cached and cached > time.time():
            return username

        if not self._ldap_bind_auth(username, password):
            return None

        groups = self._ipa.get_user_groups_cached(username, self._group_cache, ttl=60)
        if self._admin_group not in groups:
            logger.warning("Admin UI: %s not in %s", username, self._admin_group)
            return None

        self._auth_cache[cache_key] = time.time() + AUTH_CACHE_TTL
        return username

    def _ldap_bind_auth(self, username: str, password: str) -> bool:
        """Authenticate by LDAP simple bind to FreeIPA."""
        try:
            import ldap
        except ImportError:
            logger.error("python-ldap not installed — cannot authenticate")
            return False

        base_dn = self._ipa._base_dn
        user_dn = f"uid={username},cn=users,cn=accounts,{base_dn}"

        for uri in self._ipa._servers:
            try:
                conn = ldap.initialize(uri)
                conn.set_option(ldap.OPT_PROTOCOL_VERSION, 3)
                conn.set_option(ldap.OPT_REFERRALS, 0)
                conn.set_option(ldap.OPT_NETWORK_TIMEOUT, 5)
                conn.simple_bind_s(user_dn, password)
                conn.unbind_s()
                return True
            except ldap.INVALID_CREDENTIALS:
                logger.warning("LDAP auth failed for %s: invalid credentials", username)
                return False
            except Exception as e:
                logger.warning("LDAP bind failed (%s): %s", uri, e)
                continue

        logger.error("LDAP auth: cannot reach any FreeIPA server")
        return False

    # ── process_request hook for websockets ──────────

    async def process_request(self, connection, request):
        """
        Called by websockets server for every incoming request.
        Returns a Response for admin routes, or None for WebSocket upgrade.

        websockets 15 API: process_request(connection, request) -> Response | None
        """
        from websockets.datastructures import Headers as WsHeaders
        from websockets.http11 import Response

        path = request.path
        headers = request.headers

        # Store path and headers on the connection for use in handle_client
        connection._admin_path = path
        connection._admin_headers = headers

        # Let WebSocket upgrade requests pass through
        if "websocket" in headers.get("Upgrade", "").lower():
            return None

        # Only handle admin paths
        if not any(path.startswith(p) for p in ADMIN_PATHS):
            return None

        def make_response(status, header_list, body):
            h = WsHeaders()
            for k, v in header_list:
                h[k] = v
            return Response(status, "", h, body)

        # Authenticate
        if path != "/api/ping":
            username = self._authenticate_headers(headers)
            if not username:
                return make_response(401, [
                    ("WWW-Authenticate", 'Basic realm="Teragucci Admin"'),
                    ("Content-Type", "text/plain"),
                ], b"Authentication required")
        else:
            username = None

        # Route
        try:
            status, resp_headers, body = await self._route(path, headers, username)
            return make_response(status, resp_headers, body)
        except Exception as e:
            logger.error("Admin request error: %s", e, exc_info=True)
            return make_response(500, [("Content-Type", "text/plain")], b"Internal server error")

    async def _route(self, path: str, headers, username: Optional[str]):
        """Route admin HTTP requests. Mutations go through the admin WebSocket."""
        # Strip query string from path for routing
        route_path = path.split("?", 1)[0]

        if route_path == "/" or route_path == "/admin" or route_path == "/admin/":
            return self._serve_index()
        elif route_path == "/api/machines":
            return self._json_response(self._pool.get_status())
        elif route_path == "/api/assignments":
            result = {u: sorted(names) for u, names in self._pool._user_machines.items()}
            return self._json_response(result)
        elif route_path == "/api/ws-token":
            # Issue a short-lived token for the admin WebSocket connection
            token = self._issue_ws_token(username)
            return self._json_response({"token": token})
        elif route_path.startswith("/static/"):
            return self._serve_static(route_path)
        elif route_path == "/api/ping":
            return self._json_response({"ok": True})
        else:
            return (404, [("Content-Type", "text/plain")], b"Not found")

    def _issue_ws_token(self, username: str) -> str:
        """Issue a short-lived token that the browser can use to open /admin-ws."""
        import secrets
        token = secrets.token_urlsafe(32)
        expires = time.time() + 60  # 60 seconds
        if not hasattr(self, "_ws_tokens"):
            self._ws_tokens = {}
        # Clean up expired tokens
        now = time.time()
        self._ws_tokens = {t: (u, e) for t, (u, e) in self._ws_tokens.items() if e > now}
        self._ws_tokens[token] = (username, expires)
        return token

    def verify_ws_token(self, token: str) -> Optional[str]:
        """Verify a WebSocket token and return the associated username."""
        if not hasattr(self, "_ws_tokens"):
            return None
        entry = self._ws_tokens.get(token)
        if not entry:
            return None
        username, expires = entry
        if expires < time.time():
            self._ws_tokens.pop(token, None)
            return None
        # Token is single-use
        self._ws_tokens.pop(token, None)
        return username

    def _json_response(self, data, status: int = 200):
        body = json.dumps(data).encode()
        return (status, [("Content-Type", "application/json")], body)

    def _serve_index(self):
        static_dir = Path(__file__).parent / "static"
        index = static_dir / "index.html"
        if index.exists():
            body = index.read_bytes()
            return (200, [("Content-Type", "text/html; charset=utf-8")], body)
        return (404, [("Content-Type", "text/plain")], b"Admin UI not found")

    def _serve_static(self, path: str):
        static_dir = Path(__file__).parent / "static"
        # Prevent path traversal
        rel = path[len("/static/"):]
        if ".." in rel or rel.startswith("/"):
            return (403, [("Content-Type", "text/plain")], b"Forbidden")
        fpath = static_dir / rel
        if fpath.exists() and fpath.is_file():
            ct = "text/plain"
            if fpath.suffix == ".js":
                ct = "application/javascript"
            elif fpath.suffix == ".css":
                ct = "text/css"
            elif fpath.suffix == ".html":
                ct = "text/html"
            return (200, [("Content-Type", ct)], fpath.read_bytes())
        return (404, [("Content-Type", "text/plain")], b"Not found")

    # ── Admin WebSocket handler ──────────────────────

    async def handle_admin_ws(self, ws, username: str):
        """Handle admin mutations via WebSocket messages."""
        logger.info("Admin WS connected: %s", username)
        try:
            async for raw in ws:
                msg_id = None
                try:
                    msg = json.loads(raw)
                    msg_id = msg.get("_id")
                    action = msg.get("action")
                    resp = await self._handle_admin_action(action, msg, username)
                    if msg_id is not None:
                        resp["_id"] = msg_id
                    await ws.send(json.dumps(resp))
                except json.JSONDecodeError:
                    r = {"error": "Invalid JSON"}
                    if msg_id is not None:
                        r["_id"] = msg_id
                    await ws.send(json.dumps(r))
                except Exception as e:
                    logger.error("Admin WS error: %s", e, exc_info=True)
                    r = {"error": str(e)}
                    if msg_id is not None:
                        r["_id"] = msg_id
                    await ws.send(json.dumps(r))
        except Exception:
            pass
        logger.info("Admin WS disconnected: %s", username)

    async def _handle_admin_action(self, action: str, msg: dict, username: str) -> dict:
        """Process an admin WebSocket action."""
        if action == "set_user":
            user = msg.get("user", "")
            machines = msg.get("machines", [])
            if not user:
                return {"error": "user is required"}
            if not isinstance(machines, list):
                return {"error": "machines must be a list"}
            for m in machines:
                if m not in self._pool.machines:
                    return {"error": f"Unknown machine: {m}"}

            async with self._lock:
                current = {u: sorted(names) for u, names in self._pool._user_machines.items()}
                if machines:
                    current[user] = machines
                else:
                    current.pop(user, None)
                self._save_assignments(current)
                self._pool.update_assignments(current)

            action_str = "assigned" if machines else "removed"
            logger.info("User %s %s by %s: %s", user, action_str, username, machines)
            return {"ok": True}

        elif action == "delete_user":
            user = msg.get("user", "")
            if not user:
                return {"error": "user is required"}

            async with self._lock:
                current = {u: sorted(names) for u, names in self._pool._user_machines.items()}
                if user not in current:
                    return {"error": f"User {user} has no assignment"}
                del current[user]
                self._save_assignments(current)
                self._pool.update_assignments(current)

            logger.info("Assignment removed for %s by %s", user, username)
            return {"ok": True}

        elif action == "put_assignments":
            data = msg.get("assignments", {})
            if not isinstance(data, dict):
                return {"error": "Expected object"}
            for user, machines in data.items():
                if not isinstance(machines, list):
                    return {"error": f"Value for {user} must be a list"}
                for m in machines:
                    if m not in self._pool.machines:
                        return {"error": f"Unknown machine: {m}"}

            async with self._lock:
                self._save_assignments(data)
                self._pool.update_assignments(data)

            logger.info("Assignments updated by %s: %s", username, data)
            return {"ok": True}

        else:
            return {"error": f"Unknown action: {action}"}

    # ── Persistence ─────────────────────────────────

    def _save_assignments(self, assignments: dict):
        """Save assignments to the writable assignments file."""
        path = self._assignments_path
        if path == self._config_path:
            config = {}
            if os.path.exists(path):
                with open(path) as f:
                    config = yaml.safe_load(f) or {}
            config["assignments"] = assignments
        else:
            config = {"assignments": assignments}

        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)
