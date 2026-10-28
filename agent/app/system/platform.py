"""OS integration: single instance, start-with-Windows, logging."""

from __future__ import annotations

import contextlib
import logging
import logging.handlers
import os
import shutil
import sys
from pathlib import Path
from typing import IO

logger = logging.getLogger(__name__)

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "WorkPulseAgent"

INSTALL_DIR_NAME = "WorkPulse"
INSTALLED_EXE_NAME = "WorkPulseAgent.exe"


class AlreadyRunningError(Exception):
    pass


class SingleInstance:
    """Holds an exclusive lock on a file in the data directory for the process lifetime."""

    def __init__(self, data_dir: Path) -> None:
        data_dir.mkdir(parents=True, exist_ok=True)
        self._handle: IO[bytes] | None = open(data_dir / "agent.lock", "a+b")  # noqa: SIM115 - held open on purpose
        try:
            if sys.platform == "win32":
                import msvcrt

                self._handle.seek(0)
                msvcrt.locking(self._handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self._handle.close()
            self._handle = None
            raise AlreadyRunningError("Another WorkPulse agent is already running for this user") from exc

    def release(self) -> None:
        if self._handle:
            self._handle.close()
            self._handle = None


def installed_exe_path() -> Path:
    """Stable per-user location the packaged agent copies itself to on first run.

    Registering sign-in start-up against the original download is fragile: if the
    employee moves the file out of Downloads, empties it, or it is cleaned up, the
    Run-key command points at a file that no longer exists and the agent silently
    stops auto-starting (so the admin sees them offline after a reboot). We instead
    keep a stable copy here and point start-up at it.
    """
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return Path(base) / INSTALL_DIR_NAME / INSTALLED_EXE_NAME


def ensure_installed() -> Path | None:
    """Copy the packaged agent into the stable per-user location (see above).

    Returns the installed path, or None when not applicable (not a frozen build, or
    not Windows). Never raises — a failed copy must not stop the agent starting.
    """
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return None
    try:
        current = Path(sys.executable).resolve()
        target = installed_exe_path()
        if current == target.resolve():
            return target  # already running from the installed copy
        target.parent.mkdir(parents=True, exist_ok=True)
        # Copy on first install, or when the running build differs (an upgrade).
        if not target.exists() or current.stat().st_size != target.stat().st_size:
            shutil.copy2(current, target)
            logger.info("Installed agent to stable location: %s", target)
        return target
    except OSError:
        logger.warning("Could not install the agent to a stable location", exc_info=True)
        return None


def autostart_command() -> str:
    """Command line registered to start the agent at sign-in."""
    if getattr(sys, "frozen", False):  # packaged executable (PyInstaller)
        # Prefer the stable installed copy so start-up survives the download moving.
        target = installed_exe_path()
        exe = target if target.exists() else Path(sys.executable)
        return f'"{exe}" --minimized'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    interpreter = pythonw if pythonw.exists() else Path(sys.executable)
    return f'"{interpreter}" -m app.main --minimized'


def autostart_enabled() -> bool:
    return _autostart_value() is not None


def _autostart_value() -> str | None:
    """The command currently registered to start the agent at sign-in, or None."""
    if sys.platform != "win32":
        return None
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, RUN_VALUE)
            return str(value)
    except OSError:
        return None


def ensure_autostart_registered() -> None:
    """Packaged build: install to the stable location and make sure sign-in start-up
    points at that copy. Safe to call on every launch; never raises.

    This both registers start-up on first run and *refreshes* a stale command — if an
    earlier version registered the download path and the download has since moved, the
    command is rewritten to the installed copy so the agent still starts at sign-in.
    """
    if not getattr(sys, "frozen", False):
        return
    with contextlib.suppress(Exception):
        ensure_installed()
        desired = autostart_command()
        if _autostart_value() != desired:
            set_autostart(True)


def set_autostart(enabled: bool) -> None:
    """Per-user 'start with Windows' (HKCU Run key; no administrator rights needed)."""
    if sys.platform != "win32":
        return
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ, autostart_command())
        else:
            with contextlib.suppress(FileNotFoundError):
                winreg.DeleteValue(key, RUN_VALUE)


def configure_logging(log_dir: Path, level: str, console: bool) -> None:
    """Rotating file log. Tokens, secrets and passwords are never logged."""
    log_dir.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [
        logging.handlers.RotatingFileHandler(log_dir / "agent.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    ]
    if console:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)-7s %(threadName)s %(name)s: %(message)s",
        handlers=handlers,
        force=True,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("PIL").setLevel(logging.WARNING)
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
