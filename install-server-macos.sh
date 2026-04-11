#!/usr/bin/env bash
#
# Teraguchi Server Installer (macOS)
#
# Mac-native counterpart to install-server.sh. Instead of uinput / PAM /
# systemd / Xvfb, the macOS server runs as a LaunchAgent in the logged-in
# user's GUI session and uses ScreenCaptureKit + CoreGraphics +
# NSPasteboard + VideoToolbox.
#
# Usage:
#   bash install-server-macos.sh            # full install
#   bash install-server-macos.sh --no-agent # skip LaunchAgent install
#   bash install-server-macos.sh --dev      # run from repo, skip copy
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="${HOME}/Library/Application Support/Teraguchi"
VENV_DIR="$INSTALL_DIR/.venv"
LOG_DIR="${HOME}/Library/Logs/Teraguchi"
AGENT_LABEL="com.dxs.teraguchi.server"
AGENT_PLIST="${HOME}/Library/LaunchAgents/${AGENT_LABEL}.plist"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { printf "${CYAN}[INFO]${NC}  %s\n"  "$*"; }
ok()    { printf "${GREEN}[OK]${NC}    %s\n" "$*"; }
warn()  { printf "${YELLOW}[WARN]${NC}  %s\n" "$*"; }
err()   { printf "${RED}[ERROR]${NC} %s\n"   "$*"; }

SETUP_AGENT=true
DEV_MODE=false
for arg in "$@"; do
    case "$arg" in
        --no-agent) SETUP_AGENT=false ;;
        --dev)      DEV_MODE=true ;;
        --help|-h)
            echo "Usage: bash install-server-macos.sh [--no-agent] [--dev]"
            echo ""
            echo "  --no-agent  Skip LaunchAgent registration (run manually)"
            echo "  --dev       Use the repo in place instead of copying to"
            echo "              ~/Library/Application Support/Teraguchi"
            exit 0
            ;;
    esac
done

# ── Preflight ────────────────────────────────────────────────────

if [ "$(uname)" != "Darwin" ]; then
    err "This installer is for macOS only. Use install-server.sh on Linux."
    exit 1
fi

if [ "$EUID" -eq 0 ]; then
    err "Do NOT run this installer as root. macOS LaunchAgents must be"
    err "installed as the regular logged-in user so SCK / CoreGraphics"
    err "inherit the right GUI session."
    exit 1
fi

# ── Homebrew + Python + FFmpeg ───────────────────────────────────

if ! command -v brew >/dev/null 2>&1; then
    err "Homebrew not found. Install it first from https://brew.sh"
    exit 1
fi
ok "Homebrew found at $(command -v brew)"

# Find a Python >= 3.10. Prefer brew's python3, fall back to system.
PYTHON_BIN=""
for candidate in \
    /opt/homebrew/bin/python3.13 \
    /opt/homebrew/bin/python3.12 \
    /opt/homebrew/bin/python3.11 \
    /opt/homebrew/bin/python3 \
    /usr/local/bin/python3 \
    /usr/bin/python3
do
    if [ -x "$candidate" ]; then
        vers=$("$candidate" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo "")
        major=$(echo "$vers" | cut -d. -f1)
        minor=$(echo "$vers" | cut -d. -f2)
        if [ -n "$vers" ] && [ "$major" = "3" ] && [ "$minor" -ge 10 ]; then
            PYTHON_BIN="$candidate"
            break
        fi
    fi
done

if [ -z "$PYTHON_BIN" ]; then
    err "Python 3.10+ not found. Run: brew install python@3.13"
    exit 1
fi
ok "Using Python: $PYTHON_BIN ($($PYTHON_BIN --version 2>&1))"

if ! command -v ffmpeg >/dev/null 2>&1; then
    info "Installing FFmpeg via Homebrew..."
    brew install ffmpeg
fi
ok "FFmpeg found at $(command -v ffmpeg)"

# ── Create install dir / venv ───────────────────────────────────

if $DEV_MODE; then
    INSTALL_DIR="$SCRIPT_DIR"
    VENV_DIR="$INSTALL_DIR/.venv"
    info "Dev mode: using repo in place at $INSTALL_DIR"
else
    mkdir -p "$INSTALL_DIR"
    info "Copying server files to $INSTALL_DIR"
    # Copy everything except heavy transient dirs.
    rsync -a --delete \
        --exclude=".venv" --exclude=".git" --exclude="build" \
        --exclude="dist" --exclude="__pycache__" \
        --exclude="Teraguchi.app" \
        "$SCRIPT_DIR/" "$INSTALL_DIR/"
fi

mkdir -p "$LOG_DIR"

if [ ! -d "$VENV_DIR" ]; then
    info "Creating venv at $VENV_DIR"
    "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"
pip install --quiet --upgrade pip wheel

info "Installing Python dependencies..."
pip install --quiet \
    websockets \
    numpy \
    Pillow \
    pyobjc-core \
    pyobjc-framework-Cocoa \
    pyobjc-framework-Quartz \
    pyobjc-framework-ScreenCaptureKit \
    pyobjc-framework-AVFoundation \
    pyobjc-framework-CoreMedia \
    pyobjc-framework-CoreAudio \
    pyobjc-framework-ApplicationServices

# Optional deps from requirements-server.txt that also work on Mac
if [ -f "$INSTALL_DIR/requirements-server.txt" ]; then
    info "Installing requirements-server.txt (best-effort; Linux-only pkgs skipped)..."
    while IFS= read -r line; do
        case "$line" in
            \#*|"") continue ;;
            *python-xlib*|*python-pam*|*uinput*) continue ;;
            *) pip install --quiet "$line" 2>/dev/null || warn "Skipped: $line" ;;
        esac
    done < "$INSTALL_DIR/requirements-server.txt"
fi

ok "Dependencies installed"

# ── Sanity check import ─────────────────────────────────────────

info "Smoke-testing server import..."
cd "$INSTALL_DIR"
if ! python -c "
import server.main
from server.platform_backends import IS_MACOS, ScreenCapture, InputInjector, ClipboardSync
assert IS_MACOS, 'IS_MACOS should be True on macOS'
print('server.main import OK, backends:', ScreenCapture.__name__, InputInjector.__name__, ClipboardSync.__name__)
" ; then
    err "server.main failed to import — see traceback above."
    exit 1
fi

# ── Permissions reminder ────────────────────────────────────────

warn "=============================================================="
warn " macOS PRIVACY PERMISSIONS REQUIRED"
warn "=============================================================="
warn ""
warn " Teraguchi needs these permissions before the first run. Grant"
warn " them in System Settings → Privacy & Security:"
warn ""
warn "   * Screen & System Audio Recording  (for ScreenCaptureKit)"
warn "   * Accessibility                    (for CoreGraphics input)"
warn "   * Input Monitoring                 (for global key events)"
warn ""
warn " On first launch, macOS will prompt you to add the Python"
warn " interpreter ($PYTHON_BIN) to each of these. Click 'Open System"
warn " Settings' in the prompt, then toggle Python on."
warn ""
warn "=============================================================="

# ── LaunchAgent ─────────────────────────────────────────────────

if $SETUP_AGENT; then
    info "Writing LaunchAgent plist: $AGENT_PLIST"
    mkdir -p "$(dirname "$AGENT_PLIST")"
    cat > "$AGENT_PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${AGENT_LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>${VENV_DIR}/bin/python</string>
    <string>-m</string>
    <string>server.main</string>
    <string>--auth-mode</string>
    <string>none</string>
  </array>
  <key>WorkingDirectory</key>
  <string>${INSTALL_DIR}</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>${LOG_DIR}/server.log</string>
  <key>StandardErrorPath</key>
  <string>${LOG_DIR}/server.err.log</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
  </dict>
</dict>
</plist>
EOF
    ok "LaunchAgent written"
    info "To enable it now:"
    echo "    launchctl unload \"$AGENT_PLIST\" 2>/dev/null || true"
    echo "    launchctl load -w \"$AGENT_PLIST\""
    info "Logs will stream to:"
    echo "    $LOG_DIR/server.log"
    echo "    $LOG_DIR/server.err.log"
else
    info "LaunchAgent setup skipped. To run manually:"
    echo "    cd \"$INSTALL_DIR\""
    echo "    source .venv/bin/activate"
    echo "    python -m server.main --auth-mode none"
fi

ok "Teraguchi macOS server install complete."
