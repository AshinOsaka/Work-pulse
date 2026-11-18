"""Counts keyboard and mouse events — how much, never which keys or where.

A low-level Windows hook sees each event. This code reads only:

* the event type (key down, mouse move, button, wheel) — never the key code or character;
* the event's "injected" flag, which Windows sets when *software* made the input (a mouse-mover app, a remote-control
  tool, an on-screen keyboard) rather than a real keyboard or mouse;
* for mouse movement, how far the pointer travelled within the current minute (the width and height of the area it
  moved in). The positions themselves are never kept or sent; only that one size per minute is.

From this the agent keeps:

* counts of real key presses and mouse events (sent only when the workspace enables input metrics);
* the time of the last *real* input, so software that fakes mouse movement doesn't count as being active;
* one small summary per minute (seconds with movement, clicks, key presses, movement area, software input) used to
  notice automated movement: a mouse-mover app, or a mouse moved by a device or object instead of a hand.

The hooks run on their own thread with a message pump, as Windows requires.
"""

from __future__ import annotations

import logging
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Protocol

logger = logging.getLogger(__name__)

#: At most one mouse-move is counted per this many seconds, so ordinary movement doesn't dwarf everything.
_MOVE_THROTTLE_SECONDS = 0.5
#: Finished minutes kept for the pattern check (older ones are dropped if nobody reads them).
_KEEP_MINUTES = 30


@dataclass
class MinuteStats:
    """One minute of input, as numbers only."""

    #: Minute number (monotonic seconds // 60): consecutive minutes have consecutive numbers.
    index: int
    #: Wall-clock time the minute's first event happened.
    started_at: float
    #: Seconds in this minute with real mouse movement (0–60).
    move_seconds: int = 0
    #: Real mouse button presses and wheel turns.
    clicks: int = 0
    #: Real key presses.
    keys: int = 0
    #: Seconds in this minute with software-made (injected) input.
    injected_seconds: int = 0
    #: Width and height of the area the real pointer moved in during this minute, in pixels.
    span_x: int = 0
    span_y: int = 0
    _last_move_second: int = field(default=-1, repr=False)
    _last_injected_second: int = field(default=-1, repr=False)
    _min_x: int | None = field(default=None, repr=False)
    _max_x: int = field(default=0, repr=False)
    _min_y: int = field(default=0, repr=False)
    _max_y: int = field(default=0, repr=False)

    @property
    def span(self) -> int:
        return max(self.span_x, self.span_y)


class InputStats:
    """The counting itself, free of Windows: the hook calls these, tests call them directly."""

    def __init__(self, mono: object = None, wall: object = None) -> None:
        self._mono = mono or time.monotonic
        self._wall = wall or time.time
        self.keys = 0
        self.mouse = 0
        self._last_move = -1e9
        now = self._now()
        #: Monotonic time of the last real input, and of the last input of any kind (real or software).
        self.last_real = now
        self.last_any = now
        #: Monotonic time of the last real key press or click (a person at the computer, not a moving mouse).
        self.last_action = -1e9
        self._minute: MinuteStats | None = None
        self._done: deque[MinuteStats] = deque(maxlen=_KEEP_MINUTES)
        self._lock = threading.Lock()

    def _now(self) -> float:
        value: float = self._mono()  # type: ignore[operator]
        return value

    def _bucket(self, now: float) -> MinuteStats:
        index = int(now // 60)
        minute = self._minute
        if minute is None or minute.index != index:
            if minute is not None:
                self._done.append(minute)
            wall: float = self._wall()  # type: ignore[operator]
            minute = self._minute = MinuteStats(index=index, started_at=wall)
        return minute

    def _injected(self, minute: MinuteStats, now: float) -> None:
        second = int(now)
        if second != minute._last_injected_second:
            minute._last_injected_second = second
            minute.injected_seconds += 1

    def key(self, injected: bool) -> None:
        now = self._now()
        with self._lock:
            self.last_any = now
            minute = self._bucket(now)
            if injected:
                self._injected(minute, now)
                return
            self.keys += 1
            self.last_real = self.last_action = now
            minute.keys += 1

    def click(self, injected: bool) -> None:
        now = self._now()
        with self._lock:
            self.last_any = now
            minute = self._bucket(now)
            if injected:
                self._injected(minute, now)
                return
            self.mouse += 1
            self.last_real = self.last_action = now
            minute.clicks += 1

    def move(self, injected: bool, x: int, y: int) -> None:
        now = self._now()
        with self._lock:
            self.last_any = now
            minute = self._bucket(now)
            if injected:
                self._injected(minute, now)
                return
            self.last_real = now
            if now - self._last_move >= _MOVE_THROTTLE_SECONDS:
                self._last_move = now
                self.mouse += 1
            second = int(now)
            if second != minute._last_move_second:
                minute._last_move_second = second
                minute.move_seconds += 1
            if minute._min_x is None:
                minute._min_x, minute._max_x, minute._min_y, minute._max_y = x, x, y, y
            else:
                minute._min_x = min(minute._min_x, x)
                minute._max_x = max(minute._max_x, x)
                minute._min_y = min(minute._min_y, y)
                minute._max_y = max(minute._max_y, y)
            minute.span_x = minute._max_x - minute._min_x
            minute.span_y = minute._max_y - minute._min_y

    # ------------------------------------------------------------------ readers
    def minute_index(self) -> int:
        return int(self._now() // 60)

    def take_minutes(self) -> list[MinuteStats]:
        """Finished minutes since the last call (the current minute is still open)."""
        now = self._now()
        with self._lock:
            minute = self._minute
            if minute is not None and minute.index != int(now // 60):
                self._done.append(minute)
                self._minute = None
            done = list(self._done)
            self._done.clear()
        return done

    def idle(self) -> tuple[float, float]:
        """(seconds since the last real input, seconds since the last input of any kind)."""
        now = self._now()
        return max(0.0, now - self.last_real), max(0.0, now - self.last_any)

    def seconds_since_action(self) -> float:
        return max(0.0, self._now() - self.last_action)


class InputCounter(Protocol):
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def snapshot(self) -> tuple[int, int]:
        """Cumulative (keyboard events, mouse events) since start."""
        ...


class NullInputCounter:
    """Used off Windows, or whenever nothing needs the hooks: always zero, never hooks anything."""

    stats: InputStats | None = None

    @property
    def running(self) -> bool:
        return False

    def start(self) -> None:
        return

    def stop(self) -> None:
        return

    def restart(self) -> None:
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
    _WM_XBUTTONDOWN = 0x020B
    _WM_MOUSEWHEEL = 0x020A
    _WM_MOUSEHWHEEL = 0x020E
    #: "Made by software" flags: LLKHF_INJECTED / LLKHF_LOWER_IL_INJECTED and LLMHF_INJECTED / LLMHF_LOWER_IL_INJECTED.
    _KEY_INJECTED = 0x10 | 0x02
    _MOUSE_INJECTED = 0x01 | 0x02

    def __init__(self) -> None:
        import ctypes
        from ctypes import wintypes

        self._ct = ctypes
        self._wt = wintypes
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        # Full 64-bit types for handles and pointers. Without them ctypes passes and returns 32-bit ints,
        # which cut the module handle in half, so Windows refused the hooks and every count stayed zero.
        lresult = ctypes.c_ssize_t
        self._proc_type = ctypes.WINFUNCTYPE(lresult, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
        self._kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        self._kernel32.GetModuleHandleW.restype = wintypes.HMODULE
        self._kernel32.GetCurrentThreadId.restype = wintypes.DWORD
        self._user32.SetWindowsHookExW.argtypes = [ctypes.c_int, self._proc_type, wintypes.HINSTANCE, wintypes.DWORD]
        self._user32.SetWindowsHookExW.restype = wintypes.HHOOK
        self._user32.CallNextHookEx.argtypes = [wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
        self._user32.CallNextHookEx.restype = lresult
        self._user32.UnhookWindowsHookEx.argtypes = [wintypes.HHOOK]
        self._user32.UnhookWindowsHookEx.restype = wintypes.BOOL
        self._user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
        self._user32.GetMessageW.restype = wintypes.BOOL
        self._user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        self._user32.PostThreadMessageW.restype = wintypes.BOOL

        self.stats = InputStats()
        self._thread: threading.Thread | None = None
        self._thread_id = 0
        self._kb_handle = None
        self._mouse_handle = None
        self._lock = threading.Lock()
        # Keep references so the callbacks are not garbage-collected while hooked.
        self._kb_proc = self._proc_type(self._on_keyboard)
        self._mouse_proc = self._proc_type(self._on_mouse)

    def _dword(self, address: int, offset: int) -> int:
        return int(self._ct.c_uint32.from_address(address + offset).value)

    def _int(self, address: int, offset: int) -> int:
        return int(self._ct.c_int32.from_address(address + offset).value)

    def _on_keyboard(self, code: int, wparam: int, lparam: int) -> int:
        try:
            if code >= 0 and wparam in (self._WM_KEYDOWN, self._WM_SYSKEYDOWN):
                # KBDLLHOOKSTRUCT: only `flags` (offset 8) is read — never the key code at offset 0.
                self.stats.key(bool(self._dword(lparam, 8) & self._KEY_INJECTED))
        except Exception:  # pragma: no cover - a hook must never raise
            logger.debug("keyboard hook", exc_info=True)
        return int(self._user32.CallNextHookEx(None, code, wparam, lparam))

    def _on_mouse(self, code: int, wparam: int, lparam: int) -> int:
        try:
            if code >= 0:
                # MSLLHOOKSTRUCT: pt.x (0), pt.y (4), mouseData (8), flags (12).
                injected = bool(self._dword(lparam, 12) & self._MOUSE_INJECTED)
                if wparam == self._WM_MOUSEMOVE:
                    self.stats.move(injected, self._int(lparam, 0), self._int(lparam, 4))
                elif wparam in (
                    self._WM_LBUTTONDOWN,
                    self._WM_RBUTTONDOWN,
                    self._WM_MBUTTONDOWN,
                    self._WM_XBUTTONDOWN,
                    self._WM_MOUSEWHEEL,
                    self._WM_MOUSEHWHEEL,
                ):
                    self.stats.click(injected)
        except Exception:  # pragma: no cover - a hook must never raise
            logger.debug("mouse hook", exc_info=True)
        return int(self._user32.CallNextHookEx(None, code, wparam, lparam))

    def _run(self) -> None:
        self._thread_id = self._kernel32.GetCurrentThreadId()
        module = self._kernel32.GetModuleHandleW(None)
        self._kb_handle = self._user32.SetWindowsHookExW(self._WH_KEYBOARD_LL, self._kb_proc, module, 0)
        self._mouse_handle = self._user32.SetWindowsHookExW(self._WH_MOUSE_LL, self._mouse_proc, module, 0)
        if not self._kb_handle or not self._mouse_handle:
            logger.warning("Input monitor: could not install hooks (error %s)", self._ct.get_last_error())
            return
        logger.info("Input monitor: running")
        msg = self._wt.MSG()
        # Blocks until WM_QUIT is posted to this thread by stop().
        while self._user32.GetMessageW(self._ct.byref(msg), None, 0, 0) > 0:
            pass

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive() and self._kb_handle and self._mouse_handle)

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._thread = threading.Thread(target=self._run, name="wp-input-counter", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        with self._lock:
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

    def restart(self) -> None:
        """Windows silently removes a hook that once answered too slowly; installing it again brings it back."""
        logger.info("Input monitor: reinstalling the hooks")
        self.stop()
        self.start()

    def snapshot(self) -> tuple[int, int]:
        return self.stats.keys, self.stats.mouse


def default_input_counter() -> InputCounter:
    if sys.platform != "win32":
        return NullInputCounter()
    try:
        return WindowsInputCounter()
    except Exception:  # pragma: no cover - defensive: any ctypes/loader issue falls back to no counting
        logger.warning("Input monitor unavailable", exc_info=True)
        return NullInputCounter()
