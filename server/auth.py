"""
Server-side authentication.

Supports multiple auth backends:
- PAM:   Authenticates against Linux system users (local, LDAP, FreeIPA)
         This is the PCoIP-like mode — users log in with their Linux credentials.
- Local: Custom JSON user database with challenge-response (legacy)
- None:  Authentication disabled

PAM mode requires the server to run as root.
"""

import hashlib
import json
import logging
import os
import secrets
from pathlib import Path
from typing import Optional

from common.messages import generate_challenge, hash_password

logger = logging.getLogger(__name__)

DEFAULT_USERS_FILE = os.path.expanduser("~/.config/teragucci/users.json")


class Authenticator:
    """
    Unified authenticator supporting PAM and local auth modes.

    Usage:
        # PAM mode (PCoIP-like, uses Linux credentials)
        auth = Authenticator(mode="pam")
        auth.verify_pam("randy", "password123")

        # Local mode (legacy JSON user database)
        auth = Authenticator(mode="local")
        challenge = auth.create_challenge()
        auth.verify("user", client_hash, challenge)

        # Disabled
        auth = Authenticator(mode="none")
    """

    def __init__(self, mode: str = "pam", users_file: str = DEFAULT_USERS_FILE,
                 enabled: bool = True):
        """
        Args:
            mode: "pam", "local", or "none"
            users_file: Path to JSON users file (local mode only)
            enabled: Master enable/disable (overrides mode)
        """
        if not enabled:
            mode = "none"

        self.mode = mode
        self.enabled = mode != "none"
        self._users_file = users_file
        self._users: dict = {}
        self._pending_challenges: dict = {}

        # PAM backend
        self._pam = None
        if mode == "pam":
            try:
                from server.pam_auth import PAMAuthenticator
                self._pam = PAMAuthenticator()
                if not self._pam.available:
                    logger.error("PAM requested but python-pam not installed")
                    raise RuntimeError("PAM unavailable")
                logger.info("Auth mode: PAM (system users)")
            except ImportError:
                logger.error("PAM requested but server.pam_auth not found")
                raise

        elif mode == "local":
            self._load_users()
            logger.info("Auth mode: local (JSON user database)")

        else:
            logger.info("Auth mode: disabled")

    # ── PAM authentication ───────────────────────────────────

    def verify_pam(self, username: str, password: str) -> bool:
        """Authenticate via PAM. Returns True on success."""
        if self.mode != "pam" or not self._pam:
            logger.error("verify_pam called but mode is %s", self.mode)
            return False
        return self._pam.authenticate(username, password)

    def get_user_info(self, username: str) -> Optional[dict]:
        """Get system user info (uid, gid, home). Works in any mode."""
        try:
            from server.pam_auth import PAMAuthenticator
            return PAMAuthenticator.get_user_info(username)
        except ImportError:
            import pwd
            try:
                pw = pwd.getpwnam(username)
                return {"uid": pw.pw_uid, "gid": pw.pw_gid, "home": pw.pw_dir}
            except KeyError:
                return None

    # ── Local (legacy) authentication ────────────────────────

    def _load_users(self):
        if self.mode != "local":
            return
        try:
            path = Path(self._users_file)
            if path.exists():
                with open(path) as f:
                    self._users = json.load(f)
                logger.info("Loaded %d users from %s", len(self._users), self._users_file)
            else:
                logger.info("No users file at %s, disabling local auth", self._users_file)
                self.enabled = False
        except Exception as e:
            logger.error("Failed to load users: %s", e)
            self.enabled = False

    def _save_users(self):
        path = Path(self._users_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self._users, f, indent=2)

    def add_user(self, username: str, password: str):
        """Add or update a local user."""
        salt = secrets.token_hex(16)
        password_hash = hashlib.sha256(f"{password}:{salt}".encode()).hexdigest()
        self._users[username] = {"password_hash": password_hash, "salt": salt}
        self._save_users()
        logger.info("Local user added/updated: %s", username)

    def remove_user(self, username: str):
        if username in self._users:
            del self._users[username]
            self._save_users()
            logger.info("Local user removed: %s", username)

    def create_challenge(self) -> str:
        challenge = generate_challenge()
        self._pending_challenges[challenge] = None
        return challenge

    def verify(self, username: str, client_hash: str, challenge: str) -> bool:
        """Verify challenge-response auth (local mode)."""
        if challenge not in self._pending_challenges:
            logger.warning("Invalid/expired challenge from %s", username)
            return False
        self._pending_challenges.pop(challenge, None)

        user = self._users.get(username)
        if not user:
            logger.warning("Unknown local user: %s", username)
            return False

        stored_hash = user["password_hash"]
        expected = hashlib.sha256(f"{stored_hash}:{challenge}".encode()).hexdigest()

        if client_hash == expected:
            logger.info("Local auth success: %s", username)
            return True
        logger.warning("Local auth failed: %s", username)
        return False

    def get_user_salt(self, username: str) -> Optional[str]:
        user = self._users.get(username)
        return user["salt"] if user else None

    def list_users(self) -> list:
        return list(self._users.keys())
