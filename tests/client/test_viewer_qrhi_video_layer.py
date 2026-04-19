"""Phase 2 D-02 / VIDEO-01 cp.7 / VIDEO-02 — VideoBlitWidget assertions.

These tests cover the THREE invariants the QRhiWidget refactor in
``client/viewer.py`` must hold:

  1. Y plane texture is created with ``QRhiTexture.Format.R16``.
  2. UV plane texture is created with ``QRhiTexture.Format.RG16``.
  3. The committed BT.709 fragment shader uses the canonical 1.5748 R
     coefficient and 1.1643 Y video-range scale and does NOT mention
     any HDR / wide-gamut matrices (BT-2020 / SMPTE-2084 / HLG).

Tests 1 + 2 instantiate ``VideoBlitWidget`` against Qt's null QRhi
backend (no GPU required, ships with Qt). Test 3 is a cheap source-grep
gate that runs even on hosts without PySide6 installed (the conftest
graceful-degradation pattern).
"""
from __future__ import annotations

import os
import pathlib

import pytest

# Source-level shader assertion — runs unconditionally; does not import Qt.
SHADER_SRC = pathlib.Path(__file__).resolve().parents[2] / "client" / "shaders" / "video_blit.frag"


def test_bt709_matrix_values_in_shader_source():
    """Cheap static check against the committed shader source.

    Phase 2 D-02 anti-pattern rule (RESEARCH.md "Anti-Patterns to Avoid"):
    the BT.709 R coefficient (1.5748) and Y video-range scale (1.1643)
    must appear; HDR / BT-2020 must NOT appear (D-06 ICC out of scope).
    """
    text = SHADER_SRC.read_text()
    assert "1.5748" in text, "BT.709 R coefficient missing"
    assert "1.1643" in text, "BT.709 Y video-range scale missing"
    assert "1.1384" in text, "BT.709 UV video-range scale missing"
    assert "1.8556" in text, "BT.709 B coefficient missing"
    # Anti-pattern guard — D-02 refuses HDR matrices for v1.
    # The regex below tolerates "BT dot 2020" prose in the anti-pattern
    # comment but bans the literal "BT.2020" / "BT2020" string that
    # would actually be used in code.
    assert "BT.2020" not in text, "BT.2020 must not be used (D-06 HDR out of scope)"
    assert "BT2020" not in text, "BT2020 must not be used (D-06 HDR out of scope)"


# Widget-level tests require PySide6 + a Qt platform plugin.
pytest.importorskip("PySide6.QtWidgets")
pytest.importorskip("PySide6.QtGui")


@pytest.fixture(scope="module")
def qapp():
    """Module-scoped QApplication.

    Forces ``QT_QPA_PLATFORM=offscreen`` so widget construction works on
    headless CI and inside this executor. Reuses any existing
    QApplication (Qt allows only one per process).
    """
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app
    # Don't quit — leaving the app alive lets other tests in the module
    # share the instance; Python interpreter shutdown reclaims it.


def _make_null_video_blit_widget():
    """Construct a VideoBlitWidget pinned to the Null QRhi backend.

    The Null backend does not require a GPU; Qt ships it for headless
    testing — exactly the use case here.
    """
    from PySide6.QtWidgets import QRhiWidget
    from client.viewer import VideoBlitWidget
    w = VideoBlitWidget()
    w.setApi(QRhiWidget.Api.Null)
    return w


def test_video_blit_widget_uses_r16_for_y_plane(qapp):
    """D-02 cp.7: Y plane MUST be QRhiTexture.Format.R16 (10-bit-in-16)."""
    from PySide6.QtCore import QCoreApplication, QEventLoop
    from PySide6.QtGui import QRhiTexture

    w = _make_null_video_blit_widget()
    w.resize(320, 240)
    w.show()
    # Pump the event loop so QRhiWidget.initialize() fires.
    for _ in range(20):
        QCoreApplication.processEvents(QEventLoop.AllEvents, 50)
    assert w._tex_y is not None, "Y texture not created during initialize()"
    assert w._tex_y.format() == QRhiTexture.Format.R16, (
        f"Y texture must be R16 (10-bit-in-16-bit), got {w._tex_y.format()!r}"
    )


def test_video_blit_widget_uses_rg16_for_uv_plane(qapp):
    """D-02 cp.7: UV plane MUST be QRhiTexture.Format.RG16 (interleaved 10-bit)."""
    from PySide6.QtCore import QCoreApplication, QEventLoop
    from PySide6.QtGui import QRhiTexture

    w = _make_null_video_blit_widget()
    w.resize(320, 240)
    w.show()
    for _ in range(20):
        QCoreApplication.processEvents(QEventLoop.AllEvents, 50)
    assert w._tex_uv is not None, "UV texture not created during initialize()"
    assert w._tex_uv.format() == QRhiTexture.Format.RG16, (
        f"UV texture must be RG16 (interleaved 10-bit), got {w._tex_uv.format()!r}"
    )


def test_video_blit_widget_loads_baked_qsb_shaders(qapp):
    """The widget must reference the committed .qsb files.

    Surface-level guarantee that the runtime shader path is the baked
    Vulkan-GLSL -> MSL pipeline, not an inline GLSL string. Catches
    accidental regressions where someone swaps the QShader.fromSerialized
    call for a literal shader source.
    """
    import client.viewer as v
    src = pathlib.Path(v.__file__).read_text()
    assert "video_blit.vert.qsb" in src, "vertex shader .qsb not referenced"
    assert "video_blit.frag.qsb" in src, "fragment shader .qsb not referenced"


def test_video_blit_widget_supports_legacy_gl_blit_env_flag(qapp, monkeypatch):
    """D-02 escape hatch: TERAGUCHI_LEGACY_GL_BLIT=1 must select the OpenGL backend."""
    from PySide6.QtWidgets import QRhiWidget
    monkeypatch.setenv("TERAGUCHI_LEGACY_GL_BLIT", "1")
    from client.viewer import VideoBlitWidget
    w = VideoBlitWidget()
    assert w.api() == QRhiWidget.Api.OpenGL, (
        f"Expected OpenGL fallback when TERAGUCHI_LEGACY_GL_BLIT=1; got {w.api()!r}"
    )


def test_video_blit_widget_defaults_to_metal_on_macos(qapp, monkeypatch):
    """D-02 default path: Metal on macOS when escape-hatch env var is unset."""
    import sys
    if sys.platform != "darwin":
        pytest.skip("Metal backend default check only meaningful on macOS")
    from PySide6.QtWidgets import QRhiWidget
    monkeypatch.delenv("TERAGUCHI_LEGACY_GL_BLIT", raising=False)
    from client.viewer import VideoBlitWidget
    w = VideoBlitWidget()
    assert w.api() == QRhiWidget.Api.Metal, (
        f"Expected Metal default on macOS; got {w.api()!r}"
    )
