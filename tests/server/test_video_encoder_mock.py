"""STAB-05 / D-02 — VideoEncoder with ffmpeg subprocess mocked.

Guards the D-02 mock boundary: no real ffmpeg invocation anywhere in this file.
The VideoEncoder's ``_start_ffmpeg`` path calls ``subprocess.Popen`` exactly
once per start; we patch that symbol at the ``server.video_encoder`` module
boundary so the reader thread sees a fake process whose ``stdout.read`` returns
``b""`` (causing the reader loop to exit immediately) and whose ``stdin`` is a
``MagicMock`` that swallows writes.

Plan 09 / D-02 boundary rationale:
- CI macos-14 runners have a brew'd ffmpeg, but invoking it in a unit test is
  slow, flaky (ffmpeg version skew → arg rejection), and leaks process handles
  when the test is interrupted. Mock-at-the-subprocess-boundary keeps every
  VideoEncoder test deterministic in < 100 ms.
- Plan 01 (fake_encoder fixture in tests/conftest.py) uses an in-Python
  ``FakeEncoder`` stand-in for assertions above the encoder layer; THIS file
  exercises the real VideoEncoder class with just the subprocess interface
  stubbed so Plan 10's EncoderLifecycle extraction has a regression gate on
  the actual module under test.

Do NOT:
- Require a real ffmpeg binary — mock boundary per D-02.
- Assert on emitted encoded-frame bytes — the mock returns empty.
- Rely on detect_encoders() — we pass an empty available_encoders dict so
  the encoder falls through to the libx264 absolute-fallback path.
"""
from __future__ import annotations

from unittest import mock

import pytest

from common.messages import QualitySettings


@pytest.fixture
def mock_popen(monkeypatch):
    """Mock subprocess.Popen for every VideoEncoder invocation.

    Returns the bound MagicMock process so tests can assert on stdin writes
    or poll behavior if they need to. Monkeypatched at the ``subprocess``
    module level — ``server.video_encoder.subprocess.Popen`` and
    ``subprocess.Popen`` reference the same attribute, so this covers both
    the encoder's start path and detect_encoders' ``subprocess.run`` path
    would NOT be touched (run is left alone) — callers should pass an empty
    ``available_encoders`` to avoid triggering detect_encoders.
    """
    fake_proc = mock.MagicMock()
    fake_proc.stdin = mock.MagicMock()
    fake_proc.stdout = mock.MagicMock()
    # Empty read terminates the reader thread's loop cleanly.
    fake_proc.stdout.read.return_value = b""
    fake_proc.poll.return_value = None
    fake_proc.returncode = None
    fake_proc.wait.return_value = 0

    def _fake_popen(*a, **kw):
        return fake_proc

    monkeypatch.setattr("subprocess.Popen", _fake_popen)
    monkeypatch.setattr("server.video_encoder.subprocess.Popen", _fake_popen)
    return fake_proc


@pytest.fixture
def empty_available_encoders():
    """Empty encoder-capability map — VideoEncoder falls through to the
    absolute libx264 software fallback without calling detect_encoders."""
    return {"h264": [], "h265": [], "av1": []}


def test_encoder_instantiates_without_real_ffmpeg(mock_popen, empty_available_encoders):
    """Constructor must not require a real ffmpeg on the runner.

    D-02 boundary proof: VideoEncoder.__init__ does not spawn a subprocess; it
    only records settings. So this test passes even if Popen is un-patched —
    but the fixture is present to prove the mock is installed before anything
    later in the session triggers a real ffmpeg call.
    """
    from server.video_encoder import VideoEncoder

    settings = QualitySettings()
    enc = VideoEncoder(1920, 1080, settings,
                       available_encoders=empty_available_encoders)
    assert enc is not None
    assert enc.width == 1920
    assert enc.height == 1080
    # Process not started until .start() is called.
    assert enc._process is None
    assert enc._running is False


def test_encoder_start_invokes_subprocess(mock_popen, empty_available_encoders):
    """D-02 — start() spawns the mocked process; no real ffmpeg invoked."""
    from server.video_encoder import VideoEncoder

    settings = QualitySettings()
    enc = VideoEncoder(1920, 1080, settings,
                       available_encoders=empty_available_encoders)
    frames: list[tuple[bytes, bool]] = []

    def on_frame(data: bytes, is_kf: bool):
        frames.append((data, is_kf))

    try:
        enc.start(on_frame)
        # Reader thread picks up the fake stdout.read()==b"" and exits
        # immediately; give it a moment to drain.
        import time
        time.sleep(0.05)
        # Process is set (mock), reader thread was created
        assert enc._process is mock_popen
        assert enc._running is True
    finally:
        try:
            enc.stop()
        except Exception:
            pass
    # No real encoded frames because the mocked stdout was empty — assert
    # the callback was never invoked (proves the mock boundary held).
    assert frames == []


def test_encoder_request_keyframe_is_callable(mock_popen, empty_available_encoders):
    """Plan 01's FakeEncoder (tests/conftest.py) assumed request_keyframe()
    exists and is safe to call. Real VideoEncoder exposes it without crashing
    — guard against any future refactor that renames or removes it."""
    from server.video_encoder import VideoEncoder

    settings = QualitySettings()
    enc = VideoEncoder(1920, 1080, settings,
                       available_encoders=empty_available_encoders)

    # Early call (before start) must be a no-op — internally guarded by
    # the `if not self._running` check at the top of request_keyframe.
    enc.request_keyframe()

    # After start, request_keyframe() restarts the encoder subprocess —
    # Popen is called a second time through our mock; no real ffmpeg runs.
    def _noop(_data, _is_kf):
        pass

    try:
        enc.start(_noop)
        import time
        time.sleep(0.05)
        # Must not raise
        enc.request_keyframe()
        # After request_keyframe, encoder is still running with a (mocked) process
        assert enc._running is True
        assert enc._process is mock_popen
    finally:
        try:
            enc.stop()
        except Exception:
            pass


def test_encoder_stop_cleans_up_without_raising(mock_popen, empty_available_encoders):
    """stop() must succeed even when the subprocess is entirely mocked.

    Guards against a refactor that adds a `.wait()` or `.kill()` path whose
    interaction with MagicMock becomes awkward (e.g. returning non-None from
    poll()). Plan 10's extraction of EncoderLifecycle must preserve this
    teardown contract."""
    from server.video_encoder import VideoEncoder

    settings = QualitySettings()
    enc = VideoEncoder(1920, 1080, settings,
                       available_encoders=empty_available_encoders)

    def _noop(_data, _is_kf):
        pass

    enc.start(_noop)
    # Must not raise even with the fully-mocked subprocess
    enc.stop()
    assert enc._running is False
    assert enc._process is None


def test_encoder_feed_frame_is_noop_when_stopped(mock_popen, empty_available_encoders):
    """feed_frame() on a stopped/never-started encoder is a silent no-op —
    guards against a regression where a caller feeds frames after teardown
    and triggers a BrokenPipeError against a closed stdin."""
    from server.video_encoder import VideoEncoder

    settings = QualitySettings()
    enc = VideoEncoder(1920, 1080, settings,
                       available_encoders=empty_available_encoders)

    # Pre-start: no process exists, feed is a no-op (early return)
    enc.feed_frame(b"\x00" * 64)

    def _noop(_data, _is_kf):
        pass

    enc.start(_noop)
    # Post-start: feed writes to mocked stdin
    enc.feed_frame(b"\xff" * 64)
    # stdin.write was called at least once
    assert mock_popen.stdin.write.call_count >= 1

    enc.stop()
    # Post-stop: another feed is a no-op (process is None, guards against crash)
    enc.feed_frame(b"\x00" * 64)
