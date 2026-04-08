#!/usr/bin/env python3
"""
Build script for packaging the Teragucci client as a standalone application.

Usage:
    python build_client.py

Creates a standalone executable in dist/Teragucci/ that can be distributed
to Mac and Windows users without requiring a Python installation.
"""

import platform
import subprocess
import sys

APP_NAME = "Teragucci"
MAIN_SCRIPT = "client/main.py"


def build():
    system = platform.system()
    print(f"Building Teragucci client for {system}...")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", APP_NAME,
        "--windowed",       # No console window
        "--onedir",         # Create a directory (faster startup than onefile)
        "--noconfirm",      # Overwrite without asking
        "--clean",
        # Include required packages
        "--hidden-import", "websockets",
        "--hidden-import", "PySide6.QtCore",
        "--hidden-import", "PySide6.QtGui",
        "--hidden-import", "PySide6.QtWidgets",
        # Collect all of PySide6's data files (plugins, etc.)
        "--collect-all", "PySide6",
        # Add our modules
        "--add-data", f"common{':' if system != 'Windows' else ';'}common",
        MAIN_SCRIPT,
    ]

    if system == "Darwin":
        cmd.extend([
            "--osx-bundle-identifier", "com.teragucci.client",
        ])

    print("Running:", " ".join(cmd))
    result = subprocess.run(cmd)

    if result.returncode == 0:
        print(f"\nBuild successful! Output in dist/{APP_NAME}/")
        if system == "Darwin":
            print(f"macOS app bundle: dist/{APP_NAME}.app")
    else:
        print(f"\nBuild failed with code {result.returncode}")
        sys.exit(1)


if __name__ == "__main__":
    build()
