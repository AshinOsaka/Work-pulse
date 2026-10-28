"""Counts keyboard and mouse events — how much, never which keys or where.

Only used when the workspace enables input metrics. A low-level Windows hook sees each event, but this
code reads nothing about it: it increments a counter and passes the event straight on. No key code, no
character, no mouse position, no window is read or stored. Key-down events are counted as keystrokes;
mouse button, wheel and (throttled) movement events are counted as mouse activity. The hooks run on
their own thread with a message pump, as Windows requires, and are removed the moment input metrics
are switched off.
"""

from __future__ import annotations

import logging
import sys
import threading
from typing import Protocol

logger = logging.getLogger(__name__)

#: At most one mouse-move is counted per this many seconds, so ordinary movement doesn't dwarf everything.
_MOVE_THROTTLE_SECONDS = 0.5


class InputCounter(Protocol):
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def snapshot(self) -> tuple[int, int]:
        """Cumulative (keyboard events, mouse events) since start."""
        ...


class NullInputCounter:
    """Used off Windows, or whenever input metrics are off: always zero, never hooks anything."""

    def start(self) -> None:
        return

    def stop(self) -> None:
        return

    def snapshot(self) -> tuple[int, int]:
        return 0, 0


class WindowsInputCounter:
    _WH_KEYBOARD_LL = 13
    _WH_MOUSE_LL = 14
    _WM_QUIT = 0x0012
    _WM_KEYDOWN = 0x0100
    _WM_SYSKEYDOWN = 0x0104
    _WM_MOUSEMOVE = 0x0200
    _WM_LBUTTONDOWN = 0x0201
    _WM_RBUTTONDOWN = 0x0204
    _WM_MBUTTONDOWN = 0x0207
    _WM_MOUSEWHEEL = 0x020A
    _WM_MOUSEHWHEEL = 0x020E

    def __init__(self, clock: object = None) -> None:
        import ctypes
        from ctypes import wintypes

        self._ct = ctypes
        self._wt = wintypes
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        import time as _time

        self._now = _time.monotonic
        self._keys = 0
        self._mouse = 0
        self._last_move = 0.0
        self._thread: threading.Thread | None = None
        self._thread_id = 0
        self._kb_handle = None
        self._mouse_handle = None
        # Keep references so the callbacks are not garbage-collected while hooked.
        self._proc_type = ctypes.CFUNCTYPE(
            ctypes.c_long, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
        )
        self._kb_proc = self._proc_type(self._on_keyboard)
        self._mouse_proc = self._proc_type(self._on_mouse)

    def _on_keyboard(self, code: int, wparam: int, lparam: int) -> int:
        if code >= 0 and wparam in (self._WM_KEYDOWN, self._WM_SYSKEYDOWN):
            self._keys += 1  # count only — the key code in lparam is never read
        return int(self._user32.CallNextHookEx(None, code, wparam, lparam))

    def _on_mouse(self, code: int, wparam: int, lparam: int) -> int:
        if code >= 0:
            if wparam == self._WM_MOUSEMOVE:
                now = self._now()
                if now - self._last_move >= _MOVE_THROTTLE_SECONDS:
                    self._last_move = now
                    self._mouse += 1
            elif wparam in (
                self._WM_LBUTTONDOWN,
                self._WM_RBUTTONDOWN,
                self._WM_MBUTTONDOWN,
                self._WM_MOUSEWHEEL,
                self._WM_MOUSEHWHEEL,
            ):
                self._mouse += 1  # the pointer position in lparam is never read
        return int(self._user32.CallNextHookEx(None, code, wparam, lparam))

    def _run(self) -> None:
        self._thread_id = self._kernel32.GetCurrentThreadId()
        module = self._kernel32.GetModuleHandleW(None)
        self._kb_handle = self._user32.SetWindowsHookExW(self._WH_KEYBOARD_LL, self._kb_proc, module, 0)
        self._mouse_handle = self._user32.SetWindowsHookExW(self._WH_MOUSE_LL, self._mouse_proc, module, 0)
        if not self._kb_handle or not self._mouse_handle:
            logger.warning("Input metrics: could not install hooks; counts will stay zero")
            return
        msg = self._wt.MSG()
        # Blocks until WM_QUIT is posted to this thread by stop().
        while self._user32.GetMessageW(self._ct.byref(msg), None, 0, 0) > 0:
            pass

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="wp-input-counter", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        thread = self._thread
        if thread is None:
            return
        if self._kb_handle:
            self._user32.UnhookWindowsHookEx(self._kb_handle)
            self._kb_handle = None
        if self._mouse_handle:
            self._user32.UnhookWindowsHookEx(self._mouse_handle)
            self._mouse_handle = None
        if self._thread_id:
            self._user32.PostThreadMessageW(self._thread_id, self._WM_QUIT, 0, 0)
        thread.join(timeout=2.0)
        self._thread = None
        self._thread_id = 0

    def snapshot(self) -> tuple[int, int]:
        return self._keys, self._mouse


def default_input_counter() -> InputCounter:
    if sys.platform != "win32":
        return NullInputCounter()
    try:
        return WindowsInputCounter()
    except Exception:  # pragma: no cover - defensive: any ctypes/loader issue falls back to no counting
        logger.warning("Input metrics unavailable; counts will stay zero", exc_info=True)
        return NullInputCounter()
