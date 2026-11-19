"""The file list of a phone plugged in for file transfer (MTP), read the way Windows Explorer shows it.

Phones don't get a drive letter, so their files are listed through the Windows shell ("This PC" → the phone →
"Internal shared storage"), only in the folders where copied files normally land: Download, Documents, Pictures,
Movies, Music, DCIM and the WhatsApp/Telegram document folders, a few levels deep. Names, sizes and dates only — no
file is opened or copied. A phone with a locked screen, or in "Charging only" mode, shows no files; that is
reported as nothing to list.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable
from datetime import datetime

from app.peripherals.files import FileInfo, Listing

logger = logging.getLogger(__name__)

#: Folders listed on each storage of the phone (top level, case-insensitive).
FOLDERS = {
    "download", "downloads", "documents", "pictures", "movies", "music", "dcim", "android", "whatsapp", "telegram",
    "bluetooth", "recordings", "whatsapp business",
}  # fmt: skip
#: Inside Android/media, only these apps' folders are listed (WhatsApp, Telegram keep received files there).
ANDROID_MEDIA = re.compile(r"^android/media/(com\.whatsapp|org\.telegram\.messenger)", re.IGNORECASE)
#: Files the phone makes by itself (photos, screenshots, recordings): never reported as copied from the computer.
PHONE_MADE = re.compile(r"(^|/)(dcim/camera|pictures/screenshots|dcim/screenshots|recordings)(/|$)", re.IGNORECASE)
MAX_DEPTH = 4
MAX_ENTRIES = 5_000
MAX_SECONDS = 15.0
_VID_PID = re.compile(r"vid_([0-9a-f]{4})&pid_([0-9a-f]{4})", re.IGNORECASE)


def hardware_id_of(shell_path: str) -> str | None:
    match = _VID_PID.search(shell_path)
    return f"{match.group(1).upper()}:{match.group(2).upper()}" if match else None


def _wanted(rel: str) -> bool:
    parts = rel.lower().split("/")
    if any(p.startswith(".") for p in parts):
        return False  # hidden folders and files (thumbnails, caches) the phone makes by itself
    if parts[0] not in FOLDERS:
        return False
    if parts[0] == "android":
        return len(parts) == 1 or (len(parts) >= 2 and parts[1] == "media" and (len(parts) == 2 or bool(ANDROID_MEDIA.match(rel))))
    return True


class ShellPhones:
    """Lists phones through Shell.Application (COM). Each call runs on the caller's thread."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock

    def _shell(self) -> object:
        import comtypes
        import comtypes.client

        comtypes.CoInitialize()
        return comtypes.client.CreateObject("Shell.Application", dynamic=True)

    def phones(self) -> dict[str, Listing]:
        """{USB id ("2717:FF48") or phone name: listing} for every phone shown under This PC."""
        found: dict[str, Listing] = {}
        try:
            shell = self._shell()
            this_pc = shell.NameSpace(17)  # type: ignore[attr-defined]
            items = this_pc.Items()
            for i in range(items.Count):
                item = items.Item(i)
                path = str(item.Path or "")
                if item.IsFileSystem or not item.IsFolder or "usb#vid_" not in path.lower():
                    continue
                key = hardware_id_of(path) or str(item.Name)
                found[key] = self._list_device(item.GetFolder)
        except Exception:
            logger.info("Phone file list not available", exc_info=True)
        return found

    def _list_device(self, device: object) -> Listing:
        listing: Listing = {}
        start = self._clock()
        storages = device.Items()  # type: ignore[attr-defined]
        for s in range(storages.Count):
            storage = storages.Item(s)
            if not storage.IsFolder:
                continue
            stack: list[tuple[object, str, int]] = [(storage.GetFolder, "", 0)]
            while stack:
                folder, prefix, depth = stack.pop()
                try:
                    entries = folder.Items()  # type: ignore[attr-defined]
                    count = entries.Count
                except Exception:  # locked phone, folder vanished
                    logger.debug("Phone folder %s not readable", prefix, exc_info=True)
                    continue
                for e in range(count):
                    if len(listing) >= MAX_ENTRIES or self._clock() - start > MAX_SECONDS:
                        return listing
                    try:
                        entry = entries.Item(e)
                        name = str(entry.ExtendedProperty("System.FileName") or entry.Name)
                        rel = f"{prefix}/{name}" if prefix else name
                        if entry.IsFolder:
                            if depth < MAX_DEPTH and _wanted(rel):
                                stack.append((entry.GetFolder, rel, depth + 1))
                        elif prefix and _wanted(rel):
                            size = entry.ExtendedProperty("System.Size")
                            stamp = _stamp(entry.ModifyDate)
                            listing[rel] = FileInfo(int(size or entry.Size or 0), stamp)
                    except Exception:
                        logger.debug("Phone entry not readable", exc_info=True)
                        continue
        return listing


def _stamp(value: object) -> int:
    """A file date as seconds; 0 when the phone doesn't give one (MTP often reports 30 Dec 1899)."""
    if not isinstance(value, datetime) or value.year < 1980:
        return 0
    try:
        return int(value.timestamp())
    except (OSError, OverflowError, ValueError):
        return 0


def phone_made(rel: str) -> bool:
    return bool(PHONE_MADE.search(rel))
