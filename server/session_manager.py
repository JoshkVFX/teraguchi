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
        (["xfce4-session"], "XFCE"),
        (["mate-session"], "MATE"),
        (["gnome-session"], "GNOME"),
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
        xvfb_cmd = [
            "Xvfb", display,
            "-screen", "0", f"{w}x{h}x{self.depth}",
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

        session = UserSession(
            username=username, uid=uid, gid=gid, home=home,
            display=display, display_num=display_num,
            width=w, height=h,
            xvfb_proc=xvfb_proc, xauthority=xauthority)

        # Start D-Bus session for the user
        self._start_dbus(session)

        # Start PulseAudio for the user (audio capture needs it)
        self._start_pulseaudio(session)

        # Start window manager
        if self._wm_cmd:
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

    def _start_window_manager(self, session: UserSession):
        try:
            session.wm_proc = subprocess.Popen(
                self._wm_cmd,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                preexec_fn=lambda: self._demote(session.uid, session.gid),
                env=session.env)
            logger.info("Window manager started for %s: %s",
                        session.username, self._wm_cmd[0])
        except Exception as e:
            logger.warning("WM failed for %s: %s", session.username, e)

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
