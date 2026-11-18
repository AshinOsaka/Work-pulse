"""Idle detection.

Uses `GetLastInputInfo`, which reports only *when* the last keyboard or mouse
input happened. No input content, keys or pointer positions are read.
"""

from __future__ import annotations

import sys
from typing import Protocol


class IdleDetector(Protocol):
    def idle_seconds(self) -> float: ...


class WindowsIdleDetector:
    def __init__(self) -> None:
        import ctypes
        from ctypes import wintypes

        class LastInputInfo(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]

        self._info = LastInputInfo()
        self._info.cbSize = ctypes.sizeof(LastInputInfo)
        self._user32 = ctypes.WinDLL("user32")
        self._kernel32 = ctypes.WinDLL("kernel32")
        self._kernel32.GetTickCount.restype = wintypes.DWORD
        self._ctypes = ctypes

    def idle_seconds(self) -> float:
        if not self._user32.GetLastInputInfo(self._ctypes.byref(self._info)):
            return 0.0
        # Both values are 32-bit millisecond tick counts; mask handles the 49.7-day wrap-around.
        elapsed_ms = (int(self._kernel32.GetTickCount()) - int(self._info.dwTime)) & 0xFFFFFFFF
        return float(elapsed_ms) / 1000.0


class NullIdleDetector:
    """Fallback where idle time is unavailable: the user is always considered active."""

    def idle_seconds(self) -> float:
        return 0.0


def default_idle_detector() -> IdleDetector:
    return WindowsIdleDetector() if sys.platform == "win32" else NullIdleDetector()


#: The hooks missed input that Windows saw for longer than this: they stopped working, so they are reinstalled.
HOOK_STALE_SECONDS = 10.0
#: Hooks are reinstalled at most this often.
HOOK_RESTART_EVERY_SECONDS = 60.0


class RealInputIdleDetector:
    """Idle time that ignores input made by software (a mouse-mover app keeps a person idle, not active).

    Windows' last-input time also moves when software fakes input. The input monitor's hooks see the "made by
    software" flag on every event, so while they run, idle time is counted from the last *real* keyboard or mouse
    input. If the hooks stop working (Windows can remove them), this falls back to the Windows time, so a person is
    never shown idle because of a fault, and the hooks are reinstalled.
    """

    def __init__(self, system: IdleDetector, monitor: object, clock: object = None) -> None:
        import time

        self._system = system
        self._monitor = monitor
        self._clock = clock or time.monotonic
        #: Workspace setting: ignore software-made input (on by default).
        self.enabled = True
        self._last_restart = -1e9

    def idle_seconds(self) -> float:
        system_idle = self._system.idle_seconds()
        stats = getattr(self._monitor, "stats", None)
        if not self.enabled or stats is None or not getattr(self._monitor, "running", False):
            return system_idle
        real_idle, any_idle = stats.idle()
        if any_idle > system_idle + HOOK_STALE_SECONDS:
            # Windows saw input the hooks didn't: they are not working. Trust Windows and reinstall them.
            now = float(self._clock())  # type: ignore[operator]
            if now - self._last_restart >= HOOK_RESTART_EVERY_SECONDS:
                self._last_restart = now
                restart = getattr(self._monitor, "restart", None)
                if restart is not None:
                    import threading

                    threading.Thread(target=restart, name="wp-input-restart", daemon=True).start()
            return system_idle
        return float(max(system_idle, real_idle))
