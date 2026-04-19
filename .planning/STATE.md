---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: unknown
last_updated: "2026-04-19T05:26:16.890Z"
progress:
  total_phases: 7
  completed_phases: 1
  total_plans: 17
  completed_plans: 17
  percent: 100
---

# Teraguchi — Project State

**Project:** Teraguchi — Open-source remote-workstation replacement for HP Anyware / PCoIP, targeting small VFX studios running Autodesk Flame, Nuke, Resolve, and Houdini.

**Maintainer:** Randy McEntee (solo, single committer; second-committer invite is a Phase 7 success criterion)

**Last updated:** 2026-04-18 (Phase 2 context gathered)

---

## Project Reference

**Core value:** A Flame artist can work an 8-hour client session remotely and not notice they're remote — input latency, color accuracy, and reliability all match sitting in front of the machine. If that holds, everything else matters. If it doesn't, the project has failed regardless of feature count.

**Current focus:** Phase 2 — input-color-fidelity (context locked, ready for planning)

**Why now:** HP Anyware (PCoIP) end-of-life announced; new sales end May 7 2026, existing customers migrate by Oct 31 2029. Every small independent VFX studio (1-10 person shops) running Flame / Nuke / Resolve over PCoIP is now on a clock. NICE DCV is AWS-only and expensive; Parsec is SaaS-only / 8-bit / Windows-server; Sunshine has no pen tablet support. The gap (self-hosted, OSS, 10-bit, Wacom-first, macOS server) is uncontested.

**Mode:** Brownfield — a working vibe-coded prototype exists end-to-end on Mac→Rocky and Mac→Mac. v1 = production-hardening, not greenfield build.

---

## Current Position

Phase: 2 (input-color-fidelity) — CONTEXT GATHERED, ready for planning
Phase 1: ✓ COMPLETE · 17 of 17 plans · Verification PASSED · 14/14 must-haves · 14/14 REQ-IDs
| Field | Value |
|-------|-------|
| Milestone | v1.0 |
| Current phase | Phase 2 — Input + Color Fidelity (context locked) |
| Current plan | Run `/gsd-plan-phase 2` to decompose Phase 2 into plans |
| Status | Phase 2 CONTEXT.md committed (be29f20); 21 implementation decisions across 4 gray areas + latency-gate; 24 requirements (INPUT-01..12, VIDEO-01..12) scoped |
| Phases complete | 1 / 7 |
| Requirements mapped | 108 / 108 (100% coverage) |
| Resume file | `.planning/phases/02-input-color-fidelity/02-CONTEXT.md` |

**Progress bar:** [██▱▱▱▱▱] 1 / 7 phases complete

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

**Next action:** `/gsd-plan-phase 2` to decompose Phase 2 into executable plans.

---

*Initialized 2026-04-18 by gsd-roadmapper.*
*Phase 1 context gathered 2026-04-18 by gsd-discuss-phase.*
*Phase 2 context gathered 2026-04-18 by gsd-discuss-phase.*
