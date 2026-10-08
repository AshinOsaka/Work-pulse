"""Protection of the agent's master key at rest.

On Windows the key is wrapped with DPAPI (CryptProtectData, current-user
scope): only the same Windows user on the same machine can unwrap it, so a
copied data directory is useless elsewhere.

On other platforms (developer machines, CI) a key-file fallback is used; it
relies on file permissions and is not intended for production deployment.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Protocol

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class ProtectionError(Exception):
    pass


class Protector(Protocol):
    name: str

    def protect(self, data: bytes) -> bytes: ...

    def unprotect(self, data: bytes) -> bytes: ...


class DpapiProtector:
    """Windows Data Protection API (user scope) with application-specific entropy."""

    name = "dpapi"
    _ENTROPY = b"WorkPulse.Agent.v1"
    _CRYPTPROTECT_UI_FORBIDDEN = 0x01

    def __init__(self) -> None:
        if sys.platform != "win32":
            raise ProtectionError("DPAPI is only available on Windows")
        import ctypes
        from ctypes import wintypes

        class DataBlob(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]

        self._ct = ctypes
        self._DataBlob = DataBlob
        crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        signature: list[Any] = [
            ctypes.POINTER(DataBlob),  # pDataIn
            wintypes.LPCWSTR,  # szDataDescr
            ctypes.POINTER(DataBlob),  # pOptionalEntropy
            ctypes.c_void_p,  # pvReserved
            ctypes.c_void_p,  # pPromptStruct
            wintypes.DWORD,  # dwFlags
            ctypes.POINTER(DataBlob),  # pDataOut
        ]
        self._protect = crypt32.CryptProtectData
        self._protect.argtypes = signature
        self._protect.restype = wintypes.BOOL
        self._unprotect = crypt32.CryptUnprotectData
        self._unprotect.argtypes = [
            ctypes.POINTER(DataBlob),
            ctypes.POINTER(wintypes.LPWSTR),
            *signature[2:],
        ]
        self._unprotect.restype = wintypes.BOOL
        self._local_free = kernel32.LocalFree
        self._local_free.argtypes = [ctypes.c_void_p]

    def _blob(self, data: bytes):  # type: ignore[no-untyped-def]
        buffer = (self._ct.c_byte * len(data)).from_buffer_copy(data)
        return self._DataBlob(len(data), self._ct.cast(buffer, self._ct.POINTER(self._ct.c_byte))), buffer

    def _result(self, ok: int, out) -> bytes:  # type: ignore[no-untyped-def]
        if not ok:
            raise ProtectionError(f"DPAPI call failed (Windows error {self._ct.get_last_error()})")
        try:
            return self._ct.string_at(out.pbData, out.cbData)
        finally:
            self._local_free(out.pbData)

    def protect(self, data: bytes) -> bytes:
        source, _a = self._blob(data)
        entropy, _b = self._blob(self._ENTROPY)
        out = self._DataBlob()
        ok = self._protect(
            self._ct.byref(source),
            "WorkPulse agent key",
            self._ct.byref(entropy),
            None,
            None,
            self._CRYPTPROTECT_UI_FORBIDDEN,
            self._ct.byref(out),
        )
        return self._result(ok, out)

    def unprotect(self, data: bytes) -> bytes:
        source, _a = self._blob(data)
        entropy, _b = self._blob(self._ENTROPY)
        out = self._DataBlob()
        ok = self._unprotect(
            self._ct.byref(source),
            None,
            self._ct.byref(entropy),
            None,
            None,
            self._CRYPTPROTECT_UI_FORBIDDEN,
            self._ct.byref(out),
        )
        return self._result(ok, out)


class KeyFileProtector:
    """Non-Windows fallback: wraps data with a key stored in a 0600 file."""

    name = "keyfile"

    def __init__(self, key_path: Path) -> None:
        if key_path.exists():
            self._key = key_path.read_bytes()
        else:
            key_path.parent.mkdir(parents=True, exist_ok=True)
            self._key = AESGCM.generate_key(bit_length=256)
            fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as handle:
                handle.write(self._key)

    def protect(self, data: bytes) -> bytes:
        nonce = os.urandom(12)
        return nonce + AESGCM(self._key).encrypt(nonce, data, b"workpulse-keyfile")

    def unprotect(self, data: bytes) -> bytes:
        try:
            return AESGCM(self._key).decrypt(data[:12], data[12:], b"workpulse-keyfile")
        except Exception as exc:
            raise ProtectionError("Could not unwrap key") from exc


def default_protector(data_dir: Path) -> Protector:
    if sys.platform == "win32":
        return DpapiProtector()
    return KeyFileProtector(data_dir / ".wrapping-key")
