---
phase: 02-input-color-fidelity
verified: 2026-04-19T00:00:00Z
status: human_needed
score: 4/5 must-haves verified (1 blocked by CR-01 gap; 1 awaits human DXS checkpoint)
overrides_applied: 0
gaps:
  - truth: "A bit-exact 10-bit ramp test pattern round-trips capture → encode → transport → decode → display with no banding (CI fixture asserts byte-equality on the bottom 2 bits at 9 known pipeline checkpoints; one regression fails CI)."
    status: partial
    reason: "9-checkpoint fixture is 6/9 GREEN automated (cp.2/3/4/5/6/7), 1/9 XFAIL (cp.1 — Linux NvFBC P010 capture surface format assertion left as 'Wave 4 owner / Linux GPU runner' TODO; capture plumbing exists in server/screen_capture.py + server/nvfbc/nvfbc_capture.c but the smoke test still calls pytest.fail()), 2/9 SKIPPED by D-01 design (cp.8 manual-verified-once on MBP XDR; cp.9 macOS Reference Mode is log-only). MORE CRITICALLY: server/mac_video_encoder.py::feed_frame submits an empty CVPixelBuffer for every frame (line 254 `del p010_bytes` with documented TODO) — when MacVideoEncoder is the active dispatch path on a macOS server (the documented production path whenever pyobjc-framework-VideoToolbox is importable per server/platform_backends.py:65-83), the encoded HEVC NAL bytes are valid Main10 frames of UNDEFINED HEAP MEMORY. The capability badge advertises '10-bit confirmed' while the displayed pixels are stale RAM. cp.1 xfail and CR-01 together mean the 'bit-exact end-to-end' contract holds only on Linux→Mac (and even there cp.1 is unwired); Mac→Mac is wired-but-functionally-broken until plane copy lands."
    artifacts:
      - path: "server/mac_video_encoder.py"
        issue: "feed_frame() at lines 222-280 allocates CVPixelBuffer via CV.CVPixelBufferCreate, then `del p010_bytes` at line 254 discards captured plane bytes. VTCompressionSessionEncodeFrame submits the empty buffer. Production dispatch (server/platform_backends.py:_MAC_VIDEO_ENC_AVAILABLE) prefers this path whenever PyObjC VT imports succeed."
      - path: "tests/smoke/test_ten_bit_pipeline.py"
        issue: "test_checkpoint_1_capture_surface_is_p010 at lines 65-70 carries @pytest.mark.xfail(reason='Wave 2 - Linux P010 capture not wired') and calls pytest.fail() in the body — capture plumbing exists in screen_capture.py (want_10bit ctor kwarg, runtime_capability_state property) and nvfbc_capture.c (NVFBC_BUFFER_FORMAT_YUV420P10LE flag), so the test is stale; checkpoint should be wired and asserted."
    missing:
      - "Implement P010 plane copy in server/mac_video_encoder.py::feed_frame: CVPixelBufferLockBaseAddress + ctypes.memmove Y + UV planes from p010_bytes (the REVIEW.md fix snippet is the working pattern), OR set _MAC_VIDEO_ENC_AVAILABLE=False to deterministically fall back to FFmpeg hevc_videotoolbox until plane copy lands. Either is a Phase 2 blocker — without one of these, every Mac-server video frame is UB heap memory."
      - "Add a follow-up test to tests/server/test_mac_video_encoder.py that feeds a known-pattern P010 frame, captures the encoded NAL output, and asserts the slice payload is non-trivial (i.e. not just SPS+PPS+empty-slice)."
      - "Wire test_checkpoint_1_capture_surface_is_p010 to assert against the live screen_capture.py capability surface (want_10bit + runtime_capability_state) instead of pytest.fail; remove the xfail. Capture-side plumbing already exists per 02-08-SUMMARY note ('capture-side P010 plumbing already in place per server/nvfbc/nvfbc_capture.c')."
human_verification:
  - test: "DXS 4-cell Wacom hardware matrix"
    expected: "All 4 cells (Intuos Pro Large + Cintiq Pro 24 × macOS Sonoma + Sequoia) pass D-17 6-step protocol (pressure ramp / eraser flip / tilt / proximity cycle / side-buttons / reconnect mid-stroke); RMS pressure-quantization error <1% per cell (D-18); Flame artist sign-off on Cintiq Pro 24 + Sequoia cell. Replace 10× `<DEFERRED — Randy to execute at DXS>` placeholders in docs/release.md with real values + recorded video links."
    why_human: "Requires real Wacom Intuos Pro Large + Cintiq Pro 24 hardware in the DXS lab on real macOS Sonoma + Sequoia clients connected to a Rocky 9 Flame server. No autonomous executor / GHA runner can satisfy this gate. Plan 02-12 has autonomous: false and explicitly defers Tasks 2 and 3 to Randy. INPUT-09 / INPUT-10 / INPUT-11 / INPUT-12 hardware-verification leg awaits this checkpoint."
  - test: "DXS pre/post-Phase-2 input-to-photon latency comparison (D-21 / VIDEO-11)"
    expected: "On a DXS Mac client + Rocky Flame workstation server with real Wacom + Cintiq, capture p50/p95/p99 input-to-photon latency at HEAD-of-Phase-1-verification and at HEAD-of-Phase-2 (3 trial sessions each, ~60s of typical Flame interaction). Post-Phase-2 p99 must be ≤ pre-Phase-2 p99 × 1.15 (no >15% regression). Bonus: post-Phase-2 p99 < 20ms. Replace 9× `<DEFERRED — Randy to execute at DXS>` placeholders in docs/release.md results table."
    why_human: "Real-hardware end-to-end measurement on a real Tailscale LAN with real Wacom hardware; CI's synthetic p99 < 25ms gate (Phase 1 D-08/D-09) cannot prove this on its own. Plan 02-12 Task 3 explicitly checkpoint:human-verify."
  - test: "INPUT-08 IOHIDUserDevice spike re-attempt on a workstation with hardware + apps"
    expected: "Either (a) PASS — a `pyobjc-framework-IOKit` script registers a virtual Wacom HID tablet via IOHIDUserDeviceCreate; Photoshop / Preview / NSView test app reads `NSEvent.pressure > 0` over a complete pen stroke; productionize server/mac_pen_injector.py per 02-10 PASS-branch sketch — OR (b) re-affirm FAIL outcome with fresh evidence, leave INPUT-08 as documented v1 limitation per docs/release.md."
    why_human: "Per docs/release.md, the autonomous executor cannot satisfy the D-08 PASS bar (no pyobjc-framework-IOKit in sandbox; no Photoshop / Preview / NSView app; no real Wacom). Currently shipped as documented v1 limitation per planned D-07 FAIL branch — Mac-server pen pressure stays mouse-click. Re-attempt only if a real studio commits to Flame-on-Mac as load-bearing."
  - test: "Visual 10-bit color confirmation on MBP XDR (D-01 cp.8)"
    expected: "Connect Mac client (MBP XDR or Pro Display XDR) to a Rocky 9 Flame server. Display the 10-bit ramp fixture (tests/smoke/fixtures/10bit_ramp.p010.bin) full-screen via the live decode + QRhi blit path. Verify by eye that the gradient shows no visible banding (artist eyeballs the bottom 2 bits — no posterization). cp.8 is intentionally manual-once per D-01."
    why_human: "Bottom 2 bits of luma are below the threshold of automated readback through the Metal blit; D-01 explicitly designates cp.8 as a manual-verified-once visual gate. Skipped in CI by design (`@pytest.mark.skip(reason='Checkpoint 8 is manual-verified-once - see VALIDATION.md Manual-Only')`)."
  - test: "Crazy-hotkeys integration test against a real Rocky 9 server AND a real Mac server"
    expected: "ROADMAP success criterion #2 demands every modifier chord (Ctrl+Shift+Alt+letter, Cmd↔Ctrl swap, Caps Lock state, dead-keys on US/UK/DE/JP) passes against BOTH a real Rocky server AND a real Mac server with zero mangling. tests/integration/test_crazy_hotkeys.py covers FLAME_CRITICAL_CHORDS in-process loopback (28 test IDs) — but the in-process loopback is not the same as a real Rocky Flame workstation receiving uinput events or a real macOS server receiving CGEventPost. Run the test suite on both real servers (DXS Rocky 9 + dxs-studio-01 macOS) and confirm hotkeys land correctly in a real Flame paint session."
    why_human: "In-process loopback validates the wire path; real-server validation requires hands on a Rocky-9 Flame workstation and a macOS server, plus the operator (Randy or a Flame artist) typing the chords and confirming Flame's response. CI cannot stand up a Flame instance."
---

# Phase 2: Input + Color Fidelity Verification Report

**Phase Goal:** Close every silent 10-bit downgrade point in the Mac→Rocky / Mac→Mac pipeline AND make Wacom + modifier-chord input lossless on the Mac client. From PROJECT.md: "10-bit end-to-end, HEVC Main10. 9 silent-downgrade points exist — every video change must be verified against VIDEO-01/VIDEO-02 test fixture. Input fidelity: zero tolerance for Wacom pressure glitches or modifier-chord mangling."

**Verified:** 2026-04-19T00:00:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | A bit-exact 10-bit ramp test pattern round-trips capture → encode → transport → decode → display with no banding (CI fixture asserts byte-equality on the bottom 2 bits at 9 known pipeline checkpoints; one regression fails CI) | ✗ FAILED | 6/9 checkpoints automated GREEN (cp.2/3/4 encoder, cp.5/6 decoder, cp.7 QRhi); cp.1 still XFAIL with stale `pytest.fail()` body though capture plumbing exists; cp.8/9 SKIPPED-by-design (manual one-off / log-only). **CR-01 critical bug**: server/mac_video_encoder.py:254 discards captured P010 plane bytes (`del p010_bytes`) — Mac-server production path emits empty CVPixelBuffer for every frame; client receives valid Main10 NAL units containing UNDEFINED HEAP MEMORY. Mac→Mac pipeline is wired-but-broken; Linux→Mac is mostly green except cp.1 wiring. Banding-free claim cannot be defended on Mac server. |
| 2 | The "crazy Flame hotkey combos" integration test — every modifier chord (Ctrl+Shift+Alt+letter, Cmd↔Ctrl swap, Caps Lock state, dead-keys on US/UK/DE/JP layouts) — passes against both a real Rocky server and a real Mac server with zero mangling | ✓ VERIFIED (in-process) / ? NEEDS HUMAN (real-server) | Automated: tests/integration/test_crazy_hotkeys.py covers FLAME_CRITICAL_CHORDS (22 chords + 2 swap variants + 3 TextCommit + 1 reconnect-order = 28 test IDs); tests/common/test_keymap.py runs ~3533 parametrized cases (per 02-03-SUMMARY); IME / dead-key path goes through TextCommitMsg in viewer.inputMethodEvent (not synthesized keycodes per D-15). Real-Rocky + real-Mac end-to-end against an actual Flame workstation routed to human verification. |
| 3 | Wacom pen pressure, tilt, eraser, tablet-side buttons, and proximity events round-trip with sub-1% pressure quantization error on Intuos Pro Large AND Cintiq Pro 24, on macOS Sonoma AND Sequoia (4-cell hardware matrix passing) | ? NEEDS HUMAN | tools/wacom_quant_analysis.py is fully implemented (198 lines, scipy.interpolate + RMS + matplotlib SVG, exit 1 iff RMS >= threshold); D-17 schema contract test exists (tests/server/test_wacom_matrix_emission.py); PenFSM lands in common/session_fsm.py (out_of_proximity ↔ in_proximity, idempotent); proximity re-synth wires viewer.focusInEvent + showEvent → PenProximityMsg per D-19. **The 4-cell physical matrix has not been executed** — docs/release.md contains 10 × `<DEFERRED — Randy to execute at DXS>` placeholders. Plan 02-12 has autonomous: false. |
| 4 | Input-to-photon latency on LAN measures sub-20ms with the Phase-1 instrumentation; CI benchmark fails the build if the number drifts above 25ms | ✓ VERIFIED (synthetic) / ? NEEDS HUMAN (DXS hardware) | CI synthetic p99 < 25ms gate (.github/workflows/ci.yml:107-127, Phase 1 D-08/D-09) is preserved unchanged in Phase 2. Per-stage structlog telemetry (Phase 1 OBS-02) instrument the pipeline. **Real-hardware sub-20ms claim awaits DXS measurement** — docs/release.md latency results table contains 9 × `<DEFERRED — Randy to execute at DXS>`. Plan 02-12 Task 3 is checkpoint:human-verify. |
| 5 | Modifiers release cleanly on `WindowDeactivate` (no more stuck-Ctrl after Cmd+Tab) and on reconnect — verified by automated focus-stress and reconnect-stress tests | ✓ VERIFIED | All 4 D-11 triggers wired: focusOutEvent (client/viewer.py:920-928 emits reset_modifiers_requested with reason='focus_out'), ConnectionSupervisor reconnect first-post-auth (client/connection_supervisor.py + client/protocol.py:339 send_reset_modifiers), F9 panic shortcut (client/main_window.py:737 QShortcut application-scope), server-side periodic safety net (server/session_runtime.py + tests/server/test_modifier_dispatch.py::test_should_fire_periodic_reset_*). All funnel through idempotent server-side InputInjector.reset_modifiers. tests/integration/test_modifier_stress.py covers focus-stress + reconnect-stress + held-chord-not-broken-by-periodic. xset -display $DISPLAY r off wired in server/session_manager.py:377. |

**Score:** 4/5 truths fully verified or routed to human checkpoint. Truth #1 has a real critical gap (CR-01) blocking the Mac-server production path.

### Required Artifacts (12 plans × must_haves cross-check)

| Plan | Artifact | Expected | Status | Details |
|------|----------|----------|--------|---------|
| 02-01 | `tests/smoke/fixtures/10bit_ramp.p010.bin` | Bit-exact P010 ramp reference (~7.7 MB) | ✓ VERIFIED | 7,776,000 bytes; matches `1920*1080*1.5*2.5/2` P010 layout |
| 02-01 | `tests/smoke/fixtures/10bit_ramp.reference.ffprobe.json` | Expected ffprobe baseline | ✓ VERIFIED | 841 bytes; cp.3 reads ffprobe_pix_fmt=yuv420p10le, profile="Main 10" |
| 02-01 | `tools/gen_10bit_ramp.py` | Reproducible generator | ✓ VERIFIED | 3,050 bytes; reproduces fixture deterministically |
| 02-01 | `tools/wacom_quant_analysis.py` | Stub → full impl | ✓ VERIFIED (stub at 02-01; fully implemented at 02-12) | 198 lines; numpy + scipy.interpolate.interp1d + matplotlib SVG; exit codes 0/1/2 per D-18 |
| 02-01 | `tests/smoke/test_ten_bit_pipeline.py` | 9-checkpoint harness | ⚠️ STUB on cp.1 | 6/9 PASS, 1/9 XFAIL (cp.1 stale TODO with pytest.fail body), 2/9 SKIPPED-by-design (cp.8/9) |
| 02-01 | pytest markers + CI wiring | flame_critical / wacom_hw / ten_bit_smoke / gpu | ✓ VERIFIED | pyproject.toml:46-48; addopts="-m 'not wacom_hw'" (line 53); CI deselects wacom_hw + gpu (.github/workflows/ci.yml:66, 103) |
| 02-02 | `common/messages.py` (extensions) | KEY_RESET_MODIFIERS / TEXT_COMMIT / PEN_PROXIMITY MsgType + dataclasses + KeyEventMsg lock bits + ServerColorCaps | ✓ VERIFIED | line 129 KEY_RESET_MODIFIERS; line 477 ServerColorCaps; line 524 color_caps field on ServerHelloMsg; lines 605-629 KeyResetModifiersMsg / TextCommitMsg / PenProximityMsg |
| 02-02 | `tests/common/test_messages_phase2.py` | 7 round-trip tests | ✓ VERIFIED | Wave 0 xfails cleared; tests pass per 02-02-SUMMARY |
| 02-03 | `common/keymap.py` (extensions) | QT_KEY_TO_MAC_VK + qt_key_to_mac_vk + FLAME_CRITICAL_CHORDS + swap_cmd_ctrl_for_linux_dest | ✓ VERIFIED | line 128 QT_KEY_TO_MAC_VK (79 entries per SUMMARY); line 218 FLAME_CRITICAL_CHORDS (22 entries); line 192 swap_cmd_ctrl_for_linux_dest |
| 02-03 | `tests/common/test_keymap.py` | ~2000 parametrized cases | ✓ VERIFIED | 301 lines; 3533 parametrized cases per 02-03-SUMMARY |
| 02-04 | `server/capability_probe.py` | probe_nvenc_main10 + probe_vt_main10 | ✓ VERIFIED | line 43 probe_nvenc_main10; line 134 probe_vt_main10 |
| 02-04 | `server/video_encoder.py` (HWEncoder ext) | supports_main10/422/444/main10_detection | ✓ VERIFIED | 40 occurrences of p010le/main10/YUV420P10LE in file |
| 02-04 | `server/bootstrap.py` | Capability probe invocation + ServerColorCaps population | ✓ VERIFIED | lines 21, 88-89 probe dispatch; line 122 build_color_caps; line 140 ServerColorCaps( |
| 02-04 | `client/health_display.py` | "10-bit: confirmed/negotiated/degraded/not_supported" badge | ✓ VERIFIED | render_color_badge function exists per 02-04-SUMMARY; consumed in overlay |
| 02-05 | `server/mac_video_encoder.py` | VTCompressionSession wrapper, EnableLowLatencyRateControl, kVTProfileLevel_HEVC_Main10_AutoLevel, AllowFrameReordering=False | ⚠️ HOLLOW (CR-01) | Wrapper exists with all configuration correct (lines 135-189), BUT feed_frame at line 254 `del p010_bytes` discards captured planes; encoded NALs contain UB heap memory. Production-active per platform_backends.py:65-83. |
| 02-05 | `server/mac_screen_capture.py` | .hdrLocalDisplay + 420YpCbCr10BiPlanarVideoRange | ✓ VERIFIED | 7 occurrences of HDR/P010 patterns; lines 103, 107, 236, 377-401 |
| 02-05 | `server/platform_backends.py` | Mac encoder dispatch | ✓ VERIFIED | _MAC_VIDEO_ENC_AVAILABLE flips True whenever pyobjc-VT imports successfully (lines 65-83) |
| 02-05 | `tests/server/test_mac_video_encoder.py` | 5 mock-at-VT-boundary tests | ✓ VERIFIED | 8,275 bytes; covers VT subprocess boundary |
| 02-06 | `server/video_encoder.py` (NVENC main10) | -pix_fmt p010le -profile:v main10 | ✓ VERIFIED | 40 p010le/main10 occurrences; cp.2 PASSES against live _build_ffmpeg_cmd output |
| 02-06 | `server/screen_capture.py` (NvFBC 10-bit) | want_10bit ctor + runtime_capability_state | ✓ VERIFIED | want_10bit kwarg at line 144; runtime_capability_state property at line 460-468 |
| 02-06 | `server/nvfbc/nvfbc_capture.c` | NVFBC_BUFFER_FORMAT_YUV420P10LE | ✓ VERIFIED | 9 YUV420P10LE references in C helper |
| 02-07 | `client/viewer.py` (QRhi) | QRhiWidget integration; VideoBlitWidget; Metal default + OpenGL fallback | ✓ VERIFIED | QRhiWidget import + VideoBlitWidget class + setApi(Metal) at line 158; --legacy-gl-blit escape hatch present |
| 02-07 | `client/shaders/video_blit.vert/.frag` + .qsb | BT.709 video-range shaders + baked binaries | ✓ VERIFIED | 4 files present (vert, frag, vert.qsb, frag.qsb); BT.709 constants 1.5748/1.1643 in frag per VALIDATION |
| 02-07 | `scripts/build_shaders.sh` | pyside6-qsb bake | ✓ VERIFIED | 1,876 bytes; executable; CI re-bakes + git diff --exit-code (.github/workflows/ci.yml:91) |
| 02-07 | `tests/client/test_viewer_qrhi_video_layer.py` | QRhi format tests | ✓ VERIFIED | 7,391 bytes; 7 tests per 02-07-SUMMARY |
| 02-08 | `client/video_decoder.py` (P010 assertion) | Format assertion + hw_backend property + no rgb24 hot-path | ✓ VERIFIED | line 14 docstring asserts p010le/yuv420p10le; line 172 hw_backend property; line 228 format check raises on Main10 silent fallback; structlog "video_decoder.p010_format_assertion_failed" event wired |
| 02-08 | `docs/build-pyav-macos.md` | FFmpeg 7.1+ link instructions | ✓ VERIFIED | 5,137 bytes |
| 02-09 | `client/viewer.py` (modifier triggers) | focusOutEvent + F9 panic + inputMethodEvent + KeyEvent lock bits | ✓ VERIFIED | reset_modifiers_requested signal at line 428; focusOutEvent at line 920; F9 wired in client/main_window.py:737 |
| 02-09 | `client/connection_supervisor.py` | first-post-auth KEY_RESET_MODIFIERS(reason='reconnect') | ✓ VERIFIED | reset hook in supervisor + client/protocol.py:339 send_reset_modifiers |
| 02-09 | `client/bookmarks.py` (per-bookmark swap_cmd_ctrl) | default ON Linux / OFF Mac | ✓ VERIFIED | swap_cmd_ctrl field present; default_swap_for_destination per WR-03 review note |
| 02-09 | `server/session_manager.py` (xset r off) | xset -display $DISPLAY r off | ✓ VERIFIED | line 377 ["xset", "-display", display, "r", "off"] |
| 02-09 | `tests/integration/test_modifier_stress.py` | focus-stress + reconnect-stress + held-chord | ✓ VERIFIED | 6,592 bytes |
| 02-10 | `server/mac_pen_injector.py` (PASS branch) OR `docs/release.md` (FAIL branch) | Either IOHIDUserDevice wrapper OR documented v1 limitation | ✓ VERIFIED (FAIL branch — planned outcome) | mac_pen_injector.py absent on disk; docs/release.md:8-72 documents D-07 FAIL outcome + INPUT-08 re-scope per planned D-07 contract; mac_input_injector.pen_event retains mouse-click fallback with one-time WARNING |
| 02-10 | `common/session_fsm.py::PenFSM` | out_of_proximity ↔ in_proximity, idempotent | ✓ VERIFIED | line 198 class PenFSM; tests/common/test_session_fsm_pen.py PASSES |
| 02-10 | `client/viewer.py` (proximity re-synth) | focusInEvent + showEvent → PenProximityMsg | ✓ VERIFIED | focusInEvent + showEvent handlers in viewer.py per 02-10-SUMMARY |
| 02-10 | `tests/server/test_mac_pen_injector.py` | FAIL-branch shape (3 tests, replaces Wave 0 xfails) | ✓ VERIFIED | 7,325 bytes; 3 tests per 02-10-SUMMARY |
| 02-11 | `tests/integration/test_crazy_hotkeys.py` | FLAME_CRITICAL_CHORDS loopback (in-process) | ✓ VERIFIED (in-process) | 10,824 bytes; covers 28 test IDs per 02-11-SUMMARY |
| 02-11 | `client/key_diagnostic.py` | "Wacom setup" tab + TCC status + deep-links | ✓ VERIFIED | line 389 addTab "Wacom setup"; line 33 import tcc_detect.read_tcc_status |
| 02-11 | `client/tcc_detect.py` | Read-only sqlite3 TCC.db reader | ✓ VERIFIED | 8,021 bytes; mode=ro per VALIDATION grep |
| 02-12 | `tools/wacom_quant_analysis.py` | Full impl (numpy + scipy interp1d + RMS + SVG) | ✓ VERIFIED | 198 lines; line 81 scipy.interpolate.interp1d; line 178 compute_rms; SVG output |
| 02-12 | `docs/release.md` | 4-cell matrix runbook + DXS latency table + spike outcome | ✓ VERIFIED (skeleton) / ⚠️ DEFERRED (results) | 13,424 bytes; runbook + tables + spike outcome present, BUT 10× `<DEFERRED — Randy to execute at DXS>` placeholders await human DXS execution |
| 02-12 | `tests/server/test_wacom_matrix_emission.py` | structlog event=wacom_matrix contract | ✓ VERIFIED | 4,752 bytes; emission schema tests (one local-env failure due to scipy missing in dev env, not Phase 2 gap) |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `client/viewer.py` | `server/input_injector.reset_modifiers` | KEY_RESET_MODIFIERS wire message | ✓ WIRED | viewer emits → protocol.send_reset_modifiers → server dispatcher → InputInjector.reset_modifiers (idempotent path) |
| `client/connection_supervisor.py` | first-post-auth KEY_RESET_MODIFIERS | reconnect hook | ✓ WIRED | client/session.py:271-273 connects reset_modifiers_requested signal; tests/client/test_protocol_modifier_wiring.py covers |
| `server/session_manager.py` | `xset -display $DISPLAY r off` | subprocess.run at session start | ✓ WIRED | line 377 |
| `tests/conftest.py` | `tests/smoke/fixtures/10bit_ramp.p010.bin` | ten_bit_ramp_frames fixture | ✓ WIRED | conftest provides ten_bit_ramp_bytes module-scope fixture |
| `.github/workflows/ci.yml` | `tests/smoke/test_ten_bit_pipeline.py` | pytest selector | ✓ WIRED | tests run by default pytest invocation; deselected only via marker |
| `pyproject.toml` | pytest markers | [tool.pytest.ini_options].markers | ✓ WIRED | flame_critical / wacom_hw / ten_bit_smoke / gpu declared |
| `server/bootstrap.py` | `server/capability_probe.py` | direct call at server startup | ✓ WIRED | imports + invokes probe_nvenc_main10 / probe_vt_main10 |
| `server/bootstrap.py` | `common.messages.ServerColorCaps` | ServerHelloMsg field population | ✓ WIRED | build_color_caps returns ServerColorCaps, populated on hello |
| `client/health_display.py` | `ServerHelloMsg.color_caps.negotiated_state` | parse + render badge | ✓ WIRED | render_color_badge consumes negotiated_state |
| `server/platform_backends.py` | `server/mac_video_encoder.py` | gated by IS_MACOS + _HAS_VT | ✓ WIRED | lines 65-83 import + _MAC_VIDEO_ENC_AVAILABLE flag |
| `server/mac_video_encoder.py` | `server/mac_screen_capture.py` | CVPixelBuffer format negotiation | ⚠️ PARTIAL | format constant referenced (kCVPixelFormatType_420YpCbCr10BiPlanarVideoRange) but CR-01: feed_frame discards captured bytes |
| `server/screen_capture.py` | `server/nvfbc/nvfbc_capture.c` | ctypes / pybind buffer format | ✓ WIRED | want_10bit kwarg threads through to NvFBC helper; NVFBC_BUFFER_FORMAT_YUV420P10LE flag |
| `server/video_encoder.py` | `server/screen_capture.py` | capture pixel format negotiation | ✓ WIRED | _color_caps + _build_ffmpeg_cmd dispatch on Main10 |
| `client/viewer.py` | `client/shaders/video_blit.frag.qsb` | QRhiGraphicsPipeline load | ✓ WIRED | _FRAG_QSB_NAME = "video_blit.frag.qsb" at line 78 |
| `tests/smoke/test_ten_bit_pipeline.py` | `client/video_decoder.py` | hw_backend + frame.format.name assertions | ✓ WIRED | cp.5 source-grep gate green |
| `client/viewer.py` | server PenFSM via PenProximityMsg | wire messages on focusIn + showEvent | ✓ WIRED | viewer focusIn/showEvent emit; common.session_fsm PenFSM consumes |
| `server/platform_backends.py` | `server/mac_input_injector.py` (FAIL branch) | composed InputInjector facade | ✓ WIRED (FAIL branch) | mac_pen_injector absent per planned D-07 FAIL; mac_input_injector.pen_event retains mouse-click fallback |
| `client/key_diagnostic.py` | `client/tcc_detect.py` | import read_tcc_status | ✓ WIRED | line 33 from client.tcc_detect import read_tcc_status; line 266 invokes |
| `docs/release.md` | `tools/wacom_quant_analysis.py` | per-release runbook instruction | ✓ WIRED | runbook step 7 invokes the script with --pass-threshold 0.01 |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `server/mac_video_encoder.py::feed_frame` | `p010_bytes` (input) → CVPixelBuffer (encoder input) | ScreenCaptureKit P010 surface (server/mac_screen_capture.py) → encoder dispatcher → feed_frame | NO — discarded at line 254 (`del p010_bytes`); empty CVPixelBuffer submitted to VTCompressionSessionEncodeFrame | ✗ HOLLOW (CR-01) |
| `client/viewer.py::VideoBlitWidget.feed_frame` | `y_bytes`, `uv_bytes` (P010 planes) | client/video_decoder.py decode_frame_planes → set on widget → render() | YES — decode_frame_planes returns 10-bit Y + UV planes; raises on Main10 silent fallback | ✓ FLOWING |
| `client/health_display.py::render_color_badge` | `negotiated_state` | ServerHelloMsg.color_caps.negotiated_state from build_color_caps probe | YES — probe_nvenc_main10 / probe_vt_main10 produce real capability flags from nvidia-smi / VTIsHardwareDecodeSupported | ✓ FLOWING |
| `client/key_diagnostic.py` Wacom tab | TCC status | client/tcc_detect.py read_tcc_status (read-only sqlite3 on TCC.db) | YES — real TCC DB read | ✓ FLOWING |
| `tools/wacom_quant_analysis.py` | client + server JSONL | structlog wacom_matrix events from real session capture | DEFERRED — JSONL files do not exist yet (DXS matrix not yet executed) | ⚠️ STATIC (awaits human DXS run) |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| 9-checkpoint pipeline test runs | `pytest tests/smoke/test_ten_bit_pipeline.py -v` | 6 passed, 2 skipped, 1 xfailed in 0.04s | ✓ PASS (6/9 automated GREEN; cp.1 acknowledged xfail; cp.8/9 manual-by-design) |
| Common + server suite passes | `pytest tests/common tests/server -q --ignore=test_pam_auth --ignore=test_wacom_matrix_emission` | 3617 passed, 99 skipped | ✓ PASS |
| Wacom analysis script imports + has CLI | `wc -l tools/wacom_quant_analysis.py; grep interp1d` | 198 lines; scipy.interpolate.interp1d at line 81; compute_rms at line 178 | ✓ PASS |
| Phase 2 message types present | grep KEY_RESET_MODIFIERS / TextCommitMsg / PenProximityMsg / ServerColorCaps in common/messages.py | 6 matches across required entities | ✓ PASS |
| Mac VT encoder declares Main10 + low-latency | grep VTCompressionSession / EnableLowLatencyRateControl / HEVC_Main10 in server/mac_video_encoder.py | All three present (lines 136, 148, 173) | ✓ PASS (config) / ✗ FAIL (data — see CR-01) |
| BT.709 shader excludes BT.2020 | grep 1.5748 / 1.1643 / BT.709 / BT.2020 in client/shaders/video_blit.frag | BT.709 constants present; BT.2020 absent per VALIDATION matrix | ✓ PASS |

### Requirements Coverage (24 IDs across 12 plans)

| Requirement | Source Plan(s) | Description | Status | Evidence |
|-------------|----------------|-------------|--------|----------|
| INPUT-01 | 02-01, 02-03, 02-09 | Table-driven keymap unit tests | ✓ SATISFIED | tests/common/test_keymap.py — ~3533 parametrized cases; QT_KEY_TO_MAC_VK + qt_key_to_linux_scancode covered |
| INPUT-02 | 02-02, 02-09 | Release-all-modifiers on QEvent::WindowDeactivate | ✓ SATISFIED | client/viewer.py focusOutEvent triggers reset; tests/integration/test_modifier_stress.py passes |
| INPUT-03 | 02-02, 02-03, 02-09 | Release-all-modifiers on reconnect | ✓ SATISFIED | client/connection_supervisor.py first-post-auth send; client/protocol.py:339 send_reset_modifiers |
| INPUT-04 | 02-01, 02-11 | Crazy Flame hotkey integration test | ✓ SATISFIED (in-process) / ? NEEDS HUMAN (real Rocky + real Mac server) | tests/integration/test_crazy_hotkeys.py 28 test IDs; real-server validation routed to human |
| INPUT-05 | 02-02, 02-03, 02-09 | International keyboard + dead-key handling (US/UK/DE/JP) | ✓ SATISFIED | TextCommitMsg via inputMethodEvent (no keycode synthesis); tests cover dead-key composition |
| INPUT-06 | 02-02, 02-03, 02-09 | Caps Lock state sync | ✓ SATISFIED | KeyEventMsg carries caps_lock_on/num_lock_on/scroll_lock_on bits; server auto-correct on mismatch |
| INPUT-07 | 02-03, 02-09 | Cmd ↔ Ctrl translation Mac client → Linux server | ✓ SATISFIED | swap_cmd_ctrl_for_linux_dest pure function; per-bookmark checkbox (default ON Linux, OFF Mac) per D-10 (caveat: WR-03 dialog UX issue noted but not goal-blocking) |
| INPUT-08 | 02-01, 02-10 | IOHIDUserDevice pen pressure injector for macOS server | ✓ SATISFIED (per planned D-07 FAIL branch) / ? NEEDS HUMAN (re-attempt with hardware) | docs/release.md:8-72 documents FAIL outcome + re-scope to v1 limitation per D-07 contract; mac_pen_injector.py absent (planned); Rocky remains the Flame-production path |
| INPUT-09 | 02-12 | Wacom hardware integration test | ? NEEDS HUMAN | docs/release.md 4-cell matrix runbook present; results table fully DEFERRED to DXS execution |
| INPUT-10 | 02-12 | Eraser + tablet-side button events round-trip | ? NEEDS HUMAN | Schema + structlog wiring + tools complete; physical eraser/button verification pending DXS |
| INPUT-11 | 02-02, 02-10, 02-12 | Proximity events delivered without loss | ✓ SATISFIED (FSM/wire) / ? NEEDS HUMAN (hardware) | PenProximityMsg + PenFSM + viewer focusIn/showEvent re-synth; physical proximity cycle pending DXS |
| INPUT-12 | 02-12 | Pressure curve preservation (no quantization artifacts) | ? NEEDS HUMAN | tools/wacom_quant_analysis.py implements RMS gate (<1%); per-cell RMS values DEFERRED to DXS run |
| VIDEO-01 | 02-02, 02-06, 02-07, 02-08 | 10-bit end-to-end pipeline verified | ⚠️ PARTIAL | Wire and Linux path verified; Mac-server path BROKEN by CR-01; Linux path cp.1 still XFAIL |
| VIDEO-02 | 02-01, 02-06, 02-07, 02-08 | Bit-exact end-to-end test pattern as CI fixture | ⚠️ PARTIAL | Fixture committed (10bit_ramp.p010.bin + reference JSON); 6/9 checkpoints automated GREEN; cp.1 stale xfail; cp.8/9 manual-by-design |
| VIDEO-03 | 02-02, 02-04, 02-05, 02-06 | HEVC Main10 via hevc_nvenc on Rocky 9 | ✓ SATISFIED | server/video_encoder.py p010le + -profile:v main10 path; cp.2/3/4 PASS; capability probe gates advertisement |
| VIDEO-04 | 02-05, 02-08 | Direct VTCompressionSession via PyObjC on macOS | ⚠️ HOLLOW | Wrapper exists with all configuration correct (HEVC_Main10_AutoLevel, EnableLowLatencyRateControl, AllowFrameReordering=False); CR-01: encoder receives empty buffers — wired but functionally broken |
| VIDEO-05 | 02-02, 02-04, 02-05, 02-06 | 4:2:0 default, 4:2:2 opt-in | ✓ SATISFIED | enable_422 settings flag gates Main42210; default Main10; capability probe HWEncoder.supports_422 surfaced |
| VIDEO-06 | 02-06 | IDR-on-drop recovery (10-bit path) | ✓ SATISFIED | Phase 1 STAB-04 wired; 02-06 confirms 10-bit variant covered |
| VIDEO-07 | 02-05, 02-06 | Encoder reconfigure without full pipeline restart | ✓ SATISFIED | VideoEncoder.reconfigure(new_bitrate_bps, new_fps=None) added; delegates to MacVideoEncoder.reconfigure on VT path |
| VIDEO-08 | 02-04, 02-05 | ScreenCaptureKit .hdrLocalDisplay + 420YpCbCr10BiPlanarVideoRange | ✓ SATISFIED | server/mac_screen_capture.py:103,107,236,377-401 |
| VIDEO-09 | 02-02, 02-04, 02-06 | NvFBC primary / mss fallback dispatch | ✓ SATISFIED | server/screen_capture.py runtime_capability_state confirmed/degraded/not_supported per build_color_caps |
| VIDEO-10 | 02-05, 02-06 | 60fps native LAN; 30fps WAN fallback | ✓ SATISFIED | ExpectedFrameRate property in MacVideoEncoder (line 183); FFmpeg side parametrized; quality-slider knobs intact |
| VIDEO-11 | 02-05, 02-06, 02-12 | Sub-20ms LAN input-to-photon; CI gate keeps it honest | ✓ SATISFIED (CI synthetic gate) / ? NEEDS HUMAN (DXS hardware p99 measurement) | Phase 1 D-08/D-09 synthetic p99 < 25ms gate preserved; real-hardware p99 measurement DEFERRED to DXS |
| VIDEO-12 | 02-05, 02-08 | PyAV client decode against system FFmpeg 7.1+ | ✓ SATISFIED | docs/build-pyav-macos.md documents the build requirement; client/video_decoder.py uses system FFmpeg path |

**Coverage:** 24/24 requirement IDs from PLAN frontmatter accounted for in REQUIREMENTS.md and traced to artifacts. ROADMAP.md says Phase 2 owns INPUT-01..12 + VIDEO-01..12 — all 24 declared in plan frontmatter, none orphaned.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `server/mac_video_encoder.py` | 250-254 | TODO + `del p010_bytes` discards captured frame data | 🛑 BLOCKER | Mac-server video encode submits empty CVPixelBuffer; encoded NALs are valid Main10 frames of UB heap memory whenever production dispatch picks the direct-VT path. Capability badge advertises "10-bit confirmed" while pixels are stale RAM. CR-01 in 02-REVIEW.md. |
| `tests/smoke/test_ten_bit_pipeline.py` | 65-70 | `@pytest.mark.xfail` + `pytest.fail("Wave 2 owner wires NvFBC P010 surface...")` | ⚠️ WARNING | cp.1 deferred to "Wave 4 / Linux GPU runner" but capture-side P010 plumbing already exists in server/screen_capture.py (want_10bit, runtime_capability_state) and server/nvfbc/nvfbc_capture.c (NVFBC_BUFFER_FORMAT_YUV420P10LE). Stale TODO; should be wired and asserted. |
| `client/bookmarks.py` | 151-158, 197-218 | `_save()` non-atomic write + no locking | ⚠️ WARNING | WR-01 in REVIEW.md; not goal-blocking but multi-machine data-loss risk per Randy's documented workflow |
| `client/protocol.py` | 625, 769 | `asyncio.get_event_loop().create_future()` deprecated in 3.12+ | ⚠️ WARNING | WR-02; will break on Python 3.14 |
| `client/main_window.py` | 102-106 | `setChecked(True)` swap_cmd_ctrl always defaults True regardless of destination_kind | ⚠️ WARNING | WR-03; Mac-server users get silent swap-on behavior on first connect |
| `client/protocol.py` | 24-32, `client/session.py` | Unused imports (HealthPong, JPEG_HEADER_SIZE, json, time, asdict) | ℹ️ INFO | IN-01; should be caught by ruff F401 |
| `server/mac_screen_capture.py` | 396-402 | `hdrLocalDisplay_set_failed` warns but doesn't downgrade `runtime_capability_state` | ⚠️ WARNING | WR-06; symmetry gap with Linux ScreenCapture; honesty contract gap |

### Human Verification Required

#### 1. DXS 4-cell Wacom hardware matrix

**Test:** Execute the 4-cell matrix per docs/release.md Phase 2 Wacom matrix ritual: Intuos Pro Large + Cintiq Pro 24 × macOS Sonoma + Sequoia. For each cell run the D-17 6-step protocol (pressure ramp / eraser flip / tilt / proximity cycle / side-buttons / reconnect mid-stroke), then run `tools/wacom_quant_analysis.py --cell <name> --pass-threshold 0.01` against captured client + server JSONL. Replace 10× `<DEFERRED — Randy to execute at DXS>` placeholders in docs/release.md results table with real RMS values + recorded video links.
**Expected:** All 4 cells pass all 6 automated steps + RMS < 1% per cell + Flame artist qualitative sign-off on the Cintiq Pro 24 + Sequoia cell.
**Why human:** No autonomous executor / GHA runner can drive a real Wacom Pro stylus on real Cintiq hardware. Plan 02-12 has `autonomous: false`. INPUT-09 / INPUT-10 / INPUT-11 / INPUT-12 hardware-verification leg awaits this checkpoint.

#### 2. DXS pre/post-Phase-2 input-to-photon latency comparison (D-21 / VIDEO-11)

**Test:** On a DXS Mac client + Rocky Flame workstation server with real Wacom + Cintiq attached (same Tailscale tailnet), capture p50/p95/p99 input-to-photon latency at HEAD-of-Phase-1-verification and at HEAD-of-Phase-2 (3 trial sessions each, ~60s of typical Flame interaction). Replace 9× `<DEFERRED — Randy to execute at DXS>` placeholders in docs/release.md latency results table.
**Expected:** Post-Phase-2 p99 ≤ pre-Phase-2 p99 × 1.15 (no >15% regression). Bonus: post-Phase-2 p99 < 20ms.
**Why human:** Real-hardware end-to-end measurement on a real Tailscale LAN with real input devices; CI's synthetic p99 < 25ms gate (Phase 1 D-08/D-09) cannot prove this on its own. Plan 02-12 Task 3 explicitly checkpoint:human-verify.

#### 3. INPUT-08 IOHIDUserDevice spike re-attempt

**Test:** On a development workstation with `pyobjc-framework-IOKit>=11.0`, real Wacom hardware, Photoshop / Preview / NSView test app installed, and operator available: register a virtual Wacom HID tablet via IOHIDUserDeviceCreate; draw a complete pen stroke; verify `NSEvent.pressure > 0` in Photoshop / Preview / NSView app.
**Expected:** Either (a) PASS — productionize server/mac_pen_injector.py per 02-10 PASS-branch sketch and re-run the Wacom matrix; OR (b) re-affirm FAIL — leave INPUT-08 as documented v1 limitation.
**Why human:** Per docs/release.md, the Phase 2 autonomous executor cannot satisfy the D-08 PASS bar (no pyobjc-framework-IOKit in sandbox; no Photoshop / Preview / NSView app; no real Wacom). Currently shipped per planned D-07 FAIL branch — Mac-server pen pressure stays mouse-click; Rocky remains the Flame-production path.

#### 4. Visual 10-bit color confirmation on MBP XDR (D-01 cp.8)

**Test:** Connect Mac client (MBP XDR or Pro Display XDR) to a Rocky 9 Flame server. Display the 10-bit ramp fixture (`tests/smoke/fixtures/10bit_ramp.p010.bin`) full-screen via the live decode + QRhi blit path. Visually verify the gradient shows no banding (no posterization, smooth transition through the bottom 2 bits).
**Expected:** Smooth gradient on MBP XDR Reference Mode; no visible banding when an artist eyeballs the ramp.
**Why human:** Bottom 2 bits of luma are below the threshold of automated readback through the Metal blit; D-01 explicitly designates cp.8 as a manual-verified-once visual gate. Skipped in CI by design.

#### 5. Crazy-hotkeys against real Rocky 9 Flame server AND real Mac server

**Test:** Run `pytest tests/integration/test_crazy_hotkeys.py -m flame_critical` against a real Rocky 9 Flame workstation (uinput injection) AND against a real macOS server (CGEventPost), both with Flame open. Confirm every FLAME_CRITICAL_CHORDS chord (Cmd↔Ctrl swap, Caps Lock state, US/UK/DE/JP dead-keys) lands correctly in a Flame paint session.
**Expected:** Zero hotkey mangling on both servers.
**Why human:** ROADMAP success criterion #2 demands "real Rocky server AND real Mac server" — in-process loopback validates the wire path but not the server-side injection at the OS level (uinput / CGEventPost) inside a real Flame instance.

### Gaps Summary

**The Phase 2 goal — 10-bit end-to-end with no silent downgrades, full-fidelity Wacom, zero modifier mangling — is mostly achieved on the Linux-server path and well-architected throughout, BUT it has one critical correctness bug and several explicit human-verification checkpoints.**

**1. CR-01 (BLOCKER for the Mac-server path):** server/mac_video_encoder.py::feed_frame discards captured P010 plane bytes (`del p010_bytes` at line 254 with documented TODO). When the production dispatcher picks the direct VTCompressionSession path (the documented production behavior whenever pyobjc-framework-VideoToolbox imports successfully — which it does on every macOS server install per requirements-server.txt), the encoder submits empty CVPixelBuffer for every frame. The on-the-wire HEVC NALs are valid Main10 frames containing UB heap memory; the client decodes them as valid P010 and the QRhi blit displays them as banded garbage. The capability badge concurrently advertises "10-bit confirmed". This is the canonical "wired-but-broken" anti-pattern Phase 2 was meant to eliminate, not introduce. **Fix:** either (a) implement the plane copy per the REVIEW.md fix snippet (CVPixelBufferLockBaseAddress + ctypes.memmove for Y + UV planes), or (b) flip `_MAC_VIDEO_ENC_AVAILABLE = False` in platform_backends.py until plane copy lands so the dispatcher deterministically falls back to the Phase 1 FFmpeg `hevc_videotoolbox` subprocess path. Option (a) is preferred (the whole point of D-04 was the 5-8ms savings).

**2. cp.1 stale xfail:** The Linux NvFBC P010 capture-surface checkpoint still calls `pytest.fail("Wave 2 owner wires NvFBC P010 surface and asserts format")` though the underlying capture plumbing exists in `server/screen_capture.py` (want_10bit ctor + runtime_capability_state property) and `server/nvfbc/nvfbc_capture.c` (NVFBC_BUFFER_FORMAT_YUV420P10LE flag). Wire the test to assert on these and remove the xfail.

**3. Five human-verification checkpoints** route INPUT-09/-10/-11/-12 hardware fidelity, VIDEO-11 real-hardware latency, INPUT-08 spike re-attempt, D-01 cp.8 visual confirmation, and ROADMAP success criterion #2 real-server validation to Randy. None of these can be closed without DXS lab time. They are not gaps — they are explicit phase-design checkpoints that require physical hardware.

**Phase 2 cannot be signed off "passed" until CR-01 is closed AND the human-verification items have been executed.** With CR-01 fixed and the human checkpoints landed, the goal IS achieved. The architectural and test scaffolding is strong: 3,617 tests pass; the 9-checkpoint fixture has 6/9 automated GREEN with documented reasons for the remaining 3; PenFSM, modifier discipline, capability probes, BT.709 shader, exhaustive keymap matrix, and TCC-aware diagnostic UI all land cleanly.

---

_Verified: 2026-04-19_
_Verifier: Claude (gsd-verifier)_
