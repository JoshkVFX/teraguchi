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

## From 02-10 (mac-pen-injector + PenFSM)

**3. Pre-existing ruff errors in `client/viewer.py`** — noted during
02-10 ruff verification on the D-19 viewer changes. Not introduced by
02-10:

- `client/viewer.py:451-452` UP045 — `Optional[QImage]` / `Optional[QPixmap]` should be `X | None`
- `client/viewer.py:659` F841 — local `rh` assigned but never used
- ~9 additional UP045 / I001 instances in the same file

Fix in a follow-up `style(client/viewer)` commit — `ruff --fix` handles
all of them. Phase 1 set the precedent (UP045 / F841 are not in the
strict-fail set). Trivial, no behavioral risk.

**4. Pre-existing test collection error in
`tests/client/test_health_display.py`** — top-level `from PySide6.QtCore
import ...` lacks a `pytest.importorskip("PySide6")` guard. Fails
collection on hosts without PySide6 installed (the executor sandbox).
Not introduced by 02-10; the file was added in an earlier wave.

Fix in a follow-up `test(client/test_health_display)` commit — add the
skip guard at top of module, mirroring the pattern in
`test_viewer_modifier_triggers.py`. Trivial.

**5. Pre-existing PAM auth test failures (`tests/server/test_pam_auth.py`)**
— 1 fail + 3 errors with `AttributeError` on the python-pam mock. Not
introduced by 02-10; reproducible at HEAD with 02-10 changes stashed.

Fix in a follow-up `test(server/test_pam_auth)` commit — likely a
python-pam version drift. Out of scope for Phase 2 (Phase 1 territory).

**6. Pre-existing F401 in `server/mac_input_injector.py`** — Phase 1
era code; 5 unused Quartz imports flagged by ruff. Not introduced by
02-10's docstring + WARNING-log update.

Fix in a follow-up `style(server/mac_input_injector)` commit.
