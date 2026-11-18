"""Reports devices plugged in and removed, and file changes on USB drives (when the workspace turns it on).

Every few seconds the list of connected devices is compared with the previous one:

* a new device → `device.connected` (name, type, size for storage, USB ids), a missing one → `device.disconnected`;
* the list is remembered between runs, so a device plugged in while WorkPulse wasn't running is reported when it
  starts ("found at start-up"), and one removed meanwhile is closed;
* on the very first run, the computer's own devices (built-in keyboard, touchpad, camera...) are taken as the
  starting point and not reported; USB drives and phones already connected are.

With USB file tracking on, each connected USB drive is listed and compared too (see `files`): the changes are sent
together as one `usb.files` event once copying settles (or every few minutes during a long copy).
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from app.peripherals import files
from app.peripherals.windows import Peripheral
from app.storage.secure_store import SecureStore
from app.system.worker import Worker

logger = logging.getLogger(__name__)

_STORE = "peripherals"
#: Reported even on the very first run (everything else connected then is taken as the computer's own).
ALWAYS_REPORT = {"storage", "phone"}
#: File changes are sent once nothing changed for this long...
SETTLE_SECONDS = 15.0
#: ... or at the latest this long after the first change (a long copy is reported in parts).
MAX_HOLD_SECONDS = 300.0
#: At most this many files per `usb.files` event (the totals still count all of them).
MAX_FILES_PER_EVENT = 500


class Probe(Protocol):
    def all(self) -> list[Peripheral]: ...


@dataclass(frozen=True)
class DevicePolicy:
    track_devices: bool = False
    track_usb_files: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> DevicePolicy:
        data = data or {}
        on = bool(data.get("track_devices", False))
        return cls(track_devices=on, track_usb_files=on and bool(data.get("track_usb_files", False)))


def _iso(at: float) -> str:
    return datetime.fromtimestamp(at, UTC).isoformat()


def _event(event_type: str, at: float, **fields: Any) -> dict[str, Any]:
    return {"id": str(uuid.uuid4()), "type": event_type, "occurred_at": _iso(at), **fields}


def _device_fields(p: Peripheral) -> dict[str, Any]:
    out: dict[str, Any] = {"device_key": p.key, "kind": p.kind, "name": p.name}
    if p.hardware_id:
        out["hardware_id"] = p.hardware_id
    if p.size_bytes:
        out["size_bytes"] = p.size_bytes
    if p.label:
        out["label"] = p.label[:60]
    return out


@dataclass
class _Drive:
    device: Peripheral
    listing: files.Listing | None = None
    complete: bool = False
    pending: dict[str, files.FileChange] = field(default_factory=dict)
    first_change: float = 0.0
    last_change: float = 0.0


class PeripheralWatcher:
    def __init__(
        self,
        emit: Callable[[dict[str, Any]], None],
        probe: Probe,
        store: SecureStore,
        *,
        clock: Callable[[], float] = time.time,
        list_tree: Callable[..., tuple[files.Listing, bool]] = files.list_tree,
        user_folders: Callable[[], list[tuple[str, Path]]] = files.user_folders,
    ) -> None:
        self._emit = emit
        self._probe = probe
        self._store = store
        self._clock = clock
        self._list_tree = list_tree
        self._user_folders = user_folders
        self.policy = DevicePolicy()
        self._present: dict[str, Peripheral] | None = None
        self._drives: dict[str, _Drive] = {}
        self._home_before: files.Listing | None = None
        self._home_reported: set[str] = set()

    def set_policy(self, policy: DevicePolicy) -> None:
        if policy == self.policy:
            return
        if not policy.track_usb_files:
            self._flush_all(self._clock())
            self._drives.clear()
            self._home_before = None
        if not policy.track_devices:
            self._present = None  # start again from what is connected when it's switched back on
        self.policy = policy

    def forget(self) -> None:
        """Signed out: nothing is remembered for the next person."""
        self._present = None
        self._drives.clear()
        self._home_before = None
        self._store.delete(_STORE)

    # ------------------------------------------------------------------ devices
    def scan(self) -> None:
        if not self.policy.track_devices:
            return
        now = self._clock()
        current = {p.key: p for p in self._probe.all()}
        if self._present is None:
            self._start(current, now)
        else:
            for key, device in current.items():
                if key not in self._present:
                    self._emit(_event("device.connected", now, **_device_fields(device)))
            for key, device in self._present.items():
                if key not in current:
                    self._emit(_event("device.disconnected", now, **_device_fields(device)))
        changed = self._present is None or set(current) != set(self._present)
        self._present = current
        if changed:
            self._store.save(_STORE, {"present": [_device_fields(p) for p in current.values()]})
        if self.policy.track_usb_files:
            self._scan_files(current, now)

    def _start(self, current: dict[str, Peripheral], now: float) -> None:
        stored = self._store.load(_STORE)
        if stored is None:
            # First run: the computer's own devices are the starting point; drives and phones are reported.
            for device in current.values():
                if device.kind in ALWAYS_REPORT:
                    self._emit(_event("device.connected", now, at_start=True, **_device_fields(device)))
            return
        before = {str(d["device_key"]): d for d in stored.get("present", []) if d.get("device_key")}
        for key, device in current.items():
            if key not in before:
                self._emit(_event("device.connected", now, at_start=True, **_device_fields(device)))
        for key, data in before.items():
            if key not in current:
                fields = {k: data[k] for k in ("device_key", "kind", "name", "hardware_id", "size_bytes", "label") if k in data}
                self._emit(_event("device.disconnected", now, at_start=True, **fields))

    # ------------------------------------------------------------------ files on USB drives
    def _scan_files(self, current: dict[str, Peripheral], now: float) -> None:
        drives = {p.key: p for p in current.values() if p.kind == "storage" and p.drive}
        for key in list(self._drives):
            if key not in drives:
                self._flush(self._drives.pop(key), now)
        for key, device in drives.items():
            drive = self._drives.get(key)
            if drive is None:
                drive = self._drives[key] = _Drive(device)
            listing, complete = self._list_tree(Path(f"{device.drive}\\"))
            if drive.listing is not None and drive.complete and complete:
                for change in files.compare(drive.listing, listing, now):
                    self._add(drive, change, now)
            drive.listing, drive.complete = listing, complete
        self._scan_home(now)
        for drive in self._drives.values():
            if drive.pending and (
                now - drive.last_change >= SETTLE_SECONDS or now - drive.first_change >= MAX_HOLD_SECONDS
            ):
                self._flush(drive, now)

    def _scan_home(self, now: float) -> None:
        if not self._drives:
            self._home_before = None
            self._home_reported.clear()
            return
        listing: files.Listing = {}
        for name, folder in self._user_folders():
            part, _ = self._list_tree(folder, max_depth=2)
            listing.update({f"{name}/{path}": info for path, info in part.items()})
        if self._home_before is None:
            self._home_before = listing
            return
        usb = [d.listing for d in self._drives.values() if d.listing]
        found = files.copied_from_usb(self._home_before, listing, usb, now)
        target = next(iter(self._drives.values()))
        for change in found:
            if change.path not in self._home_reported:
                self._home_reported.add(change.path)
                self._add(target, change, now)

    def _add(self, drive: _Drive, change: files.FileChange, now: float) -> None:
        if not drive.pending:
            drive.first_change = now
        drive.last_change = now
        earlier = drive.pending.get(change.path)
        if earlier is not None and earlier.action == "added" and change.action == "changed":
            # Still being copied: keep it as "added" with the newer size.
            change = files.FileChange("added", change.path, change.size, earlier.at)
        drive.pending[change.path] = change

    def _flush(self, drive: _Drive, now: float) -> None:
        if not drive.pending:
            return
        changes = sorted(drive.pending.values(), key=lambda c: c.at)
        drive.pending = {}
        totals: dict[str, int] = {}
        for c in changes:
            totals[c.action] = totals.get(c.action, 0) + 1
        to_usb = sum(c.size or 0 for c in changes if c.action in ("added", "changed"))
        from_usb = sum(c.size or 0 for c in changes if c.action == "copied_to_computer")
        entries = []
        for c in changes[:MAX_FILES_PER_EVENT]:
            entry: dict[str, Any] = {"action": c.action, "path": c.path[:400], "at": _iso(c.at)}
            if c.size is not None:
                entry["size"] = c.size
            if c.previous:
                entry["previous"] = c.previous[:400]
            entries.append(entry)
        self._emit(
            _event(
                "usb.files",
                now,
                **_device_fields(drive.device),
                started_at=_iso(changes[0].at),
                ended_at=_iso(changes[-1].at),
                counts=totals,
                bytes_to_usb=to_usb,
                bytes_from_usb=from_usb,
                files=entries,
                truncated=len(changes) > MAX_FILES_PER_EVENT,
            )
        )

    def _flush_all(self, now: float) -> None:
        for drive in self._drives.values():
            self._flush(drive, now)


class PeripheralWorker(Worker):
    def __init__(self, watcher: PeripheralWatcher, active: Callable[[], bool]) -> None:
        super().__init__("workpulse-devices")
        self._watcher = watcher
        self._active = active

    def interval(self) -> float:
        return 5.0

    def step(self) -> None:
        if self._active():
            self._watcher.scan()
