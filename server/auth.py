"""
Server-side authentication.

Supports password-based auth with challenge-response to avoid
sending passwords in cleartext. Credentials are stored as salted
hashes in a JSON file.
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
    Manages user authentication for the Teragucci server.

    Stores users as salted SHA-256 hashes. Uses challenge-response
    during login to avoid sending passwords over the wire.
    """

    def __init__(self, users_file: str = DEFAULT_USERS_FILE, enabled: bool = True):
        self.enabled = enabled
        self._users_file = users_file
        self._users: dict = {}  # username -> {"password_hash": ..., "salt": ...}
        self._pending_challenges: dict = {}  # challenge -> username_expected (or None)
        self._load_users()

    def _load_users(self):
        """Load user database from JSON file."""
        if not self.enabled:
            return
        try:
            path = Path(self._users_file)
            if path.exists():
                with open(path) as f:
                    self._users = json.load(f)
                logger.info("Loaded %d users from %s", len(self._users), self._users_file)
            else:
                logger.info("No users file found at %s, auth disabled", self._users_file)
                self.enabled = False
        except Exception as e:
            logger.error("Failed to load users: %s", e)
            self.enabled = False

    def _save_users(self):
        """Save user database to JSON file."""
        path = Path(self._users_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self._users, f, indent=2)

    def add_user(self, username: str, password: str):
        """Add or update a user."""
        salt = secrets.token_hex(16)
        password_hash = hashlib.sha256(f"{password}:{salt}".encode()).hexdigest()
        self._users[username] = {
            "password_hash": password_hash,
            "salt": salt,
        }
        self._save_users()
        logger.info("User added/updated: %s", username)

    def remove_user(self, username: str):
        """Remove a user."""
        if username in self._users:
            del self._users[username]
            self._save_users()
            logger.info("User removed: %s", username)

    def create_challenge(self) -> str:
        """Create a new authentication challenge."""
        challenge = generate_challenge()
        self._pending_challenges[challenge] = None
        return challenge

    def verify(self, username: str, client_hash: str, challenge: str) -> bool:
        """
        Verify a client's authentication response.

        The client computes: SHA256(password + ":" + challenge)
        We need to verify this against our stored hash.

        Since we store SHA256(password + ":" + salt), we can't directly
        compare. Instead, the protocol works as:
        1. Server sends challenge
        2. Client computes: SHA256(SHA256(password + ":" + salt) + ":" + challenge)
           where salt is sent alongside the challenge
        3. Server verifies by computing the same thing from stored hash

        This way the raw password never goes over the wire.
        """
        if challenge not in self._pending_challenges:
            logger.warning("Invalid/expired challenge from %s", username)
            return False

        self._pending_challenges.pop(challenge, None)

        user = self._users.get(username)
        if not user:
            logger.warning("Unknown user: %s", username)
            return False

        # Compute expected response
        stored_hash = user["password_hash"]
        expected = hashlib.sha256(f"{stored_hash}:{challenge}".encode()).hexdigest()

        if client_hash == expected:
            logger.info("User authenticated: %s", username)
            return True
        else:
            logger.warning("Authentication failed for: %s", username)
            return False

    def get_user_salt(self, username: str) -> Optional[str]:
        """Get the salt for a user (sent to client for hash computation)."""
        user = self._users.get(username)
        return user["salt"] if user else None

    def list_users(self) -> list:
        return list(self._users.keys())
