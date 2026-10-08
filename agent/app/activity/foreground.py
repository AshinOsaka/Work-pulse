"""Which application is in the foreground.

Reads only: the foreground window's process executable, the executable's
product description (for a friendly name), and — only when the caller asks,
i.e. when the policy permits it — the window title. Nothing is read from the
window's contents, and no input is observed.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.activity.privacy import is_sensitive
from app.activity.websites import BROWSERS, read_domain


@dataclass(frozen=True, slots=True)
class ForegroundApp:
    app_id: str  # executable name, lower case, e.g. "code.exe"
    app_name: str  # display name, e.g. "Visual Studio Code"
    title: str | None = None
    #: Host name of the active browser tab, only when requested (website tracking on).
    domain: str | None = None


class ForegroundProbe(Protocol):
    def current(self, include_title: bool, include_domain: bool = False) -> ForegroundApp | None: ...


class WindowsForegroundProbe:
    _PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

    def __init__(self) -> None:
        import ctypes
        from ctypes import wintypes

        self._ct = ctypes
        self._wt = wintypes
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._version = ctypes.WinDLL("version", use_last_error=True)
        self._user32.GetForegroundWindow.restype = wintypes.HWND
        self._user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
        self._user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
        self._user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        self._kernel32.OpenProcess.restype = wintypes.HANDLE
        self._kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        self._kernel32.QueryFullProcessImageNameW.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)
        ]  # fmt: skip
        self._kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        self._names: dict[str, str] = {}

    def current(self, include_title: bool, include_domain: bool = False) -> ForegroundApp | None:
        hwnd = self._user32.GetForegroundWindow()
        if not hwnd:
            return None
        pid = self._wt.DWORD()
        self._user32.GetWindowThreadProcessId(hwnd, self._ct.byref(pid))
        path = self._image_path(pid.value)
        if not path:
            return None
        app_id = Path(path).name.lower()
        if path not in self._names:
            self._names[path] = self._describe(path) or Path(path).stem.replace("_", " ").title()
        title = self._title(hwnd) if include_title else None
        domain = None
        if include_domain and app_id in BROWSERS:
            # The title is read here only to recognise private windows; it is not kept unless requested.
            local_title = title if include_title else self._title(hwnd)
            if not is_sensitive(app_id, local_title):
                domain = read_domain(int(hwnd), local_title or "")
        return ForegroundApp(app_id=app_id[:64], app_name=self._names[path][:120], title=title, domain=domain)

    def _image_path(self, pid: int) -> str | None:
        handle = self._kernel32.OpenProcess(self._PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return None
        try:
            size = self._wt.DWORD(1024)
            buffer = self._ct.create_unicode_buffer(size.value)
            if not self._kernel32.QueryFullProcessImageNameW(handle, 0, buffer, self._ct.byref(size)):
                return None
            return str(buffer.value)
        finally:
            self._kernel32.CloseHandle(handle)

    def _title(self, hwnd: int) -> str | None:
        length = self._user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return None
        buffer = self._ct.create_unicode_buffer(length + 1)
        self._user32.GetWindowTextW(hwnd, buffer, length + 1)
        return str(buffer.value) or None

    def _describe(self, path: str) -> str | None:
        """The executable's FileDescription (e.g. 'Google Chrome'), from its version resource."""
        ct = self._ct
        size = self._version.GetFileVersionInfoSizeW(path, None)
        if not size:
            return None
        data = ct.create_string_buffer(size)
        if not self._version.GetFileVersionInfoW(path, 0, size, data):
            return None
        pointer, length = ct.c_void_p(), ct.c_uint()
        if (
            not self._version.VerQueryValueW(data, "\\VarFileInfo\\Translation", ct.byref(pointer), ct.byref(length))
            or not length.value
        ):
            return None
        lang, codepage = ct.cast(pointer, ct.POINTER(ct.c_ushort * 2)).contents
        key = f"\\StringFileInfo\\{lang:04x}{codepage:04x}\\FileDescription"
        if not self._version.VerQueryValueW(data, key, ct.byref(pointer), ct.byref(length)) or not length.value:
            return None
        description = ct.wstring_at(pointer.value, length.value).rstrip("\x00").strip()
        return description or None


class NullForegroundProbe:
    def current(self, include_title: bool, include_domain: bool = False) -> ForegroundApp | None:
        return None


def default_probe() -> ForegroundProbe:
    return WindowsForegroundProbe() if sys.platform == "win32" else NullForegroundProbe()
