"""Client application bootstrap — QApplication + CLI + main().

Extracted from client/main.py (STAB-05 / D-12). Entry point wiring
(argparse, logging config, QApplication + Fusion style, macOS bundle
tweaks) lives here. MainWindow construction and show() is still
performed here, but the class itself has moved to client/main_window.py.
"""

from __future__ import annotations

import argparse
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from client import theme
from client.main_window import MainWindow
from common.logging import configure as _configure_logging


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Teraguchi Remote Desktop Client")
    parser.add_argument("--host", default="", help="Server hostname or IP")
    parser.add_argument("--port", type=int, default=443)
    parser.add_argument("--username", "-u", default="")
    parser.add_argument("--password", "-p", default="")
    parser.add_argument(
        "--broker", action="store_true",
        help="Connect via broker instead of direct",
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    return parser.parse_args(argv)


def main() -> None:
    """Boot the Teraguchi client."""
    args = _parse_args()

    # OBS-01: route all logging (stdlib + structlog) through the canonical
    # processor chain. phase="client" is bound into contextvars so every
    # emit carries it.
    _configure_logging(phase="client", verbose=args.verbose)

    # macOS: don't swap Control/Meta so physical Control = Control_L on Linux.
    if sys.platform == "darwin":
        QApplication.setAttribute(Qt.AA_MacDontSwapCtrlAndMeta, True)

    app = QApplication(sys.argv)
    app.setApplicationName("Teraguchi")
    app.setApplicationDisplayName("Teraguchi")
    app.setOrganizationName("Teraguchi")
    app.setDesktopFileName("teraguchi")
    app.setStyle("Fusion")

    # macOS: override process name so dock/menu bar shows "Teraguchi".
    if sys.platform == "darwin":
        try:
            from Foundation import NSBundle  # type: ignore
            bundle = NSBundle.mainBundle()
            info = bundle.localizedInfoDictionary() or bundle.infoDictionary()
            if info:
                info["CFBundleName"] = "Teraguchi"
                info["CFBundleDisplayName"] = "Teraguchi"
        except ImportError:
            pass

    app.setStyleSheet(theme.generate_stylesheet())

    window = MainWindow(
        initial_host=args.host,
        initial_port=args.port,
        initial_user=args.username,
        initial_pass=args.password,
        initial_mode="broker" if args.broker else "direct",
    )
    window.resize(1440, 900)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
