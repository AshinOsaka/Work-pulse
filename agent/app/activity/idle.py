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
