"""
PAM authentication for Teraguchi server.

Authenticates users against the Linux PAM stack, supporting:
- Local users (/etc/passwd + /etc/shadow)
- LDAP/FreeIPA users (via sssd)
- Any PAM-configured auth source

Requires: python-pam (pip install python-pam)
Must run as root for PAM access.
"""

import logging
import pwd
import grp
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import pam as pam_module
    PAM_AVAILABLE = True
except ImportError:
    PAM_AVAILABLE = False
    logger.warning("python-pam not installed — PAM auth unavailable")


class PAMAuthenticator:
    """Authenticate users via Linux PAM."""

    def __init__(self, service: str = "login"):
        self.service = service
        self._pam = pam_module.pam() if PAM_AVAILABLE else None

    @property
    def available(self) -> bool:
        return PAM_AVAILABLE and self._pam is not None

    def authenticate(self, username: str, password: str) -> bool:
        """Verify username/password against PAM."""
        if not self.available:
            logger.error("PAM not available")
            return False

        result = self._pam.authenticate(username, password, service=self.service)
        if result:
            logger.info("PAM auth success: %s", username)
        else:
            logger.warning("PAM auth failed: %s (%s)", username, self._pam.reason)
        return result

    @staticmethod
    def get_user_info(username: str) -> Optional[dict]:
        """Get uid, gid, home dir for a system user."""
        try:
            pw = pwd.getpwnam(username)
            groups = [g.gr_gid for g in grp.getgrall() if username in g.gr_mem]
            if pw.pw_gid not in groups:
                groups.insert(0, pw.pw_gid)
            return {
                "uid": pw.pw_uid,
                "gid": pw.pw_gid,
                "home": pw.pw_dir,
                "shell": pw.pw_shell,
                "groups": groups,
            }
        except KeyError:
            logger.error("System user not found: %s", username)
            return None
