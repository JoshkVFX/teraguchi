---
phase: 1
slug: stability-ci-test-baseline
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-18
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution. Sourced from `01-RESEARCH.md` §"Validation Architecture".

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | `pytest` 8.3+ with `pytest-asyncio` 0.25+ (`asyncio_mode = "auto"`) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` section (**NEW — Wave 0**) |
| **Quick run command** | `python -m pytest tests/common tests/server tests/client tests/broker -x --timeout=30` |
| **Full suite command** | `python -m pytest -x --timeout=60` |
| **Lint quick check** | `python -m ruff check . && python -m ruff format --check .` |
| **Type quick check** | `python -m mypy common/ client/protocol.py` |
| **Estimated runtime** | Quick ~15-30s local · Full ~3-5 min local (< 10 min CI) |

---

## Sampling Rate

- **After every task commit:** Run the **quick** suite (lint + typecheck + `tests/common tests/server tests/client tests/broker`; excludes `tests/integration` + `tests/smoke`). Target: < 30s local.
- **After every plan wave:** Run the **full** suite including `tests/integration`. Target: < 5 min local, < 10 min CI.
- **Before `/gsd-verify-work 1`:** Full suite green + all 4 CI jobs green on the PR + one nightly smoke run green on **each** runner (macos-14 + rockylinux:9).
- **Max feedback latency:** 30 seconds per task commit.

---

## Per-Task Verification Map

> Task IDs are placeholders pending `gsd-planner` output. Requirement-to-test mapping is final.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 1-XX-XX | XX | W | STAB-01 | — | N/A | unit | `pytest tests/common/test_messages.py -x` | ❌ W0 | ⬜ pending |
| 1-XX-XX | XX | W | STAB-01 | — | N/A | unit | `pytest tests/common/test_keymap.py -x` | ❌ W0 | ⬜ pending |
| 1-XX-XX | XX | W | STAB-01 | — | N/A | unit | `pytest tests/common/test_jitter_buffer.py -x` | ❌ W0 | ⬜ pending |
| 1-XX-XX | XX | W | STAB-01 | — | PAM mock boundary | unit | `pytest tests/server/test_auth.py -x` | ❌ W0 | ⬜ pending |
| 1-XX-XX | XX | W | STAB-01 | — | HMAC round-trip + TTL + tamper | unit | `pytest tests/broker/test_tokens.py -x` | ❌ W0 | ⬜ pending |
| 1-XX-XX | XX | W | STAB-01 | — | XOR encrypt/decrypt round-trip | unit | `pytest tests/client/test_bookmarks.py -x` | ❌ W0 | ⬜ pending |
| 1-XX-XX | XX | W | STAB-02 | — | N/A | workflow | `.github/workflows/ci.yml` exists + macos-14 + rockylinux:9 jobs green | ❌ W0 | ⬜ pending |
| 1-XX-XX | XX | W | STAB-03 | — | N/A | workflow | `ruff check` + `mypy` exit 0 in CI | ❌ W0 | ⬜ pending |
| 1-XX-XX | XX | W | STAB-04 | T-1-04 | `send_queue` drop triggers exactly one IDR per drop streak | unit | `pytest tests/server/test_pipelines.py::test_send_queue_idr_on_drop -x` | ❌ W0 | ⬜ pending |
| 1-XX-XX | XX | W | STAB-05 | — | Characterization: server/main.py behaviour unchanged post-extraction | integration | `pytest tests/integration/test_server_bootstrap.py -x` | ❌ W0 | ⬜ pending |
| 1-XX-XX | XX | W | STAB-06 | — | FSM state transitions only follow allowed pairs; disagreement surfaces via health pings | unit + integration | `pytest tests/common/test_session_fsm.py tests/integration/test_fsm_state_sync.py -x` | ❌ W0 | ⬜ pending |
| 1-XX-XX | XX | W | STAB-07 | — | All 4 pipeline queues enforce documented drop policy | unit | `pytest tests/server/test_pipelines.py -x` | ❌ W0 | ⬜ pending |
| 1-XX-XX | XX | W | STAB-08 | — | ConnectionSupervisor backoff + jitter + retry cap + FSM drive | unit | `pytest tests/client/test_connection_supervisor.py -x` | ❌ W0 | ⬜ pending |
| 1-XX-XX | XX | W | STAB-09 | — | 1-hour synthetic smoke harness green; all 4 D-17 assertions pass | smoke | `pytest tests/smoke/test_synthetic_1h.py -v --timeout=4000` | ❌ W0 | ⬜ pending |
| 1-XX-XX | XX | W | SEC-01 | T-1-01 | All 4 `CERT_NONE` sites removed; client rejects self-signed cert from wrong CA | integration | `pytest tests/integration/test_tls_verify.py -x` | ❌ W0 | ⬜ pending |
| 1-XX-XX | XX | W | OBS-01 | — | structlog JSON emits include required schema fields every time | unit | `pytest tests/common/test_logging.py -x` | ❌ W0 | ⬜ pending |
| 1-XX-XX | XX | W | OBS-02 | — | Per-stage latency breakdown emitted in HealthStats | unit + integration | `pytest tests/server/test_health_monitor.py tests/integration/test_latency_breakdown.py -x` | ❌ W0 | ⬜ pending |
| 1-XX-XX | XX | W | OBS-03 | — | keyframe_requested / keyframe_emitted counters exposed | unit | `pytest tests/server/test_health_monitor.py::test_keyframe_telemetry -x` | ❌ W0 | ⬜ pending |
| 1-XX-XX | XX | W | OBS-05 | T-1-05 | Diagnostic bundle contains all documented sections; redaction rules enforced | integration | `pytest tests/integration/test_diag_bundle.py -x` | ❌ W0 | ⬜ pending |
| 1-XX-XX | XX | W | D-08 gate | — | Latency p99 < 25 ms LAN in synthetic benchmark | smoke | `pytest tests/smoke/test_latency_benchmark.py -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

*Planner must replace `1-XX-XX` placeholders with concrete task IDs during plan generation, and tie the STAB-04 / SEC-01 / OBS-05 rows to the security threat model entries.*

---

## Wave 0 Requirements

Every item below is a **prerequisite** before the per-task matrix can turn green. All are net-new (zero tests today, zero CI today).

### Config

- [ ] `pyproject.toml` — add `[tool.pytest.ini_options]`, `[tool.ruff]`, `[tool.mypy]`; bump `requires-python = ">=3.12"`
- [ ] `requirements-dev.txt` — add `pytest==8.3.*`, `pytest-asyncio==0.25.*`, `pytest-timeout`, `pytest-cov`, `pytest-xdist`, `ruff==0.11.*`, `mypy==1.14.*`, `python-statemachine>=2.6`, `structlog==25.1.*`, `psutil`, `freezegun`
- [ ] `tests/conftest.py` — root fixtures: TLS CA builder, structlog capture, offscreen Qt, canned encoded frames

### `tests/common/`

- [ ] `tests/common/__init__.py`
- [ ] `tests/common/test_messages.py` — STAB-01
- [ ] `tests/common/test_keymap.py` — STAB-01
- [ ] `tests/common/test_jitter_buffer.py` — STAB-01
- [ ] `tests/common/test_hybrid_transport.py` — STAB-01
- [ ] `tests/common/test_session_fsm.py` — STAB-06
- [ ] `tests/common/test_logging.py` — OBS-01

### `tests/server/`

- [ ] `tests/server/__init__.py`
- [ ] `tests/server/test_auth.py` — STAB-01
- [ ] `tests/server/test_pam_auth.py` — STAB-01 with mocked `pam.pam()`
- [ ] `tests/server/test_video_encoder_mock.py` — D-02 mocked FFmpeg subprocess
- [ ] `tests/server/test_pipelines.py` — STAB-04, STAB-07
- [ ] `tests/server/test_health_monitor.py` — OBS-02, OBS-03

### `tests/broker/`

- [ ] `tests/broker/__init__.py`
- [ ] `tests/broker/test_tokens.py` — STAB-01

### `tests/client/`

- [ ] `tests/client/__init__.py`
- [ ] `tests/client/test_bookmarks.py` — STAB-01
- [ ] `tests/client/test_connection_supervisor.py` — STAB-08

### `tests/integration/`

- [ ] `tests/integration/__init__.py`
- [ ] `tests/integration/conftest.py` — loopback server/client harness (D-03)
- [ ] `tests/integration/test_auth_flow.py`
- [ ] `tests/integration/test_tls_verify.py` — SEC-01
- [ ] `tests/integration/test_fsm_state_sync.py` — STAB-06
- [ ] `tests/integration/test_reconnect.py` — STAB-08
- [ ] `tests/integration/test_diag_bundle.py` — OBS-05
- [ ] `tests/integration/test_latency_breakdown.py` — OBS-02
- [ ] `tests/integration/test_server_bootstrap.py` — STAB-05 characterization

### `tests/smoke/`

- [ ] `tests/smoke/__init__.py`
- [ ] `tests/smoke/fixtures/canned_encoded_frames.bin` — D-02 canned data
- [ ] `tests/smoke/test_latency_benchmark.py` — D-08 gate, D-09 synthetic accumulator
- [ ] `tests/smoke/test_synthetic_1h.py` — STAB-09 (Phase 1 = 1-hour per D-18)

### CI Workflows

- [ ] `.github/workflows/ci.yml` — STAB-02, STAB-03 (pytest + ruff + mypy on macos-14 + rockylinux:9)
- [ ] `.github/workflows/build-artifacts.yml` — D-08 artifact gate (PyInstaller `.app` arm64-only; RPM spec `rpmbuild --buildonly` dry-run)
- [ ] `.github/workflows/smoke-nightly.yml` — D-16 nightly cron (1-hour harness per D-18)

### Framework install

Covered once `requirements-dev.txt` diff lands and Wave 0 executes `pip install -r requirements-dev.txt`.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Real-hardware before/after latency comparison on DXS Flame box | CONTEXT.md §"Specific Ideas" (no-regression core-value check) | GitHub-hosted CI uses mocked encoders (D-02); real-NVENC/VideoToolbox numbers must come from a dev workstation | On `dxs-flame-01`: run a full Flame session pre-Phase-1-merge → capture p99 input-to-photon → run same session post-merge → assert delta < 5% |
| PyInstaller `.app` on macos-14 arm64 actually launches (not just exit-code 0) | D-08 artifact gate | CI smoke-builds the `.app` but only asserts exit code; a launch check would require `open -W` + window inspection that GHA can't reliably do | On Randy's Mac Studio: download the CI artifact, `open Teraguchi.app`, confirm window appears, close cleanly |
| Rocky 9 RPM install on a fresh VM | D-08 artifact gate | CI dry-runs `rpmbuild --buildonly`; actual `dnf install ./teraguchi-server-*.rpm` on a clean Rocky 9 VM confirms deps + postinstall | On a throwaway Rocky 9 VM: `dnf install ./<rpm>` then `systemctl status teraguchi-server` |
| `python-statemachine` async transition race under real socket backpressure | STAB-06 + A6 in research assumptions log | Unit tests use in-process loopback; real socket backpressure needs wire latency | On LAN between Mac Studio and dxs-flame-07: drive handshake → streaming → degraded → streaming loop 100× while throttling via `tc qdisc`; assert no `UnknownStateError` |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies explicitly linked
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all ❌ MISSING references in the per-task matrix
- [ ] No watch-mode flags (`pytest --watch`, `ruff --watch`, etc. — all one-shot)
- [ ] Feedback latency < 30s on quick suite
- [ ] `nyquist_compliant: true` set in frontmatter after planner populates task IDs

**Approval:** pending
