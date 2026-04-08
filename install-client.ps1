#
# Teragucci Client Installer (Windows)
#
# Installs Python dependencies, creates a launch shortcut, and optionally
# builds a standalone .exe with PyInstaller.
#
# Usage (run in PowerShell):
#   .\install-client.ps1
#   .\install-client.ps1 -Build       # also build standalone exe
#   .\install-client.ps1 -Shortcut    # create Desktop shortcut
#

param(
    [switch]$Build,
    [switch]$Shortcut,
    [switch]$Help
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvDir = Join-Path $ScriptDir ".venv"

function Write-Info($msg)  { Write-Host "[INFO]  $msg" -ForegroundColor Cyan }
function Write-Ok($msg)    { Write-Host "[OK]    $msg" -ForegroundColor Green }
function Write-Warn($msg)  { Write-Host "[WARN]  $msg" -ForegroundColor Yellow }
function Write-Err($msg)   { Write-Host "[ERROR] $msg" -ForegroundColor Red }

if ($Help) {
    Write-Host "Usage: .\install-client.ps1 [-Build] [-Shortcut]"
    Write-Host "  -Build      Also build standalone .exe with PyInstaller"
    Write-Host "  -Shortcut   Create a Desktop shortcut"
    exit 0
}

Write-Host ""
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "  Teragucci Client Installer (Windows)       " -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host ""

# ── Check Python ─────────────────────────────────────────────────

Write-Info "Checking for Python 3.10+..."

$Python = $null
foreach ($cmd in @("python", "python3", "py -3")) {
    try {
        $ver = & $cmd.Split()[0] $cmd.Split()[1..99] --version 2>&1
        if ($ver -match "Python (\d+)\.(\d+)") {
            $major = [int]$Matches[1]
            $minor = [int]$Matches[2]
            if ($major -ge 3 -and $minor -ge 10) {
                $Python = $cmd
                Write-Ok "Found: $ver"
                break
            }
        }
    } catch {
        continue
    }
}

if (-not $Python) {
    # Try 'py -3' launcher specifically
    try {
        $ver = & py -3 --version 2>&1
        if ($ver -match "Python (\d+)\.(\d+)") {
            $major = [int]$Matches[1]
            $minor = [int]$Matches[2]
            if ($major -ge 3 -and $minor -ge 10) {
                $Python = "py -3"
                Write-Ok "Found: $ver (via py launcher)"
            }
        }
    } catch {}
}

if (-not $Python) {
    Write-Err "Python 3.10+ is required but not found."
    Write-Host ""
    Write-Host "  Download from: https://www.python.org/downloads/" -ForegroundColor Yellow
    Write-Host "  IMPORTANT: Check 'Add Python to PATH' during install!" -ForegroundColor Yellow
    Write-Host ""
    exit 1
}

# ── Create virtual environment ───────────────────────────────────

Write-Host ""
Write-Info "Creating Python virtual environment..."

if (Test-Path $VenvDir) {
    Write-Info "Existing venv found, upgrading..."
} else {
    if ($Python -eq "py -3") {
        & py -3 -m venv $VenvDir
    } else {
        & $Python -m venv $VenvDir
    }
}

$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
$VenvPip = Join-Path $VenvDir "Scripts\pip.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Err "Failed to create virtual environment."
    exit 1
}

Write-Ok "Virtual environment: $VenvDir"

# ── Install dependencies ─────────────────────────────────────────

Write-Info "Installing Python dependencies..."

& $VenvPip install --upgrade pip -q 2>&1 | Out-Null
& $VenvPip install -r (Join-Path $ScriptDir "requirements-client.txt") -q
Write-Ok "Dependencies installed (PySide6 + websockets)"

# ── Verify PySide6 ───────────────────────────────────────────────

Write-Host ""
Write-Info "Verifying PySide6..."

try {
    & $VenvPython -c "from PySide6.QtWidgets import QApplication; print('PySide6 OK')" 2>&1 | Out-Null
    Write-Ok "PySide6 works"
} catch {
    Write-Err "PySide6 import failed. Try reinstalling:"
    Write-Host "    $VenvPip install --force-reinstall PySide6"
    exit 1
}

# ── Create launch script ────────────────────────────────────────

$LauncherBat = Join-Path $ScriptDir "teragucci.bat"
$LauncherContent = @"
@echo off
REM Teragucci Client Launcher
cd /d "$ScriptDir"
call "$VenvDir\Scripts\activate.bat"
python -m client.main %*
"@
Set-Content -Path $LauncherBat -Value $LauncherContent
Write-Ok "Created launcher: teragucci.bat"

# Also create a PowerShell launcher
$LauncherPs1 = Join-Path $ScriptDir "teragucci-launch.ps1"
$PsContent = @"
# Teragucci Client Launcher
Set-Location "$ScriptDir"
& "$VenvPython" -m client.main @args
"@
Set-Content -Path $LauncherPs1 -Value $PsContent
Write-Ok "Created launcher: teragucci-launch.ps1"

# ── Desktop shortcut ─────────────────────────────────────────────

if ($Shortcut) {
    Write-Host ""
    Write-Info "Creating Desktop shortcut..."

    $Desktop = [Environment]::GetFolderPath("Desktop")
    $ShortcutPath = Join-Path $Desktop "Teragucci.lnk"

    $WshShell = New-Object -ComObject WScript.Shell
    $Lnk = $WshShell.CreateShortcut($ShortcutPath)
    $Lnk.TargetPath = $LauncherBat
    $Lnk.WorkingDirectory = $ScriptDir
    $Lnk.Description = "Teragucci Remote Desktop Client"
    $Lnk.Save()

    Write-Ok "Desktop shortcut created: $ShortcutPath"
}

# ── Optional: Build standalone exe ───────────────────────────────

if ($Build) {
    Write-Host ""
    Write-Info "Building standalone application with PyInstaller..."

    & $VenvPip install pyinstaller -q
    & $VenvPython (Join-Path $ScriptDir "build_client.py")

    $DistDir = Join-Path $ScriptDir "dist\Teragucci"
    if (Test-Path $DistDir) {
        Write-Ok "Standalone app built: $DistDir"
        Write-Host "  You can copy the dist\Teragucci folder to any Windows PC." -ForegroundColor Yellow
    }
}

# ── Done ─────────────────────────────────────────────────────────

Write-Host ""
Write-Host "=============================================" -ForegroundColor Green
Write-Host "  Teragucci client installation complete!     " -ForegroundColor Green
Write-Host "=============================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Launch:"
Write-Host "    teragucci.bat" -ForegroundColor White
Write-Host ""
Write-Host "  Or with a direct connection:"
Write-Host "    teragucci.bat --host 192.168.1.100 --port 9876" -ForegroundColor White
Write-Host ""
Write-Host "  With credentials:"
Write-Host "    teragucci.bat --host 192.168.1.100 -u myuser" -ForegroundColor White
Write-Host ""
Write-Host "  To create a Desktop shortcut later:"
Write-Host "    .\install-client.ps1 -Shortcut" -ForegroundColor Gray
Write-Host ""
Write-Host "  To build a portable exe later:"
Write-Host "    .\install-client.ps1 -Build" -ForegroundColor Gray
Write-Host ""
