"""Device identification.

The fingerprint is a SHA-256 of a stable machine identifier (Windows
MachineGuid) plus the hostname. Only the hash is sent; the raw identifier
never leaves the device. It lets the server recognise a re-installed agent on
the same machine instead of creating duplicate devices.
"""

from __future__ import annotations

import hashlib
import platform
import re
import socket
import sys
import uuid

from app import __version__


def machine_guid() -> str | None:
    if sys.platform != "win32":
        return None
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
            0,
            winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
        ) as key:
            value, _ = winreg.QueryValueEx(key, "MachineGuid")
            return str(value)
    except OSError:
        return None


def hostname() -> str:
    name = socket.gethostname() or "workstation"
    return re.sub(r"[^A-Za-z0-9.\-_]", "-", name)[:255]


def device_fingerprint() -> str:
    stable = machine_guid() or f"node-{uuid.getnode():012x}"
    return hashlib.sha256(f"workpulse:{stable}:{hostname().lower()}".encode()).hexdigest()


def os_name() -> str:
    return {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")


def os_version() -> str:
    if sys.platform == "win32":
        release, version, *_ = platform.win32_ver()
        return f"{release} ({version})"[:60]
    return f"{platform.system()} {platform.release()}"[:60]


def device_info() -> dict[str, str]:
    """Metadata sent at registration: nothing personal, nothing about usage."""
    host = hostname()
    return {
        "name": host,
        "hostname": host,
        "os": os_name(),
        "os_version": os_version(),
        "agent_version": __version__,
        "fingerprint": device_fingerprint(),
    }
