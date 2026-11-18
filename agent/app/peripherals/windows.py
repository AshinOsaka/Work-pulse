"""What is plugged into this computer, read from Windows (device names and types only).

* Devices (mouse, keyboard, phone, camera, headset): Windows' device list (SetupAPI), one class at a time.
* USB storage (pen drives, external disks, memory cards): the drive letters whose disk is on USB or a card reader,
  with the disk's maker and model, its size and its volume name.

Nothing on the devices is opened or read here. The device's own ID (which can contain a serial number) is never sent:
only a short one-way fingerprint of it, so the same device is recognised again.
"""

from __future__ import annotations

import hashlib
import logging
import re
import sys
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Peripheral:
    #: Short one-way fingerprint: the same device always gets the same key.
    key: str
    kind: str  # storage | phone | mouse | keyboard | camera | audio
    name: str
    #: USB vendor and product ids ("046D:C077"), when the device has them.
    hardware_id: str | None = None
    #: Storage only: drive letter ("E:"), total size in bytes, volume name.
    drive: str | None = None
    size_bytes: int | None = None
    label: str | None = None


def fingerprint(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8", "replace")).hexdigest()[:20]


_VID_PID = re.compile(r"VID_([0-9A-F]{4}).*?PID_([0-9A-F]{4})", re.IGNORECASE)


def hardware_id(instance_id: str) -> str | None:
    match = _VID_PID.search(instance_id)
    return f"{match.group(1).upper()}:{match.group(2).upper()}" if match else None


# Device setup classes (GUIDs are fixed by Windows).
CLASSES: dict[str, str] = {
    "{4d36e96f-e325-11ce-bfc1-08002be10318}": "mouse",
    "{4d36e96b-e325-11ce-bfc1-08002be10318}": "keyboard",
    "{eec5ad98-8080-425f-922a-dabf3de3f69a}": "phone",  # portable devices (phones over MTP)
    "{3f966bd9-fa04-4ec5-991c-d326973b5128}": "phone",  # Android USB (ADB)
    "{ca3e7ab9-b4c3-4ae6-8251-579ef933890f}": "camera",
    "{6bdd1fc6-810f-11d0-bec7-08002be2092f}": "camera",  # imaging devices
    "{4d36e96c-e325-11ce-bfc1-08002be10318}": "audio",  # sound, video and game controllers
}

#: Bus types that mean a removable disk: USB, SD and MMC card readers.
_REMOVABLE_BUSES = {7, 0x0C, 0x0D}


class WindowsPeripherals:
    def __init__(self) -> None:
        import ctypes
        from ctypes import wintypes

        self._ct = ctypes
        self._wt = wintypes
        self._setupapi = ctypes.WinDLL("setupapi", use_last_error=True)
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        class GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", wintypes.DWORD),
                ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8),
            ]

        class SpDevinfoData(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("ClassGuid", GUID),
                ("DevInst", wintypes.DWORD),
                ("Reserved", ctypes.c_size_t),
            ]

        self._GUID = GUID
        self._SpDevinfoData = SpDevinfoData
        handle = ctypes.c_void_p
        s = self._setupapi
        s.SetupDiGetClassDevsW.argtypes = [ctypes.POINTER(GUID), wintypes.LPCWSTR, wintypes.HWND, wintypes.DWORD]
        s.SetupDiGetClassDevsW.restype = handle
        s.SetupDiEnumDeviceInfo.argtypes = [handle, wintypes.DWORD, ctypes.POINTER(SpDevinfoData)]
        s.SetupDiEnumDeviceInfo.restype = wintypes.BOOL
        s.SetupDiGetDeviceRegistryPropertyW.argtypes = [
            handle, ctypes.POINTER(SpDevinfoData), wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
            ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
        ]  # fmt: skip
        s.SetupDiGetDeviceRegistryPropertyW.restype = wintypes.BOOL
        s.SetupDiGetDeviceInstanceIdW.argtypes = [
            handle, ctypes.POINTER(SpDevinfoData), wintypes.LPWSTR, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
        ]  # fmt: skip
        s.SetupDiGetDeviceInstanceIdW.restype = wintypes.BOOL
        s.SetupDiDestroyDeviceInfoList.argtypes = [handle]
        s.SetupDiDestroyDeviceInfoList.restype = wintypes.BOOL

        k = self._kernel32
        k.GetLogicalDrives.restype = wintypes.DWORD
        k.GetDriveTypeW.argtypes = [wintypes.LPCWSTR]
        k.GetDriveTypeW.restype = wintypes.UINT
        k.CreateFileW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
            wintypes.HANDLE,
        ]  # fmt: skip
        k.CreateFileW.restype = wintypes.HANDLE
        k.DeviceIoControl.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p,
        ]  # fmt: skip
        k.DeviceIoControl.restype = wintypes.BOOL
        k.CloseHandle.argtypes = [wintypes.HANDLE]
        k.GetVolumeInformationW.argtypes = [
            wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
            ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD), wintypes.LPWSTR, wintypes.DWORD,
        ]  # fmt: skip
        k.GetVolumeInformationW.restype = wintypes.BOOL
        k.GetDiskFreeSpaceExW.argtypes = [
            wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_ulonglong), ctypes.POINTER(ctypes.c_ulonglong),
            ctypes.POINTER(ctypes.c_ulonglong),
        ]  # fmt: skip
        k.GetDiskFreeSpaceExW.restype = wintypes.BOOL
        k.SetErrorMode.argtypes = [wintypes.UINT]
        k.SetErrorMode.restype = wintypes.UINT
        self._guids = {kind: self._guid(text) for text, kind in CLASSES.items()}
        self._guid_kinds = [(self._guid(text), kind) for text, kind in CLASSES.items()]

    def _guid(self, text: str) -> object:
        import uuid

        u = uuid.UUID(text)
        g = self._GUID()
        g.Data1, g.Data2, g.Data3 = u.time_low, u.time_mid, u.time_hi_version
        for i, b in enumerate(u.bytes[8:]):
            g.Data4[i] = b
        return g

    # ------------------------------------------------------------------ devices
    def _property(self, info: object, data: object, prop: int) -> str:
        ct = self._ct
        buf = ct.create_unicode_buffer(512)
        ok = self._setupapi.SetupDiGetDeviceRegistryPropertyW(
            info, ct.byref(data), prop, None, buf, ct.sizeof(buf), None
        )
        return str(buf.value).strip() if ok else ""

    def devices(self) -> list[Peripheral]:
        ct = self._ct
        found: dict[str, Peripheral] = {}
        digcf_present = 0x2
        for guid, kind in self._guid_kinds:
            info = self._setupapi.SetupDiGetClassDevsW(ct.byref(guid), None, None, digcf_present)
            if not info or info == ct.c_void_p(-1).value:
                continue
            try:
                index = 0
                while True:
                    data = self._SpDevinfoData()
                    data.cbSize = ct.sizeof(self._SpDevinfoData)
                    if not self._setupapi.SetupDiEnumDeviceInfo(info, index, ct.byref(data)):
                        break
                    index += 1
                    buf = ct.create_unicode_buffer(512)
                    if not self._setupapi.SetupDiGetDeviceInstanceIdW(info, ct.byref(data), buf, 512, None):
                        continue
                    instance = buf.value
                    enumerator = self._property(info, data, 0x16).upper()  # SPDRP_ENUMERATOR_NAME
                    if kind == "phone" and enumerator != "USB":
                        continue  # drive letters also appear as "portable devices"; phones come over USB
                    if kind == "audio" and not enumerator.startswith(("USB", "BTH")):
                        continue  # the computer's own sound card and software audio drivers
                    name = self._property(info, data, 0x0C) or self._property(info, data, 0x00)  # friendly / desc
                    hw = hardware_id(instance)
                    # One receiver can show up as several mice/keyboards: one entry per kind and product.
                    key = fingerprint(kind, hw) if hw else fingerprint(kind, instance)
                    if key not in found:
                        found[key] = Peripheral(key=key, kind=kind, name=(name or kind.title())[:120], hardware_id=hw)
            finally:
                self._setupapi.SetupDiDestroyDeviceInfoList(info)
        return list(found.values())

    # ------------------------------------------------------------------ USB storage
    def _disk(self, letter: str) -> tuple[int, str, str] | None:
        """(bus type, maker, model) of the disk behind a drive letter."""
        ct, wt, k = self._ct, self._wt, self._kernel32
        handle = k.CreateFileW(f"\\\\.\\{letter}:", 0, 0x1 | 0x2, None, 3, 0, None)
        if not handle or handle == wt.HANDLE(-1).value:
            return None
        try:
            query = (ct.c_uint32 * 3)(0, 0, 0)  # StorageDeviceProperty, PropertyStandardQuery
            out = ct.create_string_buffer(1024)
            returned = wt.DWORD()
            if not k.DeviceIoControl(handle, 0x002D1400, query, 12, out, 1024, ct.byref(returned), None):
                return None
            raw = out.raw[: returned.value]
            if len(raw) < 32:
                return None

            def dword(offset: int) -> int:
                return int.from_bytes(raw[offset : offset + 4], "little")

            def text(offset: int) -> str:
                if not offset or offset >= len(raw):
                    return ""
                end = raw.find(b"\0", offset)
                return str(raw[offset : end if end != -1 else len(raw)].decode("ascii", "replace")).strip()

            return dword(28), text(dword(12)), text(dword(16))
        finally:
            k.CloseHandle(handle)

    def volumes(self) -> list[Peripheral]:
        ct, wt, k = self._ct, self._wt, self._kernel32
        found: list[Peripheral] = []
        old_mode = k.SetErrorMode(0x0001 | 0x8000)  # no "insert a disk" pop-ups for empty card readers
        try:
            mask = k.GetLogicalDrives()
            for i in range(26):
                if not mask & (1 << i):
                    continue
                letter = chr(ord("A") + i)
                root = f"{letter}:\\"
                drive_type = k.GetDriveTypeW(root)
                if drive_type not in (2, 3):  # removable, fixed
                    continue
                disk = self._disk(letter)
                if drive_type == 3 and (disk is None or disk[0] not in _REMOVABLE_BUSES):
                    continue  # the computer's own disks
                label = ct.create_unicode_buffer(261)
                fs = ct.create_unicode_buffer(261)
                serial = wt.DWORD()
                if not k.GetVolumeInformationW(root, label, 261, ct.byref(serial), None, None, fs, 261):
                    continue  # an empty card reader
                total = ct.c_ulonglong()
                k.GetDiskFreeSpaceExW(root, None, ct.byref(total), None)
                maker, model = (disk[1], disk[2]) if disk else ("", "")
                name = " ".join(p for p in (maker, model) if p) or label.value or "USB drive"
                key = fingerprint("storage", f"{serial.value:08x}", maker, model, str(total.value))
                found.append(
                    Peripheral(
                        key=key,
                        kind="storage",
                        name=name[:120],
                        drive=f"{letter}:",
                        size_bytes=int(total.value) or None,
                        label=(label.value or None),
                    )
                )
        finally:
            k.SetErrorMode(old_mode)
        return found

    def all(self) -> list[Peripheral]:
        return self.volumes() + self.devices()


class NullPeripherals:
    def all(self) -> list[Peripheral]:
        return []


def default_peripherals() -> WindowsPeripherals | NullPeripherals:
    if sys.platform != "win32":
        return NullPeripherals()
    try:
        return WindowsPeripherals()
    except Exception:  # pragma: no cover - defensive
        logger.warning("Device list unavailable", exc_info=True)
        return NullPeripherals()
