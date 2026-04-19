# Phase 2 — Deferred Items (Out-of-Scope Findings)

Issues discovered during plan execution that are out-of-scope for the
current plan and intentionally NOT fixed. Fold into a future plan or
phase-wide cleanup pass.

## From 02-02 (message-wiring)

**1. Pre-existing ruff errors in `common/messages.py`** — noted during
02-02 ruff verification. Not introduced by 02-02. Scope boundary per
executor deviation rules.

- `common/messages.py:29` I001 — import block un-sorted (needs `ruff --fix`)
- `common/messages.py:36` F401 — `typing.Optional` unused
- `common/messages.py:36` F401 — `typing.List` unused
- `common/messages.py:93` E501 — `decode_video_header` return line 112 chars (legacy Phase 1 code)

Fix in a follow-up `style(common)` commit — trivial, no behavioral risk.
Phase 1 mypy is clean; ruff was not previously run on the whole file
with the strict config.

## From 02-04 (capability-probe)

**2. Pre-existing mypy error in `common/logging.py:343`** — noted during
02-04 mypy verification on `server/capability_probe.py`. The StageTimer
`__exit__` is typed `-> bool` but always returns `False` — mypy flags
this as `[exit-return]` per PEP 479 (literal-False should be annotated
as `Literal[False]` or `None`). Not introduced by 02-04. Scope boundary;
`server/capability_probe.py` itself is clean.

Fix in a follow-up `fix(common/logging)` commit — change `-> bool` to
`-> None` (since the function only returns `False`) and remove the
literal return. Trivial, no behavioral risk.
