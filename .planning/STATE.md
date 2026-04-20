---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: In progress (Phase 3)
last_updated: "2026-04-20T07:45:00.000Z"
progress:
  total_phases: 7
  completed_phases: 2
  total_plans: 36
  completed_plans: 30
  percent: 83
---

# Teraguchi — Project State

**Project:** Teraguchi — Open-source remote-workstation replacement for HP Anyware / PCoIP, targeting small VFX studios running Autodesk Flame, Nuke, Resolve, and Houdini.

**Maintainer:** Randy McEntee (solo, single committer; second-committer invite is a Phase 7 success criterion)

**Last updated:** 2026-04-18 (Phase 2 context gathered)

---

## Project Reference

**Core value:** A Flame artist can work an 8-hour client session remotely and not notice they're remote — input latency, color accuracy, and reliability all match sitting in front of the machine. If that holds, everything else matters. If it doesn't, the project has failed regardless of feature count.

**Current focus:** Phase 02 — input-color-fidelity

**Why now:** HP Anyware (PCoIP) end-of-life announced; new sales end May 7 2026, existing customers migrate by Oct 31 2029. Every small independent VFX studio (1-10 person shops) running Flame / Nuke / Resolve over PCoIP is now on a clock. NICE DCV is AWS-only and expensive; Parsec is SaaS-only / 8-bit / Windows-server; Sunshine has no pen tablet support. The gap (self-hosted, OSS, 10-bit, Wacom-first, macOS server) is uncontested.

**Mode:** Brownfield — a working vibe-coded prototype exists end-to-end on Mac→Rocky and Mac→Mac. v1 = production-hardening, not greenfield build.

---

## Current Position

Phase: 3
Plan: 03-01 complete; 03-02 + 03-03 next (Wave 1 parallelizable)
Phase 1: ✓ COMPLETE · 17 of 17 plans · Verification PASSED · 14/14 must-haves · 14/14 REQ-IDs
Phase 2: ✓ COMPLETE · 12 of 12 plans · Verification human_needed (5 DXS HW checkpoints) · 24/24 REQ-IDs
Phase 3: IN PROGRESS · 1 of 7 plans complete (03-01 Wave 0 TDD scaffolding)
| Field | Value |
|-------|-------|
| Milestone | v1.0 |
| Current phase | Phase 3 — Display + Multi-Monitor + Clipboard |
| Current plan | 03-01 complete; 03-02 + 03-03 next (Wave 1 parallelizable) |
| Status | 03-01 Wave 0 TDD scaffolding committed: wire-shape contract (D-02 / D-05 / D-13 / D-17 / ConnectionProfile 7 fields) + 19 RED test skeletons + 3 conftest fixtures. 3798 passed / 152 skipped / 0 failed on quick suite. Plans 02-06 have TDD targets ready. |
| Phases complete | 2 / 7 |
| Requirements mapped | 108 / 108 (100% coverage) |
| Resume file | `.planning/phases/03-display-multi-monitor-clipboard/03-02-PLAN.md` |

**Progress bar:** [██▱▱▱▱▱] 2 / 7 phases complete (Phase 3: 1/7 plans)

---

## Performance Metrics

| Metric | Target | Current |
|--------|--------|---------|
| Input-to-photon latency (LAN) | <20ms | Not measured (instrumentation lands Phase 1) |
| Frame rate (LAN) | 60fps | Working in prototype, not benchmarked |
| Frame rate (WAN Tailscale) | 30fps fallback | Working in prototype, not benchmarked |
| Color depth | 10-bit end-to-end | Working in prototype, NOT VERIFIED (banding-detector test pattern lands Phase 2) |
| Audio mouth-to-ear (LAN) | <80ms | Not implemented on macOS server; Phase 4 |
| Audio mouth-to-ear (WAN) | <150ms | Not implemented on macOS server; Phase 4 |
| 8-hour session crash-free | Required | Not measured (smoke harness lands Phase 1) |
| Test coverage | Pytest baseline on `common/`, auth, tokens, bookmarks | 0% (no tests committed; Phase 1) |
| CI gating | Mac runner + Rocky 9 container green on every PR | None (Phase 1) |

---

## Accumulated Context

### Decisions Locked (from PROJECT.md + REQUIREMENTS.md)

| Decision | Value | Source |
|----------|-------|--------|
| License | Apache 2.0 | REQUIREMENTS.md |
| Target frame rates | 60fps LAN / 30fps WAN | REQUIREMENTS.md |
| Linux server OS | Rocky Linux 9 only (RPM signed) | REQUIREMENTS.md |
| Audio codec | Opus, 48kHz, low-latency mode | REQUIREMENTS.md |
| Video codec | HEVC Main10 (10-bit) — NVENC on Rocky, VTCompressionSession on Mac | research/STACK.md + REQUIREMENTS.md |
| Apple Developer ID | Logik Academy Pro account; contractor handles Phase 6 signing setup | REQUIREMENTS.md |
| Transport (WAN) | QUIC (aioquic 1.3.0) primary | research/STACK.md |
| Transport (LAN) | TLS-WS + UDP dual-channel primary, with QUIC fallback | research/STACK.md |
| Broker | Paused for v1; direct client→server PAM is the v1 path | PROJECT.md |
| Connection discovery | Tailscale-first + manual hostname / saved bookmarks | REQUIREMENTS.md |
| Tech stack | Python 3.12+ floor; PySide6 6.10; PyAV 17.x against system FFmpeg 7.1+ | research/STACK.md |
| Client target | macOS only in v1 (Linux client runs but is not packaged/signed/supported) | PROJECT.md |
| Server targets | Rocky Linux 9 + macOS in v1; Windows is Phase 3 (post-v1) | PROJECT.md |
| Granularity | Standard (7 phases) | config.json |
| Mode | yolo (autonomous execution per config) | config.json |

### Open Questions Resolved (from research/SUMMARY.md)

All five open questions in research/SUMMARY.md were resolved by REQUIREMENTS.md before roadmap lock:

1. License → Apache 2.0
2. 60fps LAN / 30fps WAN → confirmed
3. Rocky 9 only (no Ubuntu / Debian for v1) → confirmed
4. Opus audio codec → confirmed
5. Apple Developer ID → in place via Logik Academy Pro

### Critical-Path Blockers (must clear in Phase 1)

1. `server/main.py` `send_queue(maxsize=30)` → `maxsize=4` + request-IDR-on-drop (5-line fix; without it, every later latency claim is unverifiable)
2. TLS certificate verification OFF everywhere (`ssl.CERT_NONE` in client/broker/QUIC/aiohttp probes) — SEC-01 in Phase 1; full security hardening lives in Phase 6
3. Zero pytest tests + zero CI — STAB-01, STAB-02, STAB-03 in Phase 1; refactoring `server/main.py` (1,191 lines) without tests is pure risk

### Spike Backlog (must resolve before their phases finalize)

| Spike | Phase | Estimate | Risk if Spike Fails |
|-------|-------|----------|---------------------|
| IOHIDUserDevice pen pressure on macOS | Phase 2 | 2 days | INPUT-08 re-scoped to "Mac-server pen pressure unsupported in v1" |
| Wacom hardware matrix session | Phase 2 | 1 day | INPUT-09/-10/-11/-12 verification deferred or device set narrowed |
| Mixed-DPI hardware session (Cintiq Pro 24 + Retina) | Phase 3 | 1 day | DISP-03/-05/-07 verification deferred to post-v1 |
| USB/IP target on macOS server | Phase 5 | 2 days | USB-02 re-scoped to "Mac server cannot receive USB/IP in v1; Linux server only" |

### Todos / Carry-Forward Notes

- Phase 1 plan-phase invocation should bake in: bug-fix tickets for `send_queue` (STAB-04), `ssl.CERT_NONE` removal (SEC-01), and the `server/main.py` decomposition (STAB-05) as the FIRST plans, before any other Phase 1 work, so subsequent observability work (OBS-01..03, OBS-05) measures a corrected pipeline rather than the broken one.
- Phase 7 second-committer invite (GOV-07) is a soft commitment with no hard pre-req — the decision is "before v1.1 work begins," not "before v1 ships." Don't block v1 release on it.

### Blockers

None at roadmap-lock time. All five PROJECT.md / SUMMARY.md open questions were resolved via REQUIREMENTS.md.

---

## Session Continuity

**Files written most recent session:**

- `.planning/phases/02-input-color-fidelity/02-CONTEXT.md` — 21 implementation decisions across 4 gray areas + latency gate (commit be29f20)
- `.planning/phases/02-input-color-fidelity/02-DISCUSSION-LOG.md` — full Q&A audit trail

**Phase 2 decisions locked (see 02-CONTEXT.md for full detail):**

- Color fidelity: 9-checkpoint byte-equality fixture; Metal/QRhi direct 10-bit texture on client; refuse-and-overlay HW capability gate; full VTCompressionSession PyObjC wrapper in Phase 2; 4:2:0 default, 4:2:2 opt-in; ICC out of scope
- macOS pen pressure: IOHIDUserDevice spike, 2-day success bar = pressure visible in Photoshop/Preview. Fail path = document as v1 limitation, Flame on Rocky stays production path. New `server/mac_pen_injector.py` module
- Hotkey correctness: auto-swap Cmd↔Ctrl with per-bookmark override; release-all-modifiers on focusOut + reconnect + periodic + F9 panic key; exhaustive Qt × modifier × platform keymap tests; US/UK/DE/JP layouts + IME passthrough; `xset r off` + client-driven repeats; Caps bit in every KeyEvent
- Wacom HW verification: one-shot gate + per-release runbook ritual (no self-hosted runners); hybrid protocol + automated counters + video; RMS < 1% on known-ramp for INPUT-12; proximity synthesis on focusIn/showEvent; TCC detect + guide in client
- Latency: keep Phase 1 synthetic p99<25ms gate; add one-time DXS real-HW measurement to docs/release.md

**Next action:** Run `/gsd-execute-phase 3` again (or the equivalent plan executor) to tackle 03-02 (client mode UX) and 03-03 (server crop pipeline) — both are Wave 1 plans with `depends_on: [01]` and can execute in parallel.

**Phase 3 — 03-01 Wave 0 TDD scaffolding completed (2026-04-20):**

- `a24ea35` feat(03-01): extend common/messages.py with Phase 3 wire shapes — 2 files / +352 lines
- `40cc866` test(03-01): add Phase 3 RED test skeletons + conftest fixtures — 21 files / +667 lines

**Wire-shape contract locked:**
- MsgType.SESSION_CONFIGURE + MsgType.CLIPBOARD_CHUNK constants
- MouseMoveMsg / MouseButtonMsg / MouseScrollMsg promoted to dataclasses (were raw dicts)
- server_x / server_y integer fields on all 5 input message dataclasses (D-05 physical-px)
- ClipboardChunkMsg dataclass (D-17 chunk envelope)
- ClientHelloMsg.capture_mode + picked_monitor_id + picked_monitor_name (D-02)
- ConnectionProfile: 7 Phase 3 fields with D-16 secure defaults (all clipboard directions ON)

**Test scaffolding ready:**
- 3 shared fixtures (mock_nsscreen, fake_mss_monitor_list, fixture_png)
- 19 RED skeleton test files + 2 extensions to existing files
- 51 new Wave 0 skeleton skips on the quick suite
- 3798 passed / 152 skipped / 0 failed on quick suite (no regressions)

**Known deviation:** `tests/server/test_clipboard.py` was listed as "existing" in the plan but did not exist in the repo (Phase 2 shipped clipboard code without unit tests). Auto-created as a new file with only the Wave 0 skeleton per Rule 3. Plan 06 fleshes out the real CLIP-01/D-16 tests.

---

*Initialized 2026-04-18 by gsd-roadmapper.*
*Phase 1 context gathered 2026-04-18 by gsd-discuss-phase.*
*Phase 2 context gathered 2026-04-18 by gsd-discuss-phase.*
*Phase 3 Plan 01 executed 2026-04-20 by gsd-execute-plan (sequential).*
