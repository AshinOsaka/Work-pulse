"""Which files were added to, changed on, renamed on or deleted from a USB drive — names and sizes only.

The drive is listed (folder by folder, names, sizes and modified times) every few seconds while it is connected, and
each list is compared with the one before. No file is ever opened or read. The first list after the drive is
connected is the starting point: files already on it are not reported.

Files copied *from* the USB drive to this computer are noticed in the person's Desktop, Documents and Downloads folders
(two levels deep): a new file there with the same name and size as a file on a connected USB drive. Other new files in
those folders are never reported.
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

#: A drive (or user folder) is listed up to this many entries; beyond that, changes are not seen.
MAX_ENTRIES = 20_000
#: ... and for at most this long per listing.
MAX_LIST_SECONDS = 3.0
SKIP_DIRS = {"system volume information", "$recycle.bin", "recycler", ".trashes", ".spotlight-v100", ".fseventsd"}


@dataclass(frozen=True)
class FileInfo:
    size: int
    mtime: int


Listing = dict[str, FileInfo]


@dataclass(frozen=True)
class FileChange:
    #: added | changed | deleted | renamed (on a USB drive), copied_to_computer (from a USB drive),
    #: copied_to_phone | copied_from_phone (phones over a cable)
    action: str
    path: str
    size: int | None
    at: float
    #: For "renamed": the old name.
    previous: str | None = None


def list_tree(root: Path, *, max_depth: int | None = None, clock: object = None) -> tuple[Listing, bool]:
    """(relative path → size/modified time, complete). Never follows links; skips system folders."""
    tick = clock or time.monotonic
    start: float = tick()  # type: ignore[operator]
    found: Listing = {}
    stack: list[tuple[Path, int]] = [(root, 0)]
    complete = True
    while stack:
        folder, depth = stack.pop()
        try:
            with os.scandir(folder) as entries:
                for entry in entries:
                    if len(found) >= MAX_ENTRIES or tick() - start > MAX_LIST_SECONDS:  # type: ignore[operator]
                        return found, False
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            if entry.name.lower() not in SKIP_DIRS and (max_depth is None or depth < max_depth):
                                stack.append((Path(entry.path), depth + 1))
                        elif entry.is_file(follow_symlinks=False):
                            st = entry.stat(follow_symlinks=False)
                            rel = os.path.relpath(entry.path, root).replace("\\", "/")
                            found[rel] = FileInfo(st.st_size, int(st.st_mtime))
                    except OSError:
                        continue
        except OSError:
            complete = False
            continue
    return found, complete


def compare(before: Listing, after: Listing, at: float) -> list[FileChange]:
    added = {p: i for p, i in after.items() if p not in before}
    deleted = {p: i for p, i in before.items() if p not in after}
    changes: list[FileChange] = []
    # A file that disappeared and one that appeared with the same size and time: renamed or moved.
    by_shape: dict[tuple[int, int], list[str]] = {}
    for path, info in deleted.items():
        by_shape.setdefault((info.size, info.mtime), []).append(path)
    for path, info in sorted(added.items()):
        olds = by_shape.get((info.size, info.mtime))
        if olds:
            old = olds.pop(0)
            del deleted[old]
            changes.append(FileChange("renamed", path, info.size, at, previous=old))
        else:
            changes.append(FileChange("added", path, info.size, at))
    for path, info in sorted(deleted.items()):
        changes.append(FileChange("deleted", path, info.size, at))
    for path, info in sorted(after.items()):
        old_info = before.get(path)
        if old_info is not None and old_info != info:
            changes.append(FileChange("changed", path, info.size, at))
    return changes


def user_folders() -> list[tuple[str, Path]]:
    home = Path(os.environ.get("USERPROFILE") or Path.home())
    folders = []
    for name in ("Desktop", "Documents", "Downloads", "Pictures", "Videos"):
        path = home / name
        if path.is_dir():
            folders.append((name, path))
    # OneDrive moves Desktop and Documents.
    one = os.environ.get("ONEDRIVE")
    if one:
        for name in ("Desktop", "Documents"):
            path = Path(one) / name
            if path.is_dir() and all(path != p for _, p in folders):
                folders.append((name, path))
    return folders


def copied_from_usb(
    before: Listing, after: Listing, usb_files: Iterable[Listing], at: float
) -> list[FileChange]:
    """New files on the computer with the same name and size as a file on a connected USB drive."""
    on_usb: set[tuple[str, int]] = set()
    for listing in usb_files:
        for path, info in listing.items():
            on_usb.add((path.rsplit("/", 1)[-1].lower(), info.size))
    changes = []
    for path, info in sorted(after.items()):
        if path in before:
            continue
        if (path.rsplit("/", 1)[-1].lower(), info.size) in on_usb:
            changes.append(FileChange("copied_to_computer", path, info.size, at))
    return changes
