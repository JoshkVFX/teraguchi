"""
Platform backend dispatch for the Teraguchi server.

The server has three backend contracts that differ by OS:

    * screen capture   (Linux: mss/NvFBC/XDamage, macOS: ScreenCaptureKit)
    * input injection  (Linux: uinput/XTest,      macOS: CoreGraphics)
    * clipboard sync   (Linux: xclip/xsel,        macOS: NSPasteboard)

Rather than scattering ``if sys.platform == "darwin"`` checks through
``server/main.py``, we keep the dispatch here and re-export the correct
classes for the current platform. ``server/main.py`` imports the public
names from this module and the rest of the session runtime is
platform-agnostic.

On an unsupported platform we re-export the Linux classes so static
analysis still works; runtime behavior will of course be broken.
"""

import logging
import sys

logger = logging.getLogger(__name__)

IS_MACOS = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")

# ----------------------------------------------------------------------
# Screen capture
# ----------------------------------------------------------------------

if IS_MACOS:
    from server.mac_screen_capture import MacScreenCapture as ScreenCapture  # noqa: F401
    logger.info("platform_backends: using MacScreenCapture (ScreenCaptureKit)")
else:
    from server.screen_capture import ScreenCapture  # noqa: F401

# ----------------------------------------------------------------------
# Input injection
# ----------------------------------------------------------------------

if IS_MACOS:
    from server.mac_input_injector import MacInputInjector as InputInjector  # noqa: F401
    # On macOS there is no Xvfb / XTest analogue — the virtual-display
    # injector is stubbed to the same class as the physical one so the
    # session runtime's "virtual vs physical" branch still compiles.
    XTestInputInjector = InputInjector  # type: ignore
    logger.info("platform_backends: using MacInputInjector (CoreGraphics)")
else:
    from server.input_injector import InputInjector  # noqa: F401
    from server.xtest_injector import XTestInputInjector  # noqa: F401

# ----------------------------------------------------------------------
# Video encode (Phase 2 D-04 / VIDEO-04)
# ----------------------------------------------------------------------
#
# When the macOS server has pyobjc-framework-VideoToolbox installed,
# the Mac path prefers the direct VTCompressionSession wrapper in
# server.mac_video_encoder (saves 5-8ms/frame per WWDC21 session 10158
# vs. the FFmpeg subprocess hop). Otherwise we fall back to the Phase 1
# FFmpeg ``hevc_videotoolbox`` path documented in server/video_encoder.py.
#
# server.video_encoder.VideoEncoder.start() reads this flag once at
# session creation; do not flip it at runtime.
_MAC_VIDEO_ENC_AVAILABLE: bool = False
if IS_MACOS:
    try:
        from server.mac_video_encoder import _HAS_VT as _MAC_VIDEO_ENC_AVAILABLE  # noqa: F401
        if _MAC_VIDEO_ENC_AVAILABLE:
            logger.info(
                "platform_backends: MacVideoEncoder available "
                "(VTCompressionSession direct path)"
            )
        else:
            logger.warning(
                "platform_backends.mac_video_encoder_pyobjc_missing — "
                "falling back to FFmpeg hevc_videotoolbox subprocess path"
            )
    except Exception as _e:
        _MAC_VIDEO_ENC_AVAILABLE = False
        logger.warning(
            "platform_backends.mac_video_encoder_unavailable: %s", _e
        )

# ----------------------------------------------------------------------
# Clipboard
# ----------------------------------------------------------------------

if IS_MACOS:
    from server.mac_clipboard import MacClipboardSync as ClipboardSync  # noqa: F401
    logger.info("platform_backends: using MacClipboardSync (NSPasteboard)")
else:
    from server.clipboard import ClipboardSync  # noqa: F401
