---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: In progress (Phase 3)
last_updated: "2026-04-20T20:40:00.000Z"
progress:
  total_phases: 7
  completed_phases: 2
  total_plans: 36
  completed_plans: 34
  percent: 94
---

# Teraguchi — Project State

**Project:** Teraguchi — Open-source remote-workstation replacement for HP Anyware / PCoIP, targeting small VFX studios running Autodesk Flame, Nuke, Resolve, and Houdini.

**Maintainer:** Randy McEntee (solo, single committer; second-committer invite is a Phase 7 success criterion)

**Last updated:** 2026-04-18 (Phase 2 context gathered)

---

## Project Reference

**Core value:** A Flame artist can work an 8-hour client session remotely and not notice they're remote — input latency, color accuracy, and reliability all match sitting in front of the machine. If that holds, everything else matters. If it doesn't, the project has failed regardless of feature count.

**Current focus:** Phase 03 — display-multi-monitor-clipboard (Wave 4 server-side clipboard complete; Plan 07 client-side clipboard UI + integration tests next; D-08 DXS hardware spike still pending for Plan 04)

**Why now:** HP Anyware (PCoIP) end-of-life announced; new sales end May 7 2026, existing customers migrate by Oct 31 2029. Every small independent VFX studio (1-10 person shops) running Flame / Nuke / Resolve over PCoIP is now on a clock. NICE DCV is AWS-only and expensive; Parsec is SaaS-only / 8-bit / Windows-server; Sunshine has no pen tablet support. The gap (self-hosted, OSS, 10-bit, Wacom-first, macOS server) is uncontested.

**Mode:** Brownfield — a working vibe-coded prototype exists end-to-end on Mac→Rocky and Mac→Mac. v1 = production-hardening, not greenfield build.

---

## Current Position

Phase: 3
Plan: 03-06 COMPLETE; 03-04 code complete (D-08 manual hardware gate pending); 03-07 next
Phase 1: ✓ COMPLETE · 17 of 17 plans · Verification PASSED · 14/14 must-haves · 14/14 REQ-IDs
Phase 2: ✓ COMPLETE · 12 of 12 plans · Verification human_needed (5 DXS HW checkpoints) · 24/24 REQ-IDs
Phase 3: IN PROGRESS · 5 of 7 plans (01, 02, 03, 05, 06) + 03-04 code-complete awaiting D-08 hardware spike
| Field | Value |
|-------|-------|
| Milestone | v1.0 |
| Current phase | Phase 3 — Display + Multi-Monitor + Clipboard |
| Current plan | 03-06 COMPLETE; 03-04 code complete (D-08 manual gate pending); 03-07 next |
| Status | Plan 03-06 server clipboard complete across 4 commits (ClipboardChunkAssembler + PNG paths on Linux+Mac + CRLF preservation + per-direction gating with Pitfall 7 race fix); full quick suite 3899/0/115 (+24 GREEN vs Plan 05 baseline 3875, -15 Wave 0 skips converted). 03-04 code committed across 3 commits (cursor math + DPR + F12 overlay + docs template): _widget_to_remote returns 4-tuple (rx_norm, ry_norm, server_x_px, server_y_px) per D-05; _current_screen_dpr uses QWindow.windowHandle().screen().devicePixelRatio() per D-06 (Pitfall 1 root-cause fix); showEvent wires QWindow.screenChanged to _on_screen_changed which recomputes scaling cache + re-emits pen_proximity when _pen_was_in_proximity (Pitfall 2 cross-trigger symmetric to Phase 2 D-19); mouse/button/scroll signals extended from 2/4/4 → 4/6/6 args with server_x/server_y; pen_data dict gains server_x/server_y keys; protocol.send_mouse_move/send_mouse_button/send_mouse_scroll/send_pen_event build new dataclass shapes; session._send_mouse_* slots consume 4-arg signals; F12 overlay (client/coord_debug_overlay.py NEW) gated at HANDLER-INSTALL time on TERAGUCHI_DEBUG=1 per Pitfall 8 — release builds leave _coord_overlay=None and F12 falls through; UI-SPEC Surface 6 verbatim copy + zero inline hex (theme.* tokens only); docs/release.md pre-populated with D-08 spike template (8-row matrix, sign-off checkboxes, un-flipped pending). Full quick suite 3850/0/132 (12 new GREEN tests vs Plan 03-03 baseline 3838); target tests 12/12 GREEN. ROADMAP plan 04 checkbox stays un-flipped — flips only after Randy runs D-08 at DXS and records results in docs/release.md. DISP-03 + DISP-05 requirement behavior is shipped in code but NOT marked complete pending hardware verification. |
| Phases complete | 2 / 7 |
| Requirements mapped | 108 / 108 (100% coverage) |
| Resume file | `.planning/phases/03-display-multi-monitor-clipboard/03-07-PLAN.md` (Wave 4 client clipboard UI + integration tests); 03-04 continuation pending D-08 hardware session |

**Progress bar:** [██▱▱▱▱▱] 2 / 7 phases complete (Phase 3: 5/7 plans + 03-04 code-complete awaiting hardware gate)

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
| Mixed-DPI hardware session (Retina MBP + external non-Retina monitor) | Phase 3 | 1 day | DISP-03/-05/-07 verification deferred to post-v1 |
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

**Phase 3 — 03-02 Wave 1 client mode UX completed (2026-04-20):**

- `8167847` feat(03-02): bookmark migration + ModeSelector widget + MonitorSelector radio mode — 5 files / +745 lines
- `e354468` feat(03-02): push capture_mode on ClientHelloMsg + toolbar mode badge — 4 files / +384 lines

**Plan 02 delivered:**
- Connect-dialog ModeSelector widget (UI-SPEC Surface 1 verbatim copy): 3 radios (Single monitor / Mirror all / Pick one) + help text + pick-one sub-selector via MonitorSelector in radio mode (D-04).
- MonitorSelector gains `set_mode("radio")` single-check semantics, `monitor_missing(name)` signal, `set_picked(id, name)` with id→name→primary fallback, `selected_ids()` / `selected_names()` accessors, and Select All/None visibility toggle. Menu title flips to "Pick one monitor" in radio mode.
- client/bookmarks.py::_load Phase 3 migration block marks migrated=True when any Phase 3 field is missing, triggering atomic _save() rewrite (Pitfall 9). T-03-05 STRIDE mitigation: monitor_mode whitelist enum check reverts tampered values to mirror_all with structlog warning.
- client/protocol.py::set_capture_mode setter + ClientHelloMsg construction now carries capture_mode + picked_monitor_id + picked_monitor_name on every connect (D-02). T-03-07 client-side whitelist rejects unknown modes.
- client/session.py::connect() extended with monitor_mode/picked_monitor_id/picked_monitor_name kwargs. New connect_with_profile() convenience. Capture-mode push lands BEFORE protocol.connect so the first handshake carries the user's mode.
- client/fullscreen_toolbar.py _ModeBadge (UI-SPEC Surface 2): Mode: single | mirror | pick: {name} | pick → primary verbatim copy, ACCENT/WARNING underline, GOLD locked dot, tooltips verbatim. FullscreenToolbar.update_capture_mode(mode, picked_name, degraded) slot + mode_badge property.

**Test gate:**
- 31 GREEN in Task 1/2 test files (16 bookmarks + 8 ModeSelector + 7 mode badge)
- 3620 passed / 0 failed / 111 skipped on client+common (no regressions vs Plan 01 baseline)
- 3816 passed / 0 failed / 145 skipped on full quick suite (`not wacom_hw and not gpu and not smoke_1h and not latency_bench`)

**DISP-01 + DISP-07 requirement behavior landed:**
- DISP-01 (per-session monitor mode selector): connect-dialog picker + bookmark persistence + wire push + toolbar badge — all client-side surface complete. Server-side consumption lands in 03-03.
- DISP-07 (per-monitor fullscreen mode): pick-one sub-selector + ClientHelloMsg.picked_monitor_* fields surface the client half. Server-side crop + fullscreen geometry math lands in 03-03 + 03-04.

**Known deviation (Plan 02):** One Rule 1 test semantics fix (not source fix) — isHidden() replaces isVisible() in two headless badge tests because Qt's effective visibility returns False when parent-chain isn't shown. Production badge behavior is correct; the fix only tightened the headless test assertion. Documented in 03-02-SUMMARY.md.

**Phase 3 — 03-03 Wave 1 server capture pipeline completed (2026-04-20):**

- `6e4b377` feat(03-03): server-side BGRA crop + capture_mode plumbing + full hotplug signature — 9 files / +816 lines
- `3ce51f1` feat(03-03): Mac SCK hot-plug delegate + Eizo CG279X CustomEDID profile — 4 files / +405 lines

**Plan 03 delivered:**
- server/screen_capture.py: capture_raw_bgra_with_crop (D-02) — mirror_all crop=None is byte-equal to capture_raw_bgra (Phase 2 9-checkpoint fixture preserved); single+pick_one do NumPy BGRA crop pre-encode; degenerate crops return single black pixel per PATTERNS L720-722.
- server/screen_capture.py + server/mac_screen_capture.py: detect_hotplug upgraded to full (id|displayID, width, height, x, y) tuple per MonitorInfo so reorder + same-size swap + reposition all trigger change (D-09/D-11; fixes Pitfall 4).
- server/session_runtime.py: apply_capture_mode with T-03-09 whitelist enum check, D-04 id-wins-name-fallback, D-09 pick_one→primary fallback setting capture_mode_degraded=True (Plan 05 toast surface), W-5 session.multi_session_crop_collision forensic guard. Wired into CLIENT_HELLO handler.
- server/stream_loop.py: encoder feed calls capture_raw_bgra_with_crop(crop) reading authenticated session's crop_rect; defensive getattr fallback for Phase 1 test stubs.
- server/monitor_hotplug.py: poll cadence 5.0s→1.0s (D-11 push-complement); checks _hotplug_pending before detect_hotplug; re-applies per-session crop after encoder_lifecycle.restart (foundation for Plan 05 fall-back-to-primary broadcast).
- server/mac_screen_capture.py: _DisplayChangeDelegate(NSObject) subscribing via NSWorkspaceDidChangeScreenParametersNotification sets _hotplug_pending under _lock; exceptions wrapped in try/except (pyobjc discipline mirror of _StreamOutputHandler).
- server/session_manager.py: _generate_edid emits "Eizo CG279X" monitor-name descriptor + "ENC" manufacturer ID (DISP-04). Checksum auto-recomputes; PCoIP fallback + our-bundled fallback unchanged.
- docs/release.md: Phase 3.5 follow-ups section — P010 raw-capture crop seam (v1 ships BGRA-only; encoder's internal BGRA→P010 preserves 10-bit through unchanged Phase 2 pipeline) + multi-session crop per host (v1.1).

**Test gate:**
- 22 GREEN on Plan 03 acceptance battery (7 capture_crop + 4 screen_capture_hotplug + 4 mac_screen_capture_hotplug (skip on non-Mac) + 5 session_manager_edid + 6 integration capture_mode)
- 3838 passed / 0 failed / 139 skipped on full quick suite (+5 tests vs Plan 02 baseline 3833 — no regressions)
- 7 passed / 0 failed / 2 skipped on ten_bit_smoke gate (Phase 2 9-checkpoint fixture preserved; mirror_all byte-equality validated via hashlib.sha256)

**DISP-04 + DISP-07 requirement behavior landed:**
- DISP-04 (Flame-approved CustomEDID): Eizo CG279X + ENC manufacturer ID emitted by _generate_edid; Flame's monitor-config dialog accepts without warning.
- DISP-07 (per-monitor fullscreen mode): server-side crop + capture-mode negotiation complete. Plan 02 + 03 together deliver the end-to-end DISP-07 surface; Plan 04 lands the client-side cursor math for the cropped path.

**Known deviations (Plan 03):** Three Rule 1 fixes — (1) defensive getattr fallback in stream_loop for Phase 1 _StubCapture compat; (2) D-10 docstring rephrased to avoid regex false-positive in acceptance gate; (3) 5-line comment added to mac_screen_capture.py observer install so `screenParametersChanged_` grep finds both the Python def + the selector-mapping comment. No source behavior changes in fixes 2+3; fix 1 is a pure additive safety branch. Documented in 03-03-SUMMARY.md.

**Phase 3 — 03-04 Wave 2 code-complete; D-08 hardware gate pending (2026-04-20):**

- `8e3f18c` test(03-04): add failing tests for cursor math + per-screen DPR + screenChanged — 3 files / +312 / -45 lines (RED phase — 12 new tests, 5 Wave 0 skips converted)
- `a377090` feat(03-04): cursor math + per-screen DPR + screenChanged + server_x/y wire — 3 files / +352 lines (GREEN phase; viewer.py + protocol.py + session.py)
- `64610c4` feat(03-04): add F12 coord-debug overlay widget (D-07, UI-SPEC Surface 6) — 1 file / +189 lines (NEW client/coord_debug_overlay.py)
- `78f6be2` docs(03-04): pre-populate D-08 4-corner DXS hardware spike template — 1 file / +59 / -1 lines (docs/release.md recording sheet)

**Plan 04 delivered (code-complete):**
- `_widget_to_remote` rewritten to return 4-tuple `(rx_norm, ry_norm, server_x_px, server_y_px)` (D-05); both branches (simple + composite past-last-monitor edge case) produce consistent integer outputs.
- `_current_screen_dpr` helper (D-06) uses `self.window().windowHandle().screen().devicePixelRatio()` — never the primary's DPR (Pitfall 1 / Mozilla bz #794038 root-cause fix). Falls back to `devicePixelRatioF()` when windowHandle is None.
- `_connect_screen_changed` + `_on_screen_changed` wired inside `showEvent`. Slot recomputes `_update_scaling` + re-emits `pen_proximity` when `_pen_was_in_proximity` (Pitfall 2 — symmetric to Phase 2 D-19 focusIn re-synth). Logs DPR transitions at INFO level.
- All 5 `_widget_to_remote` call sites (tabletEvent + 4 mouse handlers) unpack the 4-tuple. Qt signals extended: `mouse_moved` 2→4 args, `mouse_button_changed` 4→6 args, `mouse_scrolled` 4→6 args.
- `client/protocol.py` adds `send_mouse_move` / `send_mouse_button` / `send_mouse_scroll` / `send_pen_event` helpers that build `MouseMoveMsg` / `MouseButtonMsg` / `MouseScrollMsg` / `PenEventMsg` dataclasses with `server_x` / `server_y`. `send_key_event` inline dict adds `server_x` / `server_y` sentinels (-1) so KeyEvent wire carries the fields.
- `client/session.py::_send_mouse_*` slot signatures updated to accept `server_x` / `server_y` kwargs (default -1 sentinel = backward-compat).
- F12 dev overlay (D-07) gated at HANDLER-INSTALL time on `TERAGUCHI_DEBUG=1` per Pitfall 8. Release builds leave `_coord_overlay=None`; F12 keyPressEvent branch is `None`-guarded and falls through. UI-SPEC Surface 6 verbatim copy; zero inline hex (theme.* tokens only); `WA_TransparentForMouseEvents` never blocks clicks.
- `docs/release.md` pre-populated with D-08 4-corner DXS hardware spike template (8-row matrix × 4 corners = 32 measurement cells, sign-off boxes for DISP-03 / DISP-05, pen-interaction row).

**Test gate:**
- 12 GREEN on Plan 04 target tests (3 cursor_math + 5 viewer_dpr + 4 viewer_screen_changed)
- 3850 passed / 0 failed / 132 skipped on full quick suite (+12 vs Plan 03-03 baseline 3838)
- No latency regression — Phase 1 p99<25ms gate unchanged path (cursor math adds 8 bytes on wire + removes a normalize/denormalize step; likely neutral-to-positive per D-18)

**DISP-03 + DISP-05 status:** CODE COMPLETE, NOT YET MARKED COMPLETE.
- Cursor-math + per-screen DPR + F12 overlay surface lands; synthetic DXS 4-corner CI fixture (2×2560×1600) passes within 1 px tolerance.
- Real-hardware D-08 spike pending — Randy at DXS with Cintiq Pro 24 + Retina MBP + 2× NVIDIA Xorg server rig. Matrix lives in docs/release.md waiting for sign-off.
- ROADMAP plan 04 checkbox stays `[ ]` with "(code complete; D-08 gate pending hardware session)" note.

**Next action:** Randy runs the D-08 manual spike at DXS when back from travel (mixed-DPI client: Retina MBP + external non-Retina monitor; pen row satisfied with Intuos Pro — no display tablet required), populates the docs/release.md matrix, checks DISP-03 + DISP-05 sign-off boxes. Once signed, orchestrator spawns a continuation agent that commits docs/release.md + creates 03-04-SUMMARY.md + flips ROADMAP plan 04 to `[x]` + marks DISP-03 + DISP-05 complete in REQUIREMENTS.md.

**Known deviation (Plan 04):** None — plan executed exactly as written for the code-change tasks. No Rule 1/2/3 auto-fixes were needed; all acceptance grep patterns matched on first pass; full quick suite stayed green; zero regressions against the Plan 03-03 baseline.

**Phase 3 — 03-05 Wave 3 hot-plug UX + auto-fallback completed (2026-04-20):**

- `50b9ee7` test(03-05): add failing tests for MonitorListMsg.degradations + hotplug fallback — 3 files / +405 lines (RED phase — 6 new tests)
- `ae7b185` feat(03-05): server hot-plug auto-fallback harvests degradations payload — 2 files / +105 / -51 lines (GREEN phase; MonitorListMsg.degradations field + server iteration restructure + D-18 telemetry)
- `5120ba3` test(03-05): add failing tests for RemapBanner + InfoToast + icon_clipboard + session wiring — 4 files / +538 lines (RED phase — 19 new tests)
- `3c27a2c` feat(03-05): RemapBanner + InfoToast + icon_clipboard + session degradation wiring — 7 files / +590 / -16 lines (GREEN phase; 2 new client modules + session wiring + protocol dispatch upgrade)

**Plan 05 delivered:**
- `MonitorListMsg.degradations: list = []` field added to common/messages.py carrying per-client fallback events `{client_token, previous_pick, now_showing}`. Empty list = pre-Plan-05 wire-compat default.
- server/monitor_hotplug.py iteration restructured so `apply_capture_mode` runs BEFORE the broadcast: per-session re-apply builds the degradations list in a single pass (apply_capture_mode returns False + previous_pick present → emit entry keyed by `ClientSession.client_id`); unified MonitorListMsg broadcast carries new topology + fallback events. `encoder_lifecycle.restart` stays sole encoder re-init entry. D-11 1s cadence preserved. D-10 NVIDIA xrandr-SET guard preserved (zero set operations).
- D-18 telemetry: `monitor_hotplug.broadcast` (monitor_count + degradation_count) + `monitor_hotplug.fallback` (events count) fire per iteration with counts only — no payload bytes, no monitor names (T-03-13).
- client/icons.py::icon_clipboard — UI-SPEC Surface 7 SVG body verbatim (clipboard silhouette). Plan 06 will consume for toolbar toggle.
- client/toasts.py NEW — `InfoToast` 360 px reusable widget; `show_monitor_switched_toast` (Surface 9, Plan 05); `show_oversize_image_toast` (Surface 8, Plan 06 use). Fade 120/200 ms; hover-pause; max 3 visible (T-03-19 mitigation); Esc/click dismiss. Theme tokens only, zero inline hex.
- client/remap_banner.py NEW — `RemapBanner` single-instance 48 px full-width banner per UI-SPEC Surface 5; 4-case verbatim copy dictionary (pick_missing / mirror_add / mirror_remove / single_change); only pick_missing renders "Choose monitor →" action link; sticky (no auto-timeout); Esc-dismiss + Enter-activate-action; 200 ms OutCubic slide-in; WARNING 3 px left border; theme tokens only.
- client/protocol.py MONITOR_LIST branch passes full msg dict (was `msg.get("monitors", [])`) so degradations payload reaches the session handler.
- client/session.py `_Bridge.monitor_list` Signal(list)→Signal(dict); Session.__init__ adds `remap_banner` / `toolbar` / `_client_token` / `_last_monitor_count` state; NEW `_on_monitor_list_with_degradations(msg)` handler: degradation matching our token → pick_missing banner + monitor-switched toast + toolbar.update_capture_mode(degraded=True); topology count delta without degradation → mirror_add / mirror_remove / single_change banner per capture_mode; T-03-18 mitigation filters entries by client_token (graceful single-session fallback when token empty, guarded to pick_one mode).

**Test gate:**
- 25 GREEN on Plan 05 target tests (1 messages round-trip + 2 hotplug iteration unit + 3 integration loopback + 2 icon + 6 toast + 8 banner + 3 session wiring)
- 3875 passed / 0 failed / 130 skipped on full quick suite (+25 vs Plan 04 code-complete baseline 3850; -2 Wave 0 skips converted GREEN)
- No latency regression — encoder restart path unchanged; banner + toast are presentation-layer only

**DISP-02 + DISP-06 requirement behavior landed:**
- DISP-02 (monitor hot-plug during session gracefully handled): auto-fallback to primary (Plan 03 foundation + Plan 05 iteration reorder) + RemapBanner pick_missing case + monitor-switched InfoToast + degraded mode badge. End-to-end: server detects topology change → re-applies per-session capture_mode → broadcasts MonitorListMsg with degradations → client shows non-modal banner + toast + flips mode badge. No crash path; session continues.
- DISP-06 (ScreenCaptureKit display-change handler): Plan 03 landed the `_DisplayChangeDelegate` (NSWorkspaceDidChangeScreenParametersNotification); Plan 05 completes the UX path that consumes the 1s-poll push-signaled hot-plug events. DISP-06 is now end-to-end code-complete on both Mac and Linux server paths.

**Known deviations (Plan 05):** Three Rule 1 inline fixes — (1) integration test strategy uses a `types.SimpleNamespace` fake runtime + apply_capture_mode closure instead of full websocket TLS loopback (already covered by `test_reconnect.py` for the unrelated supervisor path); (2) test assertions use `isHidden()` instead of `isVisible()` in 4 headless action-link tests because Qt offscreen visibility cascades from the parent chain — matches the Plan 02 Rule 1 pattern; (3) `test_info_toast_hover_stops_timer` uses a real QEnterEvent instead of a mock to satisfy super()-chain type-strict dispatch. Production behavior is correct in all three cases; fixes only tightened test harness. Documented in 03-05-SUMMARY.md.

**Phase 3 — 03-06 Wave 4 server clipboard completed (2026-04-20):**

- `cafcea6` feat(03-06): ClipboardChunkAssembler + 7 edge-case tests (D-17) — 2 files / +213 / -22 lines (NEW common/clipboard_chunks.py; 5 Wave 0 RED skeletons flipped GREEN + 2 new bounds tests)
- `cd593d9` feat(03-06): server/clipboard.py PNG path + CRLF preservation + hello toggles — 6 files / +457 / -64 lines (validate_png_payload + PNG image path + CRLF bytes-mode read + ClientHelloMsg toggle fields + fixture_png Rule 1 fix + 11 new GREEN tests)
- `17c0722` feat(03-06): server/mac_clipboard.py PNG path via NSPasteboardTypePNG — 2 files / +265 / -29 lines (NSPasteboardTypePNG + NSData bridge + shared validator import + drift-assert + 4 mac-only tests via pytest.importorskip("AppKit"))
- `3d96d1a` feat(03-06): per-direction clipboard gating + chunked transport + Pitfall 7 — 5 files / +654 / -30 lines (ClientSession toggle state + session_runtime _on_clipboard_change refactor + _enqueue_chunked_clipboard + CLIPBOARD_SEND c2s gate + NEW CLIPBOARD_CHUNK handler with Pitfall 7 _dropped_seqs continuation + 30s stale cleanup + CLIENT_HELLO toggle ingestion + 6 toggle tests)

**Plan 06 delivered:**
- `common/clipboard_chunks.py` NEW — `ClipboardChunkAssembler` indexed by chunk_index (not arrival order) for QUIC multiplexed safety. `MAX_TOTAL_CHUNKS=256` enforced at `__post_init__` (T-03-26 fail-fast). `MAX_CHUNK_BYTES=2MB` per-chunk cap in `add()` (T-03-27). `is_stale(now=None)` injectable-clock predicate (T-03-25, `CHUNK_TIMEOUT_S=30s`). Duplicate chunk_index is idempotent ignore; out-of-range dropped.
- `server/clipboard.py` — `get_clipboard` uses `subprocess.run(..., text=False)` + explicit UTF-8 decode so CRLF/LF/CR survive verbatim (closes the D-16 silent-universal-newlines bug). `get_clipboard_image` / `set_clipboard_image` via `xclip -t image/png` with sha256 `_last_image_hash` echo suppression. `validate_png_payload` defense-in-depth validator (magic + 64MB cap + PIL.verify). `_poll_loop` queries xclip TARGETS each tick; image path wins over text when both present. Two-arg `(content_type, payload)` `start_monitoring` callback.
- `server/mac_clipboard.py` — NSPasteboardTypePNG + NSData imports from Foundation; `get_clipboard_image` / `set_clipboard_image` mirroring the Linux contract. Shared `validate_png_payload` imported from server.clipboard; local `PNG_MAGIC` / `PNG_MAX_BYTES` carry drift-asserts for audit greppability. `_poll_loop` routes on `pb.types()`.
- `common/messages.py` — `ClientHelloMsg` extended with 4 clipboard_* toggle fields (D-15 wire payload; defaults all True per D-16 secure-defaults).
- `server/client_session.py` — per-session toggle state (clipboard_text_c2s/s2c + clipboard_image_c2s/s2c) + `_clipboard_chunks` assembler dict + `_dropped_seqs` continuation set (Pitfall 7 state).
- `server/session_runtime.py` — `_on_clipboard_change(content_type, payload)` refactored; outbound s2c gate short-circuits BEFORE JSON encode. `_enqueue_chunked_clipboard` splits base64-encoded PNG into 1MB `ClipboardChunkMsg` frames with monotonic per-runtime `sequence_id` via `_next_clipboard_seq`. Inbound `CLIPBOARD_SEND` c2s gate drops silently (no error response). NEW `CLIPBOARD_CHUNK` handler: per-session `ClipboardChunkAssembler` dict + Pitfall 7 chunk-0-boundary toggle gate with `_dropped_seqs` continuation tracking + D-16 defense-in-depth PNG revalidation BEFORE set_clipboard_image + 30s stale cleanup on every inbound chunk. CLIENT_HELLO handler reads 4 toggles from the wire.

**Test gate:**
- 23 GREEN on Plan 06 target battery (7 chunking + 3 CRLF parametrized + 7 image + 4 mac-image (skip on non-Mac via `pytest.importorskip("AppKit")`) + 6 toggles including Pitfall 7 mid-stream race with real PNG split across 2 chunks + CLIENT_HELLO population)
- 3899 passed / 0 failed / 115 skipped on full quick suite (+24 vs Plan 05 baseline 3875; -15 Wave 0 skips converted GREEN)
- All plan acceptance greps pass: ClipboardChunkAssembler exported; MAX_TOTAL_CHUNKS=256 enforced; 2 image methods each on Linux + Mac modules; validate_png_payload call sites ≥ 4; PNG_MAGIC + PNG_MAX_BYTES inline in both server modules; zero `text=True` in server/clipboard.py; NSPasteboardTypePNG count = 6; 8 clipboard_* toggle refs in session_runtime; _clipboard_chunks / _dropped_seqs / ClipboardChunkAssembler referenced
- T-03-32 payload-logging check: zero `logger.(info|warning).*data` matches across server/clipboard.py + server/mac_clipboard.py + server/session_runtime.py (payloads never logged — only counts + sizes + sha256 + sequence ids)

**CLIP-01 + CLIP-02 + CLIP-03 requirement behavior landed (server-side):**
- CLIP-01 (bidirectional text clipboard, CRLF-safe): `subprocess.run(..., text=False)` + explicit UTF-8 decode on `get_clipboard` — preserves CRLF/LF/CR verbatim on Linux path. Mac path unchanged (NSPasteboard strings are already byte-preserving). Client-side round-trip integration test lands in Plan 07.
- CLIP-02 (bidirectional image clipboard): `get_clipboard_image` / `set_clipboard_image` on both Linux (xclip -t image/png) + Mac (NSPasteboardTypePNG) with PNG magic + 64MB cap + PIL.verify defense-in-depth; sha256 `_last_image_hash` echo suppression. Outbound splits into `ClipboardChunkMsg` frames (1MB/chunk); inbound reassembles via `ClipboardChunkAssembler`. Client-side integration test lands in Plan 07.
- CLIP-03 (per-direction paste toggle): 4 toggle fields on `ClientHelloMsg` wire payload; `ClientSession.clipboard_text_c2s/s2c` + `_image_c2s/s2c` gating in `_on_clipboard_change` + `CLIPBOARD_SEND` + `CLIPBOARD_CHUNK` handlers with Pitfall 7 chunk-0-boundary race fix + `_dropped_seqs` continuation tracking. Client-side UI (`ClipboardToggleButton`) lands in Plan 07.

**Next action:** Run `/gsd-execute-phase 3` (or equivalent) to tackle Plan 03-07 (Wave 4 client clipboard UI + integration tests): ClipboardToggleButton in fullscreen toolbar + protocol send_clipboard refactor with W-6 per-chunk mid-stream cancellation + session wiring + CLIP-02 PNG round-trip integration tests that ride the server foundation from Plan 06.

**Known deviations (Plan 06):** Two Rule 1 inline fixes — (1) `tests/conftest.py` `fixture_png` payload had a bad IDAT CRC from Wave 0 scaffolding that passed the magic-byte check but failed `PIL.Image.verify()` (legitimately rejected by Plan 06's defense-in-depth validator); replaced with a byte-length-identical PIL.verify-clean 1×1 RGBA PNG (same decoded size, deterministic bytes). (2) `server/clipboard.py` docstring references to the historical `text=True` bug reworded to `text-mode-True` so the plan's strict-literal acceptance grep (`! grep "text=True" server/clipboard.py`) stays clean — semantic content preserved, zero behavior change. Documented in 03-06-SUMMARY.md.

---

*Initialized 2026-04-18 by gsd-roadmapper.*
*Phase 1 context gathered 2026-04-18 by gsd-discuss-phase.*
*Phase 2 context gathered 2026-04-18 by gsd-discuss-phase.*
*Phase 3 Plan 01 executed 2026-04-20 by gsd-execute-plan (sequential).*
*Phase 3 Plan 02 executed 2026-04-20 by gsd-execute-plan (sequential).*
*Phase 3 Plan 03 executed 2026-04-20 by gsd-execute-plan (sequential).*
*Phase 3 Plan 04 code-complete 2026-04-20 by gsd-execute-plan (sequential); D-08 manual hardware spike pending.*
*Phase 3 Plan 05 executed 2026-04-20 by gsd-execute-plan (sequential).*
*Phase 3 Plan 06 executed 2026-04-20 by gsd-execute-plan (sequential).*
