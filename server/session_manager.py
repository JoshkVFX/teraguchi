"""
X Session Manager for Teragucci server.

Manages per-user X11 sessions, mimicking HP Anyware / PCoIP behavior:
- Each authenticated user gets an isolated virtual display (Xvfb)
- Sessions persist across disconnections for seamless reconnection
- Window manager / desktop launched per user
- Supports multiple concurrent user sessions

The server runs as root and spawns per-user processes with demoted privileges.
"""

import logging
import os
import pwd
import subprocess
import time
from dataclasses import dataclass, field
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)

DEFAULT_WIDTH = 1920
DEFAULT_HEIGHT = 1080
DEFAULT_DEPTH = 24
DEFAULT_DPI = 96

MIN_DISPLAY = 10
MAX_DISPLAY = 99


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
    xvfb_proc: Optional[subprocess.Popen] = None
    wm_proc: Optional[subprocess.Popen] = None
    dbus_proc: Optional[subprocess.Popen] = None
    pulseaudio_proc: Optional[subprocess.Popen] = None
    connected_clients: int = 0
    created_at: float = field(default_factory=time.time)
    xauthority: str = ""

    @property
    def alive(self) -> bool:
        return self.xvfb_proc is not None and self.xvfb_proc.poll() is None

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
            "DBUS_SESSION_BUS_ADDRESS": f"unix:path=/run/user/{self.uid}/bus",
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

    def get_session(self, username: str) -> Optional[UserSession]:
        """Get an existing live session, or None."""
        session = self._sessions.get(username)
        if session and session.alive:
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

        # Start Xvfb
        # Start Xvfb with large max screen for dynamic resize via xrandr
        max_w, max_h = 3840, 2160
        xvfb_cmd = [
            "Xvfb", display,
            "-screen", "0", f"{max_w}x{max_h}x{self.depth}",
            "-dpi", str(self.dpi),
            "-ac",
            "+extension", "RANDR",
            "+extension", "GLX",
            "-nolisten", "tcp",
        ]
        if xauthority:
            xvfb_cmd.extend(["-auth", xauthority])

        xvfb_proc = subprocess.Popen(
            xvfb_cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE)

        # Wait for Xvfb socket
        for _ in range(50):
            if os.path.exists(f"/tmp/.X11-unix/X{display_num}"):
                break
            time.sleep(0.1)
        else:
            xvfb_proc.kill()
            raise RuntimeError(f"Xvfb failed to start on {display}")

        logger.info("Xvfb started on %s (pid %d)", display, xvfb_proc.pid)

        # Xvfb starts at max size (3840x2160), resize to requested
        if w != max_w or h != max_h:
            try:
                env_x = {"DISPLAY": display}
                modeline = subprocess.run(
                    ["cvt", str(w), str(h)],
                    capture_output=True, text=True, timeout=5, env=env_x)
                if modeline.returncode == 0:
                    for line in modeline.stdout.strip().split("\n"):
                        if line.startswith("Modeline"):
                            parts = line.split(None, 2)
                            mode_label = parts[1].strip('"')
                            mode_params = parts[2]
                            subprocess.run(
                                ["xrandr", "--newmode", mode_label] + mode_params.split(),
                                capture_output=True, timeout=5, env=env_x)
                            subprocess.run(
                                ["xrandr", "--addmode", "screen", mode_label],
                                capture_output=True, timeout=5, env=env_x)
                            subprocess.run(
                                ["xrandr", "--output", "screen", "--mode", mode_label],
                                capture_output=True, timeout=5, env=env_x)
                            logger.info("Set initial display resolution to %dx%d", w, h)
                            break
            except Exception as e:
                logger.warning("Initial resize failed: %s", e)

        session = UserSession(
            username=username, uid=uid, gid=gid, home=home,
            display=display, display_num=display_num,
            width=w, height=h,
            xvfb_proc=xvfb_proc, xauthority=xauthority)

        # Start D-Bus session for the user
        self._start_dbus(session)

        # Start PulseAudio for the user (audio capture needs it)
        self._start_pulseaudio(session)

        # Start window manager (gnome-shell needs D-Bus ready)
        if self._wm_cmd:
            if self._wm_cmd[0] == "gnome-shell":
                # Give D-Bus and Xvfb time to fully initialize
                time.sleep(1)
            self._start_window_manager(session)

        self._sessions[username] = session
        return session

    def _demote(self, uid: int, gid: int):
        """preexec_fn to drop privileges to a user."""
        os.setgid(gid)
        os.initgroups(pwd.getpwuid(uid).pw_name, gid)
        os.setuid(uid)

    def _start_dbus(self, session: UserSession):
        try:
            bus_path = f"/run/user/{session.uid}/bus"
            session.dbus_proc = subprocess.Popen(
                ["dbus-daemon", "--session", "--nofork",
                 f"--address=unix:path={bus_path}"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                preexec_fn=lambda: self._demote(session.uid, session.gid),
                env=session.env)
            logger.info("D-Bus started for %s", session.username)
        except Exception as e:
            logger.warning("D-Bus failed for %s: %s", session.username, e)

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
        except Exception as e:
            logger.warning("WM failed for %s: %s", session.username, e)

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
            env = {"DISPLAY": display}

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
        for name, proc in [("WM", session.wm_proc),
                           ("PulseAudio", session.pulseaudio_proc),
                           ("D-Bus", session.dbus_proc),
                           ("Xvfb", session.xvfb_proc)]:
            if proc and proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=2)
                logger.debug("Stopped %s (pid %d) for %s",
                             name, proc.pid, session.username)

        if session.xauthority and os.path.exists(session.xauthority):
            try:
                os.unlink(session.xauthority)
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
