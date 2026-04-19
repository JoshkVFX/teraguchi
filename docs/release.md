# Teraguchi Release Notes / Runbook

This document seeds the Phase 6 release runbook. It records outcomes
from the Phase 2 input-color-fidelity work that have user-visible v1
implications, and is the source of truth for "what's a v1 known
limitation vs. what's a bug."

## Phase 2 IOHIDUserDevice spike outcome

- **Outcome: FAIL** (recorded 2026-04-19; INPUT-08 re-scoped per D-07)
- **Reason:** The D-07/D-08 spike per `02-CONTEXT.md` requires unsigned
  Python (`pyobjc-framework-IOKit`) to register a virtual Wacom HID
  tablet via `IOHIDUserDeviceCreate` and verify across a complete pen
  stroke that **Photoshop / Preview / a simple NSView app reads
  `NSEvent.pressure > 0`**. The PASS bar cannot be met within the
  Phase 2 plan-execution environment because:
  1. `pyobjc-framework-IOKit` is not present in the executor's Python
     environment, and installing it system-wide requires elevation
     outside the executor's sandbox.
  2. The D-08 success criterion is a manual interactive verification
     against Photoshop / Preview / an NSView test app — which requires
     a logged-in macOS GUI session, the apps installed and granted
     TCC permissions, and a real Wacom Pro stylus at the workstation.
     None of those is available to the autonomous Phase 2 executor.
  3. Per `CLAUDE.md` "Zero tolerance for Wacom pressure glitches" —
     fabricating a PASS without the manual verification would ship a
     half-working injector. That is the worst possible v1 outcome:
     Flame artists trust pressure, and a silent quantization or
     proximity bug would burn that trust on the first session.

  Per `02-CONTEXT.md` D-07 "document + ship" failure-path framing, the
  honest call is to keep the existing mouse-click fallback with a
  one-time WARNING, document the limitation, and direct Flame artists
  to the Rocky Linux server (the production path per `PROJECT.md`).

- **INPUT-08 scope:** Re-scoped to "Mac-server pen pressure is a v1
  known limitation. `mac_input_injector.pen_event` retains the
  Phase 1 mouse-click downgrade path with a one-time WARNING log on
  the first non-zero pressure event."

- **Workaround:** Run Autodesk Flame on the **Rocky Linux server**
  (the production path documented in `PROJECT.md` "Server (Rocky
  Linux) — production-grade"). Mac server is dev / testing /
  light-editing in v1; Flame-on-Mac-server with full pressure is
  v1.1+ work.

- **Roadmap:** A signed **HIDDriverKit** system extension is the v1.1
  investigation. Apple's `com.apple.developer.driverkit.family.hid.virtual.device`
  entitlement requires per-app approval (weeks of bureaucracy through
  the Logik Academy Pro Developer ID). Even with the entitlement, the
  system-extension distribution model breaks the "download the .app
  and run it" UX `PROJECT.md` commits to. Re-evaluate when a real
  studio commits to Flame-on-Mac-server as a load-bearing workflow.

- **Next-spike trigger:** Re-run the D-07/D-08 spike (2 days) on a
  development workstation with `pyobjc-framework-IOKit>=11.0`, real
  Wacom hardware, Photoshop / Preview installed, and the operator
  available to draw a stroke and verify pressure. The plan retains
  the PASS-branch implementation sketch in `02-10-PLAN.md` Task 1
  for the next attempt — no plan rework needed.

### Health-overlay badge

Client health overlay reuses the 02-04 `render_color_badge` pattern.
The pen-capability badge string for v1 macOS-server bookmarks is:

```
10-bit: confirmed / pen: LIMITATION (mouse-only, see release notes)
```

For Linux-server bookmarks the pen segment is omitted (`uinput`
delivers full pressure / tilt; no caveat).

## Phase 2 PenFSM + client proximity re-synth (D-19)

Lands on both spike branches per `02-10-PLAN.md` Task 3:

- `common/session_fsm.py::PenFSM` with `out_of_proximity` /
  `in_proximity` states; `enter_proximity` and `leave_proximity`
  transitions are idempotent (a duplicate enter from `in_proximity`
  is a no-op, matching the wire-message contract on the PenProximityMsg
  receiver in `server/client_session.py`).
- `client/viewer.py::RemoteViewer.focusInEvent` and `showEvent`
  synthesize a `PenProximityMsg(in_proximity=True)` so the server FSM
  converges after Cmd-Tab cycles, screen-lock, and minimize/restore
  (D-19 fixes the canonical "proximity event eaten by lockscreen"
  PITFALLS #3 bug class).

## Notes for Phase 6 packaging

- No new TCC prompt is added by Phase 2's INPUT-08 work on the FAIL
  branch — the Mac server retains its existing Accessibility +
  Input Monitoring requirements from Phase 1.
- No `IOHIDUserDevice` lifecycle is introduced on the FAIL branch, so
  PITFALLS #4 (orphaned virtual-HID devices in `ioreg -l -c
  IOHIDUserDevice`) is not reachable in v1. If the v1.1 PASS-branch
  productionization lands, `atexit.register()` + SIGTERM/SIGINT
  handlers are mandatory in the new module per the Plan 02-10 Task 1
  acceptance criteria.

---

*Last updated: 2026-04-19 (Phase 2, Plan 02-10 — D-07 spike FAIL recorded; INPUT-08 re-scoped to v1 known-limitation).*
