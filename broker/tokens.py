"""
Broker token generation and verification.

Uses HMAC-SHA256 signed tokens for single-use authentication
between the broker and Teraguchi servers. Avoids sending user
passwords to the server after broker authentication.
"""

import hashlib
import hmac
import json
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

TOKEN_TTL = 60  # seconds


def generate_token(username: str, machine: str, secret: str,
                   ttl: int = TOKEN_TTL) -> str:
    """
    Generate a broker auth token.

    Format: base64-free JSON with HMAC signature.
    Returns: "username:machine:issued_at:expires_at:signature"
    """
    issued = int(time.time())
    expires = issued + ttl
    payload = f"{username}:{machine}:{issued}:{expires}"
    sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}:{sig}"


def verify_token(token: str, secret: str) -> Optional[str]:
    """
    Verify a broker auth token.

    Returns username if valid, None if invalid/expired.
    """
    parts = token.split(":")
    if len(parts) != 5:
        logger.warning("Token: wrong number of parts (%d)", len(parts))
        return None

    username, machine, issued_str, expires_str, sig = parts

    try:
        expires = int(expires_str)
    except ValueError:
        return None

    if time.time() > expires:
        logger.warning("Token expired for %s (expired %d)", username, expires)
        return None

    payload = f"{username}:{machine}:{issued_str}:{expires_str}"
    expected_sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(sig, expected_sig):
        logger.warning("Token signature mismatch for %s", username)
        return None

    return username
