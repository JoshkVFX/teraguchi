---
phase: 2
slug: input-color-fidelity
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-18
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: `02-RESEARCH.md` §Validation Architecture (Nyquist signals for each of the 5 ROADMAP success criteria + the 9 silent 10-bit downgrade checkpoints).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (Phase 1 baseline: 229 tests + 1 xfail) |
| **Config file** | `pyproject.toml` (pytest + ruff + mypy), `.github/workflows/ci.yml` (4 CI gates) |
| **Quick run command** | `pytest -x -q tests/common tests/client tests/server` |
| **Full suite command** | `pytest` (includes `tests/integration` + `tests/smoke`) |
| **Estimated runtime** | ~90 seconds quick; ~6 minutes full (including the 1-hour smoke harness excluded by default marker) |

Additional gates (inherited from Phase 1, must stay green):

- `pytest` (all marker-default tests)
- `ruff check . && mypy .` (lint + type)
- Build artifact smoke (`python -m client --version`, `python -m server --version`)
- Synthetic latency p99 < 25ms (Phase 1 D-08/D-09 gate)

Phase 2 adds:

- **9-checkpoint 10-bit fixture** — gated in `pytest tests/smoke/test_ten_bit_pipeline.py` (fast path: checkpoints 1–6 via mocks; slow path: checkpoints 7–9 via GPU-optional mark, skipped on GHA)
- **Exhaustive keymap matrix** — `pytest tests/common/test_keymap.py` (~2000 parametrized cases, <5s)
- **Crazy hotkeys integration** — `pytest tests/integration/test_crazy_hotkeys.py` (in-process loopback)
- **Wacom pressure RMS** — `tools/wacom_quant_analysis.py <jsonl>` — manual, gated in Phase 2 verification only

---

## Sampling Rate

- **After every task commit:** Run `pytest -x -q <files_touched>` (at minimum the targeted test files)
- **After every plan wave:** Run `pytest -x -q tests/common tests/client tests/server` + `ruff check .`
- **Before `/gsd-verify-work`:** Full suite green + 9-checkpoint fixture green + exhaustive keymap green + synthetic latency gate green
- **Max feedback latency:** ~90s quick cycle; ~6 min full cycle

---

## Per-Task Verification Map

> Preliminary — the planner fills this in as `/gsd-plan-phase` generates individual PLAN.md files. Every task must either link to an automated test command here OR declare a Wave 0 dependency. No task may ship with "manual only" unless it appears in `## Manual-Only Verifications`.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 02-XX-YY | {plan} | {wave} | INPUT-/VIDEO-* | — | N/A (Phase 2 is non-security-facing per CONTEXT.md; Phase 1 closed SEC-01) | unit / integration / smoke | `{command}` | ⬜ TBD | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

**Planner obligation:** when a PLAN.md task lists `requirements: [INPUT-XX]` or `requirements: [VIDEO-XX]`, it MUST reference the corresponding row(s) here and supply the `automated_command` field. Rows without a command will block the plan-checker.

---

## Wave 0 Requirements

Wave 0 closes infrastructure gaps that block the rest of the phase. Derived from `02-RESEARCH.md` §Validation Architecture "Wave-0 gaps":

- [ ] `tests/smoke/fixtures/ten_bit_ramp.y4m` + `tests/smoke/fixtures/ten_bit_ramp_pixels.json` — synthetic 10-bit ramp with known bottom-2-bit checksum (D-01 checkpoint reference data)
- [ ] `tests/smoke/test_ten_bit_pipeline.py` — the 9-checkpoint byte-equality test harness (stubs allowed; real capture/encode paths hooked by later waves)
- [ ] `tests/common/test_keymap.py` — upgrade Phase 1 stub to the full parametrized table (Qt × modifier × {linux scancode, mac virtual key code}); D-12
- [ ] `tests/integration/test_crazy_hotkeys.py` — in-process loopback scaffold (INPUT-04)
- [ ] `tests/server/test_mac_video_encoder.py` — mock-at-VT-boundary skeleton (mirrors Phase 1 D-02 pattern for FFmpeg)
- [ ] `tests/server/test_mac_pen_injector.py` — mock-at-IOKit-boundary skeleton
- [ ] `tests/server/test_hw_capability_probe.py` — stubs for `supports_main10`/`supports_422`/`supports_444` negotiation (D-03)
- [ ] `tests/common/test_messages_phase2.py` — `KEY_RESET_MODIFIERS`, `TextCommit`, `PenProximity` wire-round-trip (extends `common/messages.py`)
- [ ] `tools/wacom_quant_analysis.py` — argparse script skeleton + one dry-run fixture (D-18)
- [ ] `.github/workflows/ci.yml` — wire the new test selectors; keep the 4 Phase 1 gates unchanged

*Wave 0 is a single plan (suggested 02-01) and must land before any of Waves 1–6 start.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Real Wacom hardware matrix — Intuos Pro Large + Cintiq Pro 24 × macOS Sonoma + macOS Sequoia, full D-17 6-step protocol per cell | INPUT-09, INPUT-10, INPUT-11, INPUT-12 | Physical tablet required; Phase 1 D-05 locked "GitHub-hosted CI only" — no self-hosted runners for Wacom in v1 | Follow `docs/release.md` Wacom runbook (seeded in this phase per D-16). Record video. Attach structlog JSONL to release notes. Pass gate: every counter meets assertion AND `tools/wacom_quant_analysis.py` reports RMS < 1% per cell. |
| Pressure-curve qualitative sign-off | INPUT-08, INPUT-12 | "Looks right in a Flame paint stroke" is a perceptual judgment | Flame artist draws standard test stroke on Cintiq Pro 24, signs off that quantization artifacts are not visible. Record the session. |
| DXS end-to-end input-to-photon latency (pre vs post Phase 2) | Success criterion 4 | Requires DXS Flame workstation + real Cintiq + measurement rig — cannot run in GHA | Execute the Phase 1 DXS latency script on a Rocky Flame box with Phase 1 HEAD; repeat with Phase 2 HEAD. Commit the number to `docs/release.md`. Fails phase sign-off if post > pre. |
| Reference Mode / EDR / ICC state on MBP XDR | VIDEO-01, D-01 checkpoint 9 | macOS display-pipeline state can't be queried reliably from user-space apps; operator must visually confirm | Document in `docs/release.md` Phase 6 runbook: Reference Mode ON, True Tone OFF, Night Shift OFF, no ICC profile overriding the display. Client health overlay shows the negotiated state (D-03 badge) but the final display path is trusted. |
| 4:2:2 Grading-mode perceptual check | VIDEO-05 | Subjective — "grading feels right" on an M3+ Mac decoding 4:2:2 Main10 | Artist grades a standard reference clip on the 4:2:2 path; signs off. Compared against the 4:2:0 baseline. |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or a Wave 0 dependency linked above
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers every MISSING `File Exists` reference
- [ ] No watch-mode flags in any CI command
- [ ] Feedback latency < 90s (quick) / < 360s (full) — confirmed in CI runtime
- [ ] 9-checkpoint 10-bit fixture green in GHA
- [ ] Exhaustive keymap matrix green in GHA
- [ ] Phase 1's 4 CI gates still green (no regression)
- [ ] Manual-only checks above are scheduled in Phase 2 verification runbook
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
