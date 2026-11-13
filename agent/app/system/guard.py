"""Keeps the agent running while the person is signed in to Windows, and says so when it was stopped.

Three visible, ordinary Windows mechanisms (nothing hidden):

* **Restart task.** A per-user Task Scheduler task, ``WorkPulse Agent (<user>)``, runs ``--watchdog`` every
  minute. That check is tiny (no agent code is loaded): if the agent isn't running it starts it, otherwise it
  exits at once. So End Task, Quit from the tray or a crash is undone within about a minute.
* **Run marker.** While running, the agent rewrites ``running.json`` every few seconds and deletes it when it
  closes properly. If the next start finds it, the agent stopped without closing. Windows sign-out and shut
  down also do that, so the marker is compared with the start of the current Windows session: only a stop
  while the person stayed signed in (End Task or a crash) is reported.
* **Start-up check.** "Start with Windows" switched off (Task Manager → Startup apps, Settings, or the
  tray) and a deleted or disabled restart task are reported, and the task is recreated.

An installer run (an update or a reinstall) leaves an ``updating`` note first, so the restart task waits and
the next start does not report the installer closing the agent.
"""

from __future__ import annotations

import contextlib
import getpass
import json
import logging
import os
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

logger = logging.getLogger(__name__)

RUN_MARKER = "running.json"
UPDATING_MARKER = "updating"
STATE_FILE = "guard.json"
#: How long an installer's "updating" note holds off the restart task and the stop report.
UPDATING_MAX_AGE = 30 * 60
#: How often the run marker is rewritten (the reported stop time is accurate to about this).
TOUCH_SECONDS = 15.0
#: How often the restart task and start-up setting are checked.
CHECK_SECONDS = 300.0

STARTUP_APPROVED_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"
CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_BREAKAWAY_FROM_JOB = 0x01000000
NORMAL_PRIORITY_CLASS = 0x00000020


# --------------------------------------------------------------------------- the restart task
def task_name() -> str:
    """Per user, so several people on one computer each have their own (user names can't contain \\ / : * ? ")."""
    return f"WorkPulse Agent ({getpass.getuser()})"


def task_xml(exe: Path) -> str:
    """Every minute, while this person is signed in; on battery too; never stopped for running long."""
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Author>WorkPulse</Author>
    <Description>Starts WorkPulse again within a minute if it is closed. Removed when WorkPulse is uninstalled.</Description>
  </RegistrationInfo>
  <Triggers>
    <TimeTrigger>
      <Repetition>
        <Interval>PT1M</Interval>
        <StopAtDurationEnd>false</StopAtDurationEnd>
      </Repetition>
      <StartBoundary>2026-01-01T00:00:00</StartBoundary>
      <Enabled>true</Enabled>
    </TimeTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>false</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <RunOnlyIfIdle>false</RunOnlyIfIdle>
    <WakeToRun>false</WakeToRun>
    <ExecutionTimeLimit>PT2M</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{escape(str(exe))}</Command>
      <Arguments>--watchdog</Arguments>
    </Exec>
  </Actions>
</Task>
"""


def _schtasks(*args: str) -> subprocess.CompletedProcess[str]:
    program = Path(os.environ.get("SYSTEMROOT", r"C:\Windows")) / "System32" / "schtasks.exe"
    return subprocess.run(  # noqa: S603 - Windows' own Task Scheduler tool, fixed arguments
        [str(program), *args],
        capture_output=True,
        text=True,
        timeout=20,
        creationflags=CREATE_NO_WINDOW,
        check=False,
    )


def restart_task_state(exe: Path) -> str:
    """``ok``, ``missing``, ``disabled`` or ``outdated`` (points at another program, e.g. after a reinstall)."""
    result = _schtasks("/Query", "/TN", task_name(), "/XML")
    if result.returncode != 0:
        return "missing"
    xml = result.stdout
    settings = xml.split("<Settings>", 1)[-1].split("</Settings>", 1)[0]
    if "<Enabled>false</Enabled>" in settings or "<Enabled>false</Enabled>" in xml.split("<Settings>", 1)[0]:
        return "disabled"
    if escape(str(exe)).lower() not in xml.lower() or "--watchdog" not in xml:
        return "outdated"
    return "ok"


def register_restart_task(exe: Path) -> bool:
    """Create (or replace) the task. Ordinary per-user task: no administrator rights needed."""
    fd, name = tempfile.mkstemp(suffix=".xml")
    os.close(fd)
    path = Path(name)
    try:
        path.write_text(task_xml(exe), encoding="utf-16")
        result = _schtasks("/Create", "/TN", task_name(), "/XML", str(path), "/F")
    finally:
        with contextlib.suppress(OSError):
            path.unlink()
    if result.returncode != 0:
        logger.warning("Could not create the restart task: %s", (result.stderr or result.stdout).strip()[:300])
        return False
    logger.info("Restart task registered: %s", task_name())
    return True


def remove_restart_task() -> None:
    """Signed out of WorkPulse: nothing to keep running."""
    with contextlib.suppress(Exception):
        if _schtasks("/Delete", "/TN", task_name(), "/F").returncode == 0:
            logger.info("Restart task removed")


# --------------------------------------------------------------------------- start with Windows
def startup_switched_off(run_value: Callable[[], str | None]) -> bool:
    """The Run entry is gone, or Windows' own Startup apps switch for it is off."""
    if sys.platform != "win32":
        return False
    if run_value() is None:
        return True
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, STARTUP_APPROVED_KEY) as key:
            data, _ = winreg.QueryValueEx(key, "WorkPulseAgent")
    except OSError:
        return False  # never touched in Startup apps: enabled
    # The first byte is even (02, 06) when enabled and odd (03, 07) when switched off.
    return bool(data) and isinstance(data, bytes) and data[0] % 2 == 1


# --------------------------------------------------------------------------- how the last run ended
@dataclass(frozen=True)
class PreviousRun:
    started_at: float
    last_alive: float


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _write_json(path: Path, data: dict[str, Any]) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    os.replace(tmp, path)


def mark_updating(data_dir: Path) -> None:
    """An update or reinstall is about to close the agent: hold the restart task and the stop report."""
    with contextlib.suppress(OSError):
        data_dir.mkdir(parents=True, exist_ok=True)
        (data_dir / UPDATING_MARKER).write_text(str(time.time()), encoding="utf-8")


def updating_recently(data_dir: Path, now: float | None = None) -> bool:
    path = data_dir / UPDATING_MARKER
    try:
        text = path.read_text(encoding="utf-8").strip()
        written = float(text) if text else path.stat().st_mtime  # the installer writes no time: use the file's
    except (OSError, ValueError):
        return False
    # A little leeway either way for clock and file-time differences.
    return -60 <= (now or time.time()) - written <= UPDATING_MAX_AGE


def session_logon_time() -> float | None:
    """When the current Windows session was signed in to (Unix time), or None if unknown."""
    if sys.platform != "win32":
        return None
    import ctypes
    from ctypes import wintypes

    class WTSINFOW(ctypes.Structure):
        _fields_ = [
            ("State", ctypes.c_int),
            ("SessionId", wintypes.DWORD),
            ("IncomingBytes", wintypes.DWORD),
            ("OutgoingBytes", wintypes.DWORD),
            ("IncomingFrames", wintypes.DWORD),
            ("OutgoingFrames", wintypes.DWORD),
            ("IncomingCompressedBytes", wintypes.DWORD),
            ("OutgoingCompressedBytes", wintypes.DWORD),
            ("WinStationName", wintypes.WCHAR * 32),
            ("Domain", wintypes.WCHAR * 17),
            ("UserName", wintypes.WCHAR * 21),
            ("ConnectTime", ctypes.c_longlong),
            ("DisconnectTime", ctypes.c_longlong),
            ("LastInputTime", ctypes.c_longlong),
            ("LogonTime", ctypes.c_longlong),
            ("CurrentTime", ctypes.c_longlong),
        ]

    try:
        wtsapi = ctypes.WinDLL("wtsapi32")
        buffer = ctypes.c_void_p()
        size = wintypes.DWORD()
        wts_session_info = 24
        if not wtsapi.WTSQuerySessionInformationW(
            None, wintypes.DWORD(0xFFFFFFFF), wts_session_info, ctypes.byref(buffer), ctypes.byref(size)
        ):
            return None
        try:
            if size.value < ctypes.sizeof(WTSINFOW):
                return None
            filetime = int(ctypes.cast(buffer, ctypes.POINTER(WTSINFOW)).contents.LogonTime)
        finally:
            wtsapi.WTSFreeMemory(buffer)
    except (OSError, AttributeError, ValueError):
        return None
    if filetime <= 0:
        return None
    return (filetime - 116_444_736_000_000_000) / 10_000_000


def stopped_unexpectedly(previous: PreviousRun, logon_time: float | None) -> bool:
    """True when the agent died while the person stayed signed in to Windows (End Task or a crash).

    A Windows sign-out or shut down ends the session, so the current one started after the marker's last
    write. Sleep keeps the agent running, so it never leaves a marker behind. Unknown logon time: say nothing.
    """
    if logon_time is None:
        return False
    return logon_time < previous.last_alive


# --------------------------------------------------------------------------- the 1-minute check
def watchdog_main(data_dir: Path, exe: Path, is_running: Callable[[], bool]) -> int:
    """Run by the restart task. Loads no agent code: start the agent if it isn't running, then exit."""
    if updating_recently(data_dir):
        return 0  # an installer is replacing the files
    if is_running():
        return 0
    flags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | NORMAL_PRIORITY_CLASS
    command = [str(exe), "--minimized", "--restarted"]
    try:
        # Out of Task Scheduler's job, so the agent is an ordinary process like one started at sign-in.
        subprocess.Popen(command, creationflags=flags | CREATE_BREAKAWAY_FROM_JOB, close_fds=True)  # noqa: S603
    except OSError:
        subprocess.Popen(command, creationflags=flags, close_fds=True)  # noqa: S603
    return 0


# --------------------------------------------------------------------------- the running agent's side
@dataclass
class GuardHooks:
    """The Windows side, replaceable in tests."""

    exe: Path | None  # the installed agent; None = no restart task (development, headless, single-file)
    task_state: Callable[[Path], str] = restart_task_state
    register_task: Callable[[Path], bool] = register_restart_task
    remove_task: Callable[[], None] = remove_restart_task
    startup_off: Callable[[], bool] = lambda: False
    logon_time: Callable[[], float | None] = session_logon_time


class AgentGuard:
    """The running agent's side: the run marker, and the restart task / start-up checks."""

    def __init__(self, data_dir: Path, hooks: GuardHooks, emit: Callable[[str, dict[str, Any]], None]) -> None:
        self._dir = data_dir
        self._hooks = hooks
        self._emit = emit
        self._last_check = 0.0
        self._quiet = False

    # -- start-up
    def take_previous_end(self, now: float) -> PreviousRun | None:
        """Reads (and clears) the last run's marker. Returns it when that run stopped unexpectedly."""
        marker = self._dir / RUN_MARKER
        data = _read_json(marker)
        with contextlib.suppress(OSError):
            marker.unlink()
        updating = updating_recently(self._dir, now)
        # Just installed or updated: repair quietly, and the installer closing the agent is not reported.
        self._quiet = updating
        with contextlib.suppress(OSError):
            (self._dir / UPDATING_MARKER).unlink()
        if not data or updating:
            return None
        try:
            previous = PreviousRun(float(data["started_at"]), float(data["last_alive"]))
        except (KeyError, TypeError, ValueError):
            return None
        if previous.last_alive > now:
            return None
        return previous if stopped_unexpectedly(previous, self._hooks.logon_time()) else None

    # -- while running (about every TOUCH_SECONDS)
    def tick(self, signed_in: bool, now: float) -> None:
        if not signed_in:
            self.clear()
            return
        marker = self._dir / RUN_MARKER
        started = (_read_json(marker) or {}).get("started_at", now)
        with contextlib.suppress(OSError):
            _write_json(marker, {"pid": os.getpid(), "started_at": started, "last_alive": now})
        if now - self._last_check >= CHECK_SECONDS:
            self._last_check = now
            self.check(now)

    def check(self, now: float) -> None:
        """Repair the restart task and report anything switched off (once per change, not every start)."""
        state = _read_json(self._dir / STATE_FILE) or {}
        problems: dict[str, bool] = {}
        exe = self._hooks.exe
        if exe is not None:
            task = self._hooks.task_state(exe)
            if task != "ok":
                self._hooks.register_task(exe)
            problems["restart_task_removed"] = task == "missing"
            problems["restart_task_disabled"] = task == "disabled"
            problems["startup_disabled"] = self._hooks.startup_off()
        for what, now_bad in problems.items():
            if now_bad and not state.get(what) and not self._quiet:
                self._emit(what, {"at": now})
                logger.warning("Reported: %s", what)
            state[what] = now_bad
        self._quiet = False
        with contextlib.suppress(OSError):
            _write_json(self._dir / STATE_FILE, state)

    def wake_check(self) -> None:
        """Check on the next tick (e.g. just signed in)."""
        self._last_check = 0.0

    # -- closing
    def clear(self) -> None:
        """Closed properly (or signed out): the next start has nothing to report."""
        with contextlib.suppress(OSError):
            (self._dir / RUN_MARKER).unlink()

    def signed_out(self) -> None:
        self.clear()
        if self._hooks.exe is not None:
            self._hooks.remove_task()
        with contextlib.suppress(OSError):
            (self._dir / STATE_FILE).unlink()
