"""
X Session Manager for Teragucci server.

Manages per-user X11 sessions, replacing HP Anyware / PCoIP:
- Each authenticated user gets a GPU-accelerated X display (real Xorg with NVIDIA)
- Sessions persist across disconnections for seamless reconnection
- Window manager / desktop launched per user
- Supports multiple concurrent user sessions

The server runs as root and spawns Xorg with NVIDIA's headless display
(ConnectedMonitor + CustomEDID), providing full GPU acceleration for
applications like Autodesk Flame that require NVIDIA GLX/MetaModes.

Falls back to Xvfb on machines without NVIDIA GPU.
"""

import logging
import os
import pwd
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)

DEFAULT_WIDTH = 1920
DEFAULT_HEIGHT = 1200
DEFAULT_DEPTH = 24
DEFAULT_DPI = 96

MIN_DISPLAY = 10
MAX_DISPLAY = 99

# Path to our Xorg config for headless GPU display
XORG_CONFIG = str(Path(__file__).parent / "xorg-teragucci.conf")


def find_free_display() -> int:
    """Find an unused X display number."""
    for n in range(MIN_DISPLAY, MAX_DISPLAY):
        lock_file = f"/tmp/.X{n}-lock"
        socket_path = f"/tmp/.X11-unix/X{n}"
        if not os.path.exists(lock_file) and not os.path.exists(socket_path):
            return n
    raise RuntimeError("No free X display numbers available (checked :{}-:{})".format(
        MIN_DISPLAY, MAX_DISPLAY - 1))


def detect_window_manager() -> List[str]:
    """Detect available window managers, return launch command for best option."""
    candidates = [
        (["gnome-shell", "--x11", "--sm-disable"], "GNOME Classic (gnome-shell --x11)"),
        (["xfce4-session"], "XFCE"),
        (["mate-session"], "MATE"),
        (["openbox-session"], "Openbox"),
        (["fluxbox"], "Fluxbox"),
        (["icewm-session"], "IceWM"),
        (["twm"], "TWM"),
        (["xterm"], "xterm (fallback)"),
    ]
    for cmd, name in candidates:
        try:
            result = subprocess.run(
                ["which", cmd[0]], capture_output=True, timeout=5)
            if result.returncode == 0:
                logger.info("Window manager: %s", name)
                return cmd
        except Exception:
            pass

    logger.warning("No window manager found — sessions will have a bare X display")
    return []


def has_nvidia_gpu() -> bool:
    """Check if NVIDIA GPU and driver are available."""
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and result.stdout.strip():
            logger.info("NVIDIA GPU detected: %s", result.stdout.strip().split('\n')[0])
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return False


def find_edid_file() -> str:
    """Find or generate an EDID file for the fake display."""
    # PCoIP ships EDID files we can use
    pcoip_edid = "/usr/share/pcoip-agent/1024x768.bin"
    if os.path.exists(pcoip_edid):
        logger.info("Using PCoIP EDID: %s", pcoip_edid)
        return pcoip_edid

    # Check for our own EDID
    our_edid = str(Path(__file__).parent / "edid" / "1920x1200.bin")
    if os.path.exists(our_edid):
        return our_edid

    # Generate a minimal EDID if none found
    edid_dir = str(Path(__file__).parent / "edid")
    os.makedirs(edid_dir, exist_ok=True)
    edid_path = os.path.join(edid_dir, "default.bin")
    if not os.path.exists(edid_path):
        _generate_edid(edid_path, 1920, 1200)
    return edid_path


def _generate_edid(path: str, width: int, height: int):
    """Generate a minimal EDID 1.3 binary for a given resolution."""
    # Standard EDID 1.3 block (128 bytes)
    # This creates a basic monitor profile that NVIDIA's driver will accept
    edid = bytearray(128)

    # Header
    edid[0:8] = b'\x00\xff\xff\xff\xff\xff\xff\x00'

    # Manufacturer ID "TGC" (Teragucci) - encoded as 2 bytes
    # T=20, G=7, C=3 -> ((20-1)<<10) | ((7-1)<<5) | (3-1) = 0x4CC2
    edid[8] = 0x4C
    edid[9] = 0xC2

    # Product code
    edid[10] = 0x01
    edid[11] = 0x00

    # Serial number
    edid[12:16] = b'\x01\x00\x00\x00'

    # Week 1, Year 2025 (offset from 1990 = 35)
    edid[16] = 1
    edid[17] = 35

    # EDID version 1.3
    edid[18] = 1
    edid[19] = 3

    # Digital input, 8-bit color
    edid[20] = 0x80

    # Max image size (cm): ~52cm x 32cm for a 24" display
    edid[21] = 52  # horizontal
    edid[22] = 32  # vertical

    # Gamma 2.2 (value = (gamma * 100) - 100 = 120)
    edid[23] = 120

    # Feature support: RGB color, preferred timing in DTD1
    edid[24] = 0x0A

    # Chromaticity (standard sRGB values)
    edid[25:35] = bytes([0xEE, 0x95, 0xA3, 0x54, 0x4C, 0x99, 0x26, 0x0F, 0x50, 0x54])

    # Established timings (640x480, 800x600, 1024x768)
    edid[35] = 0x21
    edid[36] = 0x08
    edid[37] = 0x00

    # Standard timings (unused, fill with 0x0101)
    for i in range(38, 54, 2):
        edid[i] = 0x01
        edid[i + 1] = 0x01

    # Detailed Timing Descriptor #1 - preferred mode
    # 1920x1200 @ 60Hz, pixel clock 154.0 MHz
    dtd_offset = 54
    pixel_clock = 15400  # in 10kHz units
    edid[dtd_offset] = pixel_clock & 0xFF
    edid[dtd_offset + 1] = (pixel_clock >> 8) & 0xFF

    # Horizontal: 1920 active, 160 blanking
    h_active = width
    h_blank = 160
    edid[dtd_offset + 2] = h_active & 0xFF
    edid[dtd_offset + 3] = h_blank & 0xFF
    edid[dtd_offset + 4] = ((h_active >> 8) << 4) | (h_blank >> 8)

    # Vertical: 1200 active, 35 blanking
    v_active = height
    v_blank = 35
    edid[dtd_offset + 5] = v_active & 0xFF
    edid[dtd_offset + 6] = v_blank & 0xFF
    edid[dtd_offset + 7] = ((v_active >> 8) << 4) | (v_blank >> 8)

    # Sync offsets/widths
    edid[dtd_offset + 8] = 48   # h_sync_offset
    edid[dtd_offset + 9] = 32   # h_sync_width
    edid[dtd_offset + 10] = 0x36  # v_sync_offset=3, v_sync_width=6
    edid[dtd_offset + 11] = 0x00

    # Image size (mm): 518mm x 324mm
    edid[dtd_offset + 12] = 0x06  # h_size low
    edid[dtd_offset + 13] = 0x44  # v_size low
    edid[dtd_offset + 14] = 0x21  # h_size high | v_size high

    edid[dtd_offset + 15] = 0  # h_border
    edid[dtd_offset + 16] = 0  # v_border
    edid[dtd_offset + 17] = 0x1E  # flags: digital separate sync, +hsync +vsync

    # Descriptor #2: Monitor name
    name_offset = 72
    edid[name_offset:name_offset + 5] = b'\x00\x00\x00\xFC\x00'
    name = "Teragucci"
    name_bytes = name.encode('ascii')[:13].ljust(13, b'\x0a')
    edid[name_offset + 5:name_offset + 18] = name_bytes

    # Descriptor #3: Monitor range limits
    range_offset = 90
    edid[range_offset:range_offset + 5] = b'\x00\x00\x00\xFD\x00'
    edid[range_offset + 5] = 24   # min v_freq
    edid[range_offset + 6] = 120  # max v_freq
    edid[range_offset + 7] = 28   # min h_freq (kHz)
    edid[range_offset + 8] = 160  # max h_freq (kHz)
    edid[range_offset + 9] = 22   # max pixel clock / 10 (220 MHz)
    edid[range_offset + 10] = 0x00  # no GTF

    # Descriptor #4: Dummy (unused)
    edid[108:126] = b'\x00\x00\x00\x10\x00' + b'\x00' * 13

    # Extension flag (0 = no extensions)
    edid[126] = 0

    # Checksum: sum of all 128 bytes must be 0 mod 256
    edid[127] = (256 - (sum(edid[:127]) % 256)) % 256

    with open(path, 'wb') as f:
        f.write(bytes(edid))
    logger.info("Generated EDID file: %s (%dx%d)", path, width, height)


@dataclass
class UserSession:
    """Tracks a running user X session."""
    username: str
    uid: int
    gid: int
    home: str
    display: str          # e.g., ":10"
    display_num: int
    width: int = DEFAULT_WIDTH
    height: int = DEFAULT_HEIGHT
    xorg_proc: Optional[subprocess.Popen] = None  # Real Xorg or Xvfb
    gpu_display: bool = False  # True if using real GPU Xorg
    wm_proc: Optional[subprocess.Popen] = None
    dbus_proc: Optional[subprocess.Popen] = None
    dbus_pid: Optional[int] = None  # PID from dbus-launch (for cleanup)
    dbus_address: str = ""  # D-Bus session bus address from dbus-launch
    pulseaudio_proc: Optional[subprocess.Popen] = None
    connected_clients: int = 0
    created_at: float = field(default_factory=time.time)
    xauthority: str = ""

    @property
    def alive(self) -> bool:
        return self.xorg_proc is not None and self.xorg_proc.poll() is None

    @property
    def env(self) -> dict:
        """Environment for processes in this session."""
        e = {
            "DISPLAY": self.display,
            "HOME": self.home,
            "USER": self.username,
            "LOGNAME": self.username,
            "SHELL": pwd.getpwuid(self.uid).pw_shell,
            "XDG_RUNTIME_DIR": f"/run/user/{self.uid}",
            "DBUS_SESSION_BUS_ADDRESS": self.dbus_address,
            "XDG_SESSION_TYPE": "x11",
        }
        if self.xauthority:
            e["XAUTHORITY"] = self.xauthority
        return e


class SessionManager:
    """
    Manages per-user virtual X sessions.

    Like PCoIP / HP Anyware:
    - User authenticates → get or create their X session
    - Session persists when client disconnects
    - User reconnects → same session, same state
    - Each session is an isolated Xvfb display with a window manager
    """

    def __init__(self, width: int = DEFAULT_WIDTH, height: int = DEFAULT_HEIGHT,
                 depth: int = DEFAULT_DEPTH, dpi: int = DEFAULT_DPI):
        self.width = width
        self.height = height
        self.depth = depth
        self.dpi = dpi
        self._sessions: Dict[str, UserSession] = {}
        self._wm_cmd = detect_window_manager()
        self._has_nvidia = has_nvidia_gpu()
        self._edid_file = find_edid_file() if self._has_nvidia else ""
        if self._has_nvidia:
            logger.info("GPU mode: will launch real Xorg with NVIDIA driver")
        else:
            logger.info("Software mode: will use Xvfb (no NVIDIA GPU detected)")

    def get_session(self, username: str) -> Optional[UserSession]:
        """Get an existing live session, or None."""
        session = self._sessions.get(username)
        if session and session.alive:
            # Check if WM died and restart it
            if session.wm_proc and session.wm_proc.poll() is not None:
                logger.warning("WM died for %s (exit %s), restarting",
                               username, session.wm_proc.returncode)
                self._start_window_manager(session)
            return session
        if session:
            logger.warning("Session for %s died, cleaning up", username)
            self._cleanup_session(session)
            del self._sessions[username]
        return None

    def create_session(self, username: str, uid: int, gid: int, home: str,
                       width: int = 0, height: int = 0) -> UserSession:
        """Create a new X session for a user, or return existing one."""
        existing = self.get_session(username)
        if existing:
            logger.info("Reusing session for %s on %s", username, existing.display)
            return existing

        w = width or self.width
        h = height or self.height
        display_num = find_free_display()
        display = f":{display_num}"

        logger.info("Creating session for %s on %s (%dx%d)", username, display, w, h)

        # Ensure XDG_RUNTIME_DIR exists
        runtime_dir = f"/run/user/{uid}"
        os.makedirs(runtime_dir, mode=0o700, exist_ok=True)
        os.chown(runtime_dir, uid, gid)

        # Xauthority
        xauth_dir = "/run/teragucci"
        os.makedirs(xauth_dir, mode=0o755, exist_ok=True)
        xauthority = f"{xauth_dir}/{username}.xauth"

        try:
            # Remove stale xauth
            if os.path.exists(xauthority):
                os.unlink(xauthority)
            subprocess.run(
                ["xauth", "-f", xauthority, "generate", display, ".", "trusted"],
                capture_output=True, timeout=10,
                env={"XAUTHORITY": xauthority, "HOME": home})
            os.chown(xauthority, uid, gid)
        except Exception as e:
            logger.warning("xauth failed: %s (using -ac instead)", e)
            xauthority = ""

        # Launch X server — real Xorg with NVIDIA GPU, or Xvfb fallback
        gpu_display = False
        if self._has_nvidia:
            xorg_proc, gpu_display = self._start_xorg_gpu(
                display, display_num, w, h, xauthority)
        else:
            xorg_proc = None

        if not xorg_proc:
            # Fallback to Xvfb (no GPU, or Xorg failed)
            xorg_proc = self._start_xvfb(display, display_num, w, h, xauthority)
            gpu_display = False

        session = UserSession(
            username=username, uid=uid, gid=gid, home=home,
            display=display, display_num=display_num,
            width=w, height=h,
            xorg_proc=xorg_proc, gpu_display=gpu_display,
            xauthority=xauthority)

        # Start D-Bus session for the user
        self._start_dbus(session)

        # Start PulseAudio for the user (audio capture needs it)
        self._start_pulseaudio(session)

        # Start window manager (gnome-shell needs D-Bus ready)
        if self._wm_cmd:
            if self._wm_cmd[0] == "gnome-shell":
                # Give D-Bus and X server time to fully initialize
                time.sleep(1)
            self._start_window_manager(session)

        self._sessions[username] = session
        return session

    def _start_xorg_gpu(self, display: str, display_num: int,
                        width: int, height: int,
                        xauthority: str) -> tuple:
        """Start a real Xorg server with NVIDIA GPU acceleration.

        Returns (Popen, True) on success, (None, False) on failure.
        """
        xorg_bin = "/usr/libexec/Xorg"
        if not os.path.exists(xorg_bin):
            xorg_bin = shutil.which("Xorg") or shutil.which("X")
        if not xorg_bin:
            logger.warning("Xorg binary not found, falling back to Xvfb")
            return None, False

        # Write a per-display xorg config with the EDID path filled in
        config_path = f"/tmp/teragucci-xorg-{display_num}.conf"
        self._write_xorg_config(config_path, width, height)

        log_file = f"/var/log/teragucci-Xorg-{display_num}.log"

        xorg_cmd = [
            xorg_bin, display,
            "-config", config_path,
            "-novtswitch",
            "-noreset",
            "-nolisten", "tcp",
            "-logfile", log_file,
        ]
        if xauthority:
            xorg_cmd.extend(["-auth", xauthority])

        logger.info("Starting Xorg GPU display %s: %s", display, " ".join(xorg_cmd))

        try:
            xorg_proc = subprocess.Popen(
                xorg_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE)

            # Wait for X socket to appear (Xorg takes longer than Xvfb)
            for i in range(100):  # 10 seconds max
                if os.path.exists(f"/tmp/.X11-unix/X{display_num}"):
                    break
                # Check if process died
                if xorg_proc.poll() is not None:
                    stderr = xorg_proc.stderr.read().decode(errors='replace') if xorg_proc.stderr else ""
                    logger.error("Xorg died on startup (exit %d): %s",
                                 xorg_proc.returncode, stderr[:500])
                    # Check the log file for more details
                    try:
                        with open(log_file) as f:
                            log_tail = f.read()[-2000:]
                        logger.error("Xorg log tail:\n%s", log_tail)
                    except Exception:
                        pass
                    return None, False
                time.sleep(0.1)
            else:
                xorg_proc.kill()
                logger.error("Xorg timed out waiting for socket on %s", display)
                return None, False

            logger.info("Xorg GPU started on %s (pid %d)", display, xorg_proc.pid)

            # Set initial resolution via xrandr
            time.sleep(0.5)  # Give Xorg a moment to fully initialize
            self._set_gpu_resolution(display, width, height, xauthority)

            return xorg_proc, True

        except Exception as e:
            logger.error("Failed to start Xorg GPU: %s", e)
            return None, False

    def _write_xorg_config(self, config_path: str, width: int, height: int):
        """Write a per-display xorg.conf with EDID and resolution settings."""
        edid = self._edid_file

        config = f'''# Auto-generated by Teragucci session manager
# GPU-accelerated headless display with NVIDIA driver

Section "ServerLayout"
    Identifier     "Teragucci"
    Screen      0  "Screen0"
    Option         "AllowEmptyInitialConfiguration" "true"
EndSection

Section "ServerFlags"
    Option         "DefaultServerLayout" "Teragucci"
    Option         "AllowMouseOpenFail" "true"
    Option         "AutoAddDevices" "false"
    Option         "AutoEnableDevices" "false"
    Option         "DontVTSwitch" "true"
EndSection

Section "Device"
    Identifier     "Device0"
    Driver         "nvidia"
    Option         "ConnectedMonitor" "DFP-0"
    Option         "CustomEDID" "DFP-0:{edid}"
    Option         "AllowEmptyInitialConfiguration" "true"
    Option         "HardDPMS" "false"
    Option         "Interactive" "false"
    Option         "ModeValidation" "AllowNonEdidModes, NoEdidMaxPClkCheck, NoHorizSyncCheck, NoVertRefreshCheck, NoMaxSizeCheck"
    Option         "MetaModes" "DFP-0: {width}x{height} +0+0"
EndSection

Section "Monitor"
    Identifier     "Monitor0"
    HorizSync      28.0-160.0
    VertRefresh    24.0-120.0
EndSection

Section "Screen"
    Identifier     "Screen0"
    Device         "Device0"
    Monitor        "Monitor0"
    DefaultDepth   24
    Option         "AllowEmptyInitialConfiguration" "true"
    SubSection     "Display"
        Virtual    {max(width, 3840)} {max(height, 2160)}
        Depth      24
    EndSubSection
EndSection

Section "Extensions"
    Option         "GLX" "Enable"
    Option         "RANDR" "Enable"
EndSection
'''
        with open(config_path, 'w') as f:
            f.write(config)
        logger.debug("Wrote Xorg config: %s", config_path)

    def _set_gpu_resolution(self, display: str, width: int, height: int,
                            xauthority: str):
        """Set the display resolution via xrandr on GPU display."""
        env = {"DISPLAY": display}
        if xauthority:
            env["XAUTHORITY"] = xauthority

        try:
            # Query available outputs
            result = subprocess.run(
                ["xrandr", "--query"],
                capture_output=True, text=True, timeout=5, env=env)
            logger.debug("xrandr output:\n%s", result.stdout[:1000])

            # Find the connected output name
            output_name = None
            for line in result.stdout.splitlines():
                if " connected" in line:
                    output_name = line.split()[0]
                    break

            if not output_name:
                logger.warning("No connected output found in xrandr")
                return

            mode = f"{width}x{height}"
            result = subprocess.run(
                ["xrandr", "--output", output_name, "--mode", mode],
                capture_output=True, text=True, timeout=5, env=env)
            if result.returncode == 0:
                logger.info("Set GPU display to %s on %s", mode, output_name)
            else:
                # Mode might not exist, try adding it
                logger.info("Mode %s not available, trying to add it", mode)
                cvt = subprocess.run(
                    ["cvt", str(width), str(height), "60"],
                    capture_output=True, text=True, timeout=5)
                for line in cvt.stdout.splitlines():
                    if line.startswith("Modeline"):
                        parts = line.split(None, 2)
                        mode_label = parts[1].strip('"')
                        mode_params = parts[2]
                        subprocess.run(
                            ["xrandr", "--newmode", mode_label] + mode_params.split(),
                            capture_output=True, timeout=5, env=env)
                        subprocess.run(
                            ["xrandr", "--addmode", output_name, mode_label],
                            capture_output=True, timeout=5, env=env)
                        subprocess.run(
                            ["xrandr", "--output", output_name, "--mode", mode_label],
                            capture_output=True, timeout=5, env=env)
                        logger.info("Added and set mode %s", mode_label)
                        break
        except Exception as e:
            logger.warning("Failed to set GPU resolution: %s", e)

    def _start_xvfb(self, display: str, display_num: int,
                    width: int, height: int, xauthority: str) -> subprocess.Popen:
        """Start Xvfb as fallback (no GPU acceleration)."""
        xvfb_cmd = [
            "Xvfb", display,
            "-screen", "0", f"{width}x{height}x{self.depth}",
            "-dpi", str(self.dpi),
            "-ac",
            "+extension", "RANDR",
            "+extension", "GLX",
            "-nolisten", "tcp",
        ]
        if xauthority:
            xvfb_cmd.extend(["-auth", xauthority])

        logger.info("Starting Xvfb on %s (software rendering)", display)
        xvfb_proc = subprocess.Popen(
            xvfb_cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE)

        # Wait for socket
        for _ in range(50):
            if os.path.exists(f"/tmp/.X11-unix/X{display_num}"):
                break
            time.sleep(0.1)
        else:
            xvfb_proc.kill()
            raise RuntimeError(f"Xvfb failed to start on {display}")

        logger.info("Xvfb started on %s (pid %d)", display, xvfb_proc.pid)
        return xvfb_proc

    def _demote(self, uid: int, gid: int):
        """preexec_fn to drop privileges to a user."""
        os.setgid(gid)
        os.initgroups(pwd.getpwuid(uid).pw_name, gid)
        os.setuid(uid)

    def _start_dbus(self, session: UserSession):
        """Set up D-Bus for the session.

        Use the user's existing dbus-broker session bus (at
        /run/user/<uid>/bus) and update its environment so D-Bus
        activated services (gnome-terminal, etc.) get DISPLAY set.

        Fall back to dbus-launch if no existing bus is found.
        """
        # Check for existing user session bus (dbus-broker)
        user_bus = f"/run/user/{session.uid}/bus"
        if os.path.exists(user_bus):
            session.dbus_address = f"unix:path={user_bus}"
            logger.info("D-Bus using existing user bus for %s: %s",
                        session.username, session.dbus_address)
            # Update the bus environment so D-Bus activated services
            # (gnome-terminal-server, etc.) inherit our DISPLAY
            self._update_dbus_environment(session)
            return

        # No existing bus — start our own via dbus-launch
        try:
            result = subprocess.run(
                ["dbus-launch", "--sh-syntax"],
                capture_output=True, text=True, timeout=5,
                preexec_fn=lambda: self._demote(session.uid, session.gid),
                env=session.env)
            bus_addr = ""
            bus_pid = None
            for line in result.stdout.splitlines():
                if line.startswith("DBUS_SESSION_BUS_ADDRESS="):
                    bus_addr = line.split("=", 1)[1].strip(" ;'\"")
                elif line.startswith("DBUS_SESSION_BUS_PID="):
                    try:
                        bus_pid = int(line.split("=", 1)[1].strip(" ;'\""))
                    except ValueError:
                        pass
            if bus_addr:
                session.dbus_address = bus_addr
                session.dbus_pid = bus_pid
                logger.info("D-Bus started for %s: %s (pid %s)",
                            session.username, bus_addr, bus_pid)
                # Also update the bus environment for activated services
                self._update_dbus_environment(session)
            else:
                logger.warning("D-Bus launch returned no address for %s",
                               session.username)
        except Exception as e:
            logger.warning("D-Bus failed for %s: %s", session.username, e)

    def _update_dbus_environment(self, session: UserSession):
        """Push DISPLAY and XAUTHORITY into D-Bus so activated services inherit them.

        This is critical — without it, D-Bus service activation (e.g.
        gnome-terminal via StartServiceByName) won't know which X display
        to use and will fail.
        """
        env_vars = {
            "DISPLAY": session.display,
            "XDG_SESSION_TYPE": "x11",
            "GDK_BACKEND": "x11",
        }
        if session.xauthority:
            env_vars["XAUTHORITY"] = session.xauthority

        try:
            # dbus-update-activation-environment pushes vars into dbus-daemon/broker
            # AND systemd --user, so ALL activated services get them
            cmd = ["dbus-update-activation-environment", "--systemd"]
            for k, v in env_vars.items():
                cmd.append(f"{k}={v}")

            # Must pass DISPLAY and DBUS_SESSION_BUS_ADDRESS in the
            # calling environment too, or the tool complains
            run_env = session.env.copy()
            run_env["PATH"] = os.environ.get("PATH", "/usr/bin:/bin")

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=5,
                preexec_fn=lambda: self._demote(session.uid, session.gid),
                env=run_env)
            if result.returncode == 0:
                logger.info("Updated D-Bus activation environment for %s: DISPLAY=%s",
                            session.username, session.display)
            else:
                logger.warning("dbus-update-activation-environment failed: %s",
                               result.stderr.strip())
        except FileNotFoundError:
            # Fallback: use busctl to set environment on systemd user manager
            try:
                for k, v in env_vars.items():
                    subprocess.run(
                        ["busctl", "--user", "call",
                         "org.freedesktop.systemd1",
                         "/org/freedesktop/systemd1",
                         "org.freedesktop.systemd1.Manager",
                         "SetEnvironment", "as", "1", f"{k}={v}"],
                        capture_output=True, timeout=5,
                        preexec_fn=lambda: self._demote(session.uid, session.gid),
                        env=session.env)
                logger.info("Updated systemd user environment for %s via busctl",
                            session.username)
            except Exception as e2:
                logger.warning("Failed to update D-Bus environment: %s", e2)
        except Exception as e:
            logger.warning("Failed to update D-Bus environment: %s", e)

    def _start_pulseaudio(self, session: UserSession):
        """Start a PulseAudio server for the user's session."""
        try:
            env = session.env.copy()
            env["PULSE_RUNTIME_PATH"] = f"/run/user/{session.uid}/pulse"
            os.makedirs(env["PULSE_RUNTIME_PATH"], mode=0o700, exist_ok=True)
            os.chown(env["PULSE_RUNTIME_PATH"], session.uid, session.gid)

            session.pulseaudio_proc = subprocess.Popen(
                ["pulseaudio", "--start", "--exit-idle-time=-1", "--daemonize=no"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                preexec_fn=lambda: self._demote(session.uid, session.gid),
                env=env)
            logger.info("PulseAudio started for %s", session.username)
        except Exception as e:
            logger.warning("PulseAudio failed for %s: %s", session.username, e)

    def _get_logind_session_id(self, username: str) -> str:
        """Find an existing logind session ID for the user."""
        try:
            result = subprocess.run(
                ["loginctl", "list-sessions", "--no-legend"],
                capture_output=True, text=True, timeout=5)
            for line in result.stdout.strip().split("\n"):
                parts = line.split()
                if len(parts) >= 3 and parts[2] == username:
                    return parts[0]
        except Exception as e:
            logger.debug("Could not query logind sessions: %s", e)
        return ""

    def _create_logind_session(self, uid: int, username: str, display: str) -> str:
        """Create a logind session for the user via busctl."""
        try:
            result = subprocess.run(
                ["busctl", "call", "org.freedesktop.login1",
                 "/org/freedesktop/login1",
                 "org.freedesktop.login1.Manager",
                 "CreateSession",
                 "uusssssussbssa(sv)",
                 str(uid),       # uid
                 "0",            # pid (0 = let logind pick)
                 username,       # service
                 "x11",          # type
                 "",             # class
                 "",             # desktop
                 "",             # seat_id
                 "0",            # vtnr
                 "",             # tty
                 display,        # display
                 "false",        # remote
                 "",             # remote_user
                 "",             # remote_host
                 "0",            # properties count
                 ],
                capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                # Parse session ID from response
                parts = result.stdout.strip().split()
                for p in parts:
                    p = p.strip('"')
                    if p.isdigit():
                        return p
                    if p.startswith('/org/freedesktop/login1/session/'):
                        sid = p.split('/')[-1].lstrip('_')
                        return sid
            logger.debug("CreateSession failed: %s", result.stderr)
        except Exception as e:
            logger.debug("Could not create logind session: %s", e)
        return ""

    def _start_window_manager(self, session: UserSession):
        try:
            env = session.env.copy()

            if self._wm_cmd and self._wm_cmd[0] == "gnome-shell":
                # gnome-shell needs XDG_SESSION_ID for ScreenShield/loginManager.js
                session_id = self._create_logind_session(
                    session.uid, session.username, session.display)
                if not session_id:
                    session_id = self._get_logind_session_id(session.username)
                if session_id:
                    env["XDG_SESSION_ID"] = session_id
                    logger.info("Using logind session %s for gnome-shell", session_id)
                else:
                    logger.warning("No logind session found for %s, gnome-shell may fail",
                                   session.username)

                env["GNOME_SHELL_SESSION_MODE"] = "classic"
                env["XDG_CURRENT_DESKTOP"] = "GNOME-Classic:GNOME"
                env["GDK_BACKEND"] = "x11"
                if not session.gpu_display:
                    # Force software rendering for Xvfb — the GPU's EGL/GLX
                    # context isn't available on virtual displays
                    env["LIBGL_ALWAYS_SOFTWARE"] = "1"
                    env["__GLX_VENDOR_LIBRARY_NAME"] = "mesa"

            wm_cmd = list(self._wm_cmd)
            if wm_cmd[0] == "gnome-shell":
                wm_cmd.extend(["--display=" + session.display, "--replace"])

            session.wm_proc = subprocess.Popen(
                wm_cmd,
                stdout=subprocess.DEVNULL,
                stderr=open(f"/tmp/teragucci-wm-{session.username}.log", "w"),
                preexec_fn=lambda: self._demote(session.uid, session.gid),
                env=env)
            logger.info("Window manager started for %s: %s",
                        session.username, self._wm_cmd[0])

            # Start gnome-terminal-server so terminal launches work via D-Bus
            if wm_cmd[0] == "gnome-shell":
                self._start_gnome_terminal_server(session)
        except Exception as e:
            logger.warning("WM failed for %s: %s", session.username, e)

    def _start_gnome_terminal_server(self, session: UserSession):
        """Pre-start gnome-terminal-server so gnome-terminal can connect."""
        try:
            gt_server = shutil.which("gnome-terminal-server")
            if not gt_server:
                gt_server = "/usr/libexec/gnome-terminal-server"
            if not os.path.exists(gt_server):
                logger.debug("gnome-terminal-server not found, skipping")
                return
            subprocess.Popen(
                [gt_server, "--app-id", "org.gnome.Terminal"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                preexec_fn=lambda: self._demote(session.uid, session.gid),
                env=session.env)
            logger.info("gnome-terminal-server started for %s", session.username)
        except Exception as e:
            logger.debug("gnome-terminal-server failed: %s", e)

    def resize_display(self, username: str, width: int, height: int) -> bool:
        """Resize an existing session's display via xrandr."""
        session = self.get_session(username)
        if not session or not session.alive:
            return False

        # Clamp to reasonable bounds
        width = max(640, min(width, 3840))
        height = max(480, min(height, 2160))

        if width == session.width and height == session.height:
            return True

        try:
            display = session.display
            env = {**os.environ, "DISPLAY": display}

            # Add the new mode if it doesn't exist
            mode_name = f"{width}x{height}"
            # Generate modeline
            modeline = subprocess.run(
                ["cvt", str(width), str(height)],
                capture_output=True, text=True, timeout=5, env=env)
            if modeline.returncode == 0:
                # Parse modeline output: Modeline "WxH_60.00" ...
                for line in modeline.stdout.strip().split("\n"):
                    if line.startswith("Modeline"):
                        parts = line.split(None, 2)
                        mode_label = parts[1].strip('"')
                        mode_params = parts[2]

                        # Create new mode
                        subprocess.run(
                            ["xrandr", "--newmode", mode_label] + mode_params.split(),
                            capture_output=True, timeout=5, env=env)
                        # Add mode to screen output
                        subprocess.run(
                            ["xrandr", "--addmode", "screen", mode_label],
                            capture_output=True, timeout=5, env=env)
                        # Set the mode
                        result = subprocess.run(
                            ["xrandr", "--output", "screen", "--mode", mode_label],
                            capture_output=True, text=True, timeout=5, env=env)
                        if result.returncode == 0:
                            session.width = width
                            session.height = height
                            logger.info("Resized display %s to %dx%d",
                                        display, width, height)
                            return True
                        else:
                            logger.warning("xrandr set mode failed: %s", result.stderr)

        except Exception as e:
            logger.warning("Display resize failed: %s", e)

        return False

    def destroy_session(self, username: str):
        session = self._sessions.pop(username, None)
        if session:
            self._cleanup_session(session)
            logger.info("Session destroyed: %s", username)

    def _cleanup_session(self, session: UserSession):
        x_name = "Xorg" if session.gpu_display else "Xvfb"
        for name, proc in [("WM", session.wm_proc),
                           ("PulseAudio", session.pulseaudio_proc),
                           ("D-Bus", session.dbus_proc),
                           (x_name, session.xorg_proc)]:
            if proc and proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=2)
                logger.debug("Stopped %s (pid %d) for %s",
                             name, proc.pid, session.username)

        # Kill dbus-launch daemon if we have its PID
        if session.dbus_pid:
            try:
                os.kill(session.dbus_pid, signal.SIGTERM)
                logger.debug("Stopped D-Bus (pid %d) for %s", session.dbus_pid, session.username)
            except OSError:
                pass

        if session.xauthority and os.path.exists(session.xauthority):
            try:
                os.unlink(session.xauthority)
            except OSError:
                pass

        # Clean up temp xorg config
        config_path = f"/tmp/teragucci-xorg-{session.display_num}.conf"
        if os.path.exists(config_path):
            try:
                os.unlink(config_path)
            except OSError:
                pass

        lock_file = f"/tmp/.X{session.display_num}-lock"
        if os.path.exists(lock_file):
            try:
                os.unlink(lock_file)
            except OSError:
                pass

    def destroy_all(self):
        for username in list(self._sessions.keys()):
            self.destroy_session(username)
        logger.info("All sessions destroyed")

    def list_sessions(self) -> List[dict]:
        return [
            {
                "username": s.username,
                "display": s.display,
                "resolution": f"{s.width}x{s.height}",
                "clients": s.connected_clients,
                "alive": s.alive,
                "uptime_s": int(time.time() - s.created_at),
            }
            for s in self._sessions.values()
        ]
