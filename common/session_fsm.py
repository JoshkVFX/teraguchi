"""Session FSMs (STAB-06 / D-13).

Declarative state + event model for both ends of a Teraguchi session.
One source of truth for state-string serialization, consumed by both
ends and serialized into ``HealthPing.client_state`` / ``HealthPong.server_state``
per Plan 01-08.

Library: ``python-statemachine >= 2.6`` (D-13 locked, pinned in
``requirements-server.txt`` and ``requirements-client.txt``).

Pitfall 1 (RESEARCH §Pitfall 1, lines 509-513): ``python-statemachine``'s
transition machinery supports both sync and async callbacks, but mixing
them silently misbehaves. Rule for callers: when any ``on_<event>`` /
``on_enter_<state>`` / ``on_exit_<state>`` callback is ``async def``,
every ``fsm.send(event)`` call MUST be ``await``ed. This module declares
no callbacks; Plans 01-11 (server health loop) and 01-15
(``ConnectionSupervisor`` on the client) attach side-effects in their
own modules via ``@ClientFSM.on_enter_streaming`` etc. — each side owns
its own I/O.

States and transitions frozen per:
  * RESEARCH §"FSM state set — client (final)" (lines 896-911) — 8 states
  * RESEARCH §"FSM state set — server (final)" (lines 913-927) — 7 states
  * RESEARCH §"Disagreement detection (STAB-06)" (line 929) — 9 pairs

Any state addition, state rename, or transition change is a
protocol-level change — gate it behind a ``ProtocolVersionMismatch``
check AND bump the wire contract.

Serialization contract:
  * ``fsm.current_state.id`` returns a short string matching exactly one
    of the entries in :data:`CLIENT_STATES` / :data:`SERVER_STATES`.
  * That string is dropped verbatim into the extended ``HealthPing`` /
    ``HealthPong`` fields (added by Plan 01-08).

This module imports nothing from ``server/`` or ``client/`` — it is pure
shared-contract code and lives in ``common/`` on purpose.
"""
from __future__ import annotations

from statemachine import State, StateMachine

# ── State name tuples (wire contract — do not reorder or rename) ─────
# Order is chosen to match the natural session lifecycle so a diff
# against the RESEARCH table is obvious.

CLIENT_STATES: tuple[str, ...] = (
    "disconnected",
    "handshaking",
    "authenticating",
    "capability_exchange",
    "streaming",
    "degraded",
    "reconnecting",
    "closed",
)

SERVER_STATES: tuple[str, ...] = (
    "bootstrapping",
    "authenticating",
    "capability_exchange",
    "streaming",
    "reconfiguring",
    "draining",
    "closed",
)


# ── Allowed (client_state, server_state) pairs for disagreement checks ─
# Per RESEARCH §"Disagreement detection (STAB-06)" (line 929) cross-
# referenced with PATTERNS §"common/session_fsm.py" (lines 398-408).
#
# A health exchange that produces a pair NOT in this set emits
# ``fsm.state_disagreement`` at ERROR level once Plan 01-11 wires the
# server health loop and Plan 01-17 wires the observability ratchet.
ALLOWED_PAIRS: frozenset[tuple[str, str]] = frozenset({
    ("handshaking",         "bootstrapping"),
    ("authenticating",      "authenticating"),
    ("capability_exchange", "capability_exchange"),
    ("streaming",           "streaming"),
    ("streaming",           "reconfiguring"),
    ("degraded",            "streaming"),
    ("reconnecting",        "draining"),
    ("reconnecting",        "closed"),
    ("closed",              "closed"),
})


def is_state_pair_allowed(client_state: str, server_state: str) -> bool:
    """Return ``True`` iff the observed pair is in :data:`ALLOWED_PAIRS`.

    Called on every ``HealthPing`` / ``HealthPong`` exchange by Plan
    01-11's server health loop. A ``False`` return triggers a
    ``fsm.state_disagreement`` structlog event at ERROR level (wired by
    Plan 01-17's observability ratchet).

    Unknown states — any string not in :data:`CLIENT_STATES` or
    :data:`SERVER_STATES` — always return ``False``. This keeps a
    malicious or out-of-version peer from smuggling a novel state string
    through the disagreement check.
    """
    if client_state not in CLIENT_STATES or server_state not in SERVER_STATES:
        return False
    return (client_state, server_state) in ALLOWED_PAIRS


# ── Client-side FSM ──────────────────────────────────────────────────
class ClientFSM(StateMachine):
    """Client session state. Drives ``ConnectionSupervisor`` (Plan 01-15).

    State set + transitions locked by RESEARCH §"FSM state set — client
    (final)". ``fsm.current_state.id`` returns the short string that
    serializes to the wire.
    """

    # States ---------------------------------------------------------
    disconnected = State(initial=True)
    handshaking = State()
    authenticating = State()
    capability_exchange = State()
    streaming = State()
    degraded = State()
    reconnecting = State()
    closed = State(final=True)

    # Transitions — locked by RESEARCH §"FSM state set — client (final)"
    connect_requested = (
        disconnected.to(handshaking)
        | reconnecting.to(handshaking)
    )
    tls_ok = handshaking.to(authenticating)
    tls_failed = handshaking.to(reconnecting)
    auth_ok = authenticating.to(capability_exchange)
    auth_failed = authenticating.to(disconnected)
    auth_timeout = authenticating.to(reconnecting)
    hello_received = capability_exchange.to(streaming)
    proto_mismatch = capability_exchange.to(disconnected)
    health_degraded = streaming.to(degraded)
    health_restored = degraded.to(streaming)
    transport_lost = (
        streaming.to(reconnecting)
        | degraded.to(reconnecting)
        | handshaking.to(reconnecting)
        | authenticating.to(reconnecting)
        | capability_exchange.to(reconnecting)
    )
    max_retries = reconnecting.to(closed)
    user_quit = (
        disconnected.to(closed)
        | handshaking.to(closed)
        | authenticating.to(closed)
        | capability_exchange.to(closed)
        | streaming.to(closed)
        | degraded.to(closed)
        | reconnecting.to(closed)
    )


# ── Server-side per-ClientSession FSM ────────────────────────────────
class ServerFSM(StateMachine):
    """Server session state (per ``ClientSession``).

    Drives per-connection reconfigure + drain flow. State set +
    transitions locked by RESEARCH §"FSM state set — server (final)".
    """

    # States ---------------------------------------------------------
    bootstrapping = State(initial=True)
    authenticating = State()
    capability_exchange = State()
    streaming = State()
    reconfiguring = State()
    draining = State()
    closed = State(final=True)

    # Transitions — locked by RESEARCH §"FSM state set — server (final)"
    tls_ok = bootstrapping.to(authenticating)
    ws_closed_early = bootstrapping.to(closed)
    auth_ok = authenticating.to(capability_exchange)
    auth_failed = authenticating.to(closed)
    auth_timeout = authenticating.to(closed)
    client_hello = capability_exchange.to(streaming)
    client_hello_abort = capability_exchange.to(draining)
    reconfigure_requested = streaming.to(reconfiguring)
    encoder_crashed = streaming.to(reconfiguring)
    ws_closed = (
        streaming.to(draining)
        | capability_exchange.to(draining)
        | reconfiguring.to(draining)
    )
    reconfigure_done = reconfiguring.to(streaming)
    encoder_dead = reconfiguring.to(closed)
    drain_timeout = draining.to(closed)
    last_frame_sent = draining.to(closed)


__all__ = [
    "CLIENT_STATES",
    "SERVER_STATES",
    "ALLOWED_PAIRS",
    "is_state_pair_allowed",
    "ClientFSM",
    "ServerFSM",
]
