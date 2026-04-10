"""
FreeIPA LDAP integration for group-based access control.

Queries FreeIPA LDAP for user group membership to authorize
access to Teraguchi workstations. Supports failover between
primary and replica FreeIPA servers.
"""

import logging
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)


class FreeIPAClient:
    """Query FreeIPA for user group membership via LDAP."""

    def __init__(self, servers: list[str], base_dn: str):
        """
        Args:
            servers: FreeIPA LDAP URIs, e.g. ["ldap://dxs-salt", "ldap://dxs-salty"]
            base_dn: LDAP base DN, e.g. "dc=the-dxs,dc=com"
        """
        self._servers = servers
        self._base_dn = base_dn
        self._ldap = None
        self._connected = False

        try:
            import ldap
            self._ldap_mod = ldap
        except ImportError:
            self._ldap_mod = None
            logger.warning("python-ldap not installed — using fallback group lookup")

    def _connect(self) -> bool:
        """Connect to FreeIPA LDAP with GSSAPI (Kerberos keytab)."""
        if self._ldap_mod is None:
            return False
        if self._connected and self._ldap:
            return True

        for uri in self._servers:
            try:
                conn = self._ldap_mod.initialize(uri)
                conn.set_option(self._ldap_mod.OPT_PROTOCOL_VERSION, 3)
                conn.set_option(self._ldap_mod.OPT_REFERRALS, 0)
                conn.set_option(self._ldap_mod.OPT_NETWORK_TIMEOUT, 5)
                # GSSAPI bind (uses host keytab)
                conn.sasl_interactive_bind_s("", self._ldap_mod.sasl.gssapi())
                self._ldap = conn
                self._connected = True
                logger.info("Connected to FreeIPA LDAP: %s", uri)
                return True
            except Exception as e:
                logger.warning("LDAP connect failed (%s): %s", uri, e)
                continue

        # Try simple anonymous bind as last resort (limited queries)
        for uri in self._servers:
            try:
                conn = self._ldap_mod.initialize(uri)
                conn.simple_bind_s("", "")
                self._ldap = conn
                self._connected = True
                logger.info("Connected to FreeIPA LDAP (anonymous): %s", uri)
                return True
            except Exception:
                continue

        logger.error("Cannot connect to any FreeIPA server")
        return False

    def get_user_groups(self, username: str) -> list[str]:
        """Get list of FreeIPA groups for a user."""
        # Try LDAP first
        if self._ldap_mod and self._connect():
            groups = self._get_groups_ldap(username)
            if groups:
                return groups
            # LDAP returned empty (anonymous bind can't read memberOf)
            logger.info("LDAP returned no groups for %s, trying id fallback", username)
        # Fallback: use id command (works on FreeIPA-joined hosts)
        return self._get_groups_fallback(username)

    def _get_groups_ldap(self, username: str) -> list[str]:
        """Query LDAP for user's group membership."""
        groups = []
        try:
            user_dn = f"uid={username},cn=users,cn=accounts,{self._base_dn}"
            result = self._ldap.search_s(
                user_dn, self._ldap_mod.SCOPE_BASE,
                "(objectClass=*)", ["memberOf"])
            if result:
                _, attrs = result[0]
                for member_of in attrs.get("memberOf", []):
                    # memberOf values are DNs like "cn=flame-users,cn=groups,cn=accounts,dc=..."
                    dn_str = member_of.decode("utf-8") if isinstance(member_of, bytes) else member_of
                    # Extract CN
                    for part in dn_str.split(","):
                        if part.strip().lower().startswith("cn="):
                            groups.append(part.strip()[3:])
                            break
        except Exception as e:
            logger.warning("LDAP group query failed for %s: %s", username, e)
            self._connected = False
            self._ldap = None
            # Fallback
            return self._get_groups_fallback(username)
        return groups

    def _get_groups_fallback(self, username: str) -> list[str]:
        """Get groups via 'id' command (works on FreeIPA-joined hosts)."""
        try:
            result = subprocess.run(
                ["id", "-Gn", username],
                capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                return result.stdout.strip().split()
        except Exception as e:
            logger.error("Group fallback failed for %s: %s", username, e)
        return []

    def is_member(self, username: str, group: str) -> bool:
        """Check if user is a member of a specific group."""
        return group in self.get_user_groups(username)

    def get_user_groups_cached(self, username: str, cache: dict,
                                ttl: float = 60.0) -> list[str]:
        """Get groups with a simple TTL cache."""
        import time
        now = time.time()
        entry = cache.get(username)
        if entry and (now - entry[0]) < ttl:
            return entry[1]
        groups = self.get_user_groups(username)
        cache[username] = (now, groups)
        return groups
