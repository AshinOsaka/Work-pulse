"""Software-made input, automated mouse movement, devices and USB file changes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.activity.automation import AutomationDetector, AutomationPolicy
from app.activity.idle import RealInputIdleDetector
from app.activity.input_counter import InputStats
from app.peripherals import files
from app.peripherals.watcher import DevicePolicy, PeripheralWatcher
from app.peripherals.windows import Peripheral, hardware_id
from app.security.crypto import Cipher
from app.storage.secure_store import SecureStore


class Clock:
    def __init__(self, start: float = 6_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now


class FakeIdle:
    def __init__(self, value: float = 0.0) -> None:
        self.value = value

    def idle_seconds(self) -> float:
        return self.value


class Monitor:
    """Stands in for the Windows hooks: real stats, always "running"."""

    def __init__(self, stats: InputStats) -> None:
        self.stats = stats
        self.running = True
        self.restarts = 0

    def restart(self) -> None:
        self.restarts += 1


# --- software-made input ----------------------------------------------------------------------------------------


def test_software_input_is_not_counted_and_keeps_the_person_idle() -> None:
    mono = Clock()
    stats = InputStats(mono=mono, wall=mono)
    mono.now += 600
    for _ in range(300):  # a mouse-mover app: injected movement every second
        mono.now += 1
        stats.move(True, 10, 10)
    assert (stats.keys, stats.mouse) == (0, 0)
    real_idle, any_idle = stats.idle()
    assert real_idle >= 900 and any_idle < 2
    # Windows' own idle time says "active" (it counts the fake input); WorkPulse goes by real input.
    detector = RealInputIdleDetector(FakeIdle(0.5), Monitor(stats), clock=mono)
    assert detector.idle_seconds() >= 900
    detector.enabled = False
    assert detector.idle_seconds() == 0.5


def test_real_input_counts_as_before() -> None:
    mono = Clock()
    stats = InputStats(mono=mono, wall=mono)
    stats.key(False)
    stats.click(False)
    stats.move(False, 1, 1)
    assert stats.keys == 1 and stats.mouse == 2
    detector = RealInputIdleDetector(FakeIdle(0.0), Monitor(stats), clock=mono)
    mono.now += 3
    assert 2.9 < detector.idle_seconds() < 3.1


def test_falls_back_to_windows_when_the_hooks_stop_seeing_input() -> None:
    mono = Clock()
    stats = InputStats(mono=mono, wall=mono)
    monitor = Monitor(stats)
    detector = RealInputIdleDetector(FakeIdle(1.0), monitor, clock=mono)
    mono.now += 120  # the hooks saw nothing for 2 minutes, but Windows saw input a second ago
    assert detector.idle_seconds() == 1.0


# --- automated movement -----------------------------------------------------------------------------------------


class Pattern:
    def __init__(self) -> None:
        self.clock = Clock(60_000.0)
        self.stats = InputStats(mono=self.clock, wall=self.clock)
        self.events: list[dict[str, Any]] = []
        self.unanswered = 0
        self.detector = AutomationDetector(
            self.events.append, lambda: self.stats, on_unanswered=self._unanswered, wall=self.clock
        )
        self.detector.set_policy(AutomationPolicy(check_after=15, answer_minutes=3, software_after=10))

    def _unanswered(self) -> None:
        self.unanswered += 1

    def run(self, seconds: int, *, move: bool = False, injected: bool = False, x: int = 500) -> None:
        for i in range(seconds):
            self.clock.now += 1
            if move:
                self.stats.move(injected, x + (i % 3), 300)
            self.detector.tick(working=True, app="Google Chrome")

    def outcomes(self) -> list[str]:
        return [e["outcome"] for e in self.events]


def test_a_mouse_moving_with_no_click_or_typing_is_checked_then_reported() -> None:
    p = Pattern()
    p.run(14 * 60, move=True)
    assert not p.detector.asking
    p.run(2 * 60, move=True)
    assert p.detector.asking and p.events == []
    p.run(3 * 60 + 5, move=True)  # nobody answers
    assert p.outcomes() == ["unanswered"]
    assert p.unanswered == 1
    event = p.events[0]
    assert event["kind"] == "hardware" and event["minutes"] >= 15 and event["apps"] == ["Google Chrome"]
    assert event["max_span_px"] <= 3
    p.run(20 * 60, move=True)
    assert p.outcomes() == ["unanswered"]  # reported once
    p.stats.key(False)  # someone is back
    p.run(2)
    assert p.outcomes() == ["unanswered", "ended"]
    assert not p.detector.asking
    assert p.events[1]["check_id"] == event["check_id"] and "ended_at" in p.events[1]


def test_a_click_answers_the_check_and_nothing_is_reported() -> None:
    p = Pattern()
    p.run(16 * 60, move=True)
    assert p.detector.asking
    p.detector.confirm()
    assert p.outcomes() == ["confirmed"]
    assert not p.detector.asking and p.unanswered == 0


def test_normal_work_is_never_checked() -> None:
    p = Pattern()
    for _ in range(40):  # moves, clicks and types every minute
        p.run(40, move=True)
        p.stats.click(False)
        p.stats.key(False)
        p.run(20)
    assert p.events == [] and not p.detector.asking


def test_reading_without_moving_is_never_checked() -> None:
    p = Pattern()
    p.run(40 * 60)
    assert p.events == [] and not p.detector.asking


def test_a_mouse_mover_app_is_reported_with_start_and_end() -> None:
    p = Pattern()
    for _ in range(12):
        p.stats.move(True, 1, 1)
        p.run(60)
    assert p.outcomes() == ["detected"]
    assert p.events[0]["kind"] == "software"
    p.run(3 * 60)  # the app stopped
    assert p.outcomes() == ["detected", "ended"]


def test_switched_off_means_no_checks() -> None:
    p = Pattern()
    p.detector.set_policy(AutomationPolicy(enabled=False))
    p.run(30 * 60, move=True)
    assert p.events == [] and not p.detector.asking


# --- devices ----------------------------------------------------------------------------------------------------


class Probe:
    def __init__(self, *devices: Peripheral) -> None:
        self.devices = list(devices)

    def all(self) -> list[Peripheral]:
        return list(self.devices)


TOUCHPAD = Peripheral("k-touch", "mouse", "ELAN Input Device")
PEN = Peripheral("k-pen", "storage", "SanDisk Cruzer Blade", drive="E:", size_bytes=32_000_000_000, label="DATA")
JIGGLER = Peripheral("k-jig", "mouse", "HID-compliant mouse", hardware_id="1A86:E026")


def store(tmp_path: Path) -> SecureStore:
    return SecureStore(tmp_path / "secure", Cipher(b"k" * 32))


def watcher(tmp_path: Path, probe: Probe, **kw: Any) -> tuple[PeripheralWatcher, list[dict[str, Any]]]:
    events: list[dict[str, Any]] = []
    w = PeripheralWatcher(events.append, probe, store(tmp_path), **kw)
    w.set_policy(DevicePolicy(track_devices=True))
    return w, events


def test_first_run_reports_drives_but_not_the_computers_own_devices(tmp_path: Path) -> None:
    w, events = watcher(tmp_path, Probe(TOUCHPAD, PEN))
    w.scan()
    assert [(e["type"], e["name"], e.get("at_start")) for e in events] == [
        ("device.connected", "SanDisk Cruzer Blade", True)
    ]


def test_plugging_in_and_removing_is_reported(tmp_path: Path) -> None:
    probe = Probe(TOUCHPAD)
    w, events = watcher(tmp_path, probe)
    w.scan()
    probe.devices.append(JIGGLER)
    w.scan()
    probe.devices.remove(JIGGLER)
    w.scan()
    assert [(e["type"], e["kind"], e.get("hardware_id")) for e in events] == [
        ("device.connected", "mouse", "1A86:E026"),
        ("device.disconnected", "mouse", "1A86:E026"),
    ]


def test_changes_while_workpulse_was_closed_are_reported_at_start(tmp_path: Path) -> None:
    probe = Probe(TOUCHPAD, PEN)
    w, _ = watcher(tmp_path, probe)
    w.scan()
    probe.devices = [TOUCHPAD, JIGGLER]  # pen drive removed, jiggler plugged in while closed
    w2, events = watcher(tmp_path, probe)
    w2.scan()
    assert sorted((e["type"], e["name"]) for e in events) == [
        ("device.connected", "HID-compliant mouse"),
        ("device.disconnected", "SanDisk Cruzer Blade"),
    ]


def test_nothing_is_recorded_while_switched_off(tmp_path: Path) -> None:
    probe = Probe(TOUCHPAD)
    w, events = watcher(tmp_path, probe)
    w.set_policy(DevicePolicy(track_devices=False))
    probe.devices.append(PEN)
    w.scan()
    assert events == []


def test_hardware_ids_are_read_from_the_device_id() -> None:
    assert hardware_id(r"HID\VID_046d&PID_C542&MI_01\8&2f") == "046D:C542"
    assert hardware_id("ACPI\\ELAN0001") is None


# --- files on USB drives ----------------------------------------------------------------------------------------


def test_compare_finds_added_changed_deleted_and_renamed() -> None:
    before = {"a.txt": files.FileInfo(10, 1), "b.pdf": files.FileInfo(20, 2), "c.doc": files.FileInfo(5, 3)}
    after = {"a.txt": files.FileInfo(11, 4), "x/b-new.pdf": files.FileInfo(20, 2), "d.xlsx": files.FileInfo(7, 5)}
    changes = {(c.action, c.path, c.previous) for c in files.compare(before, after, 1.0)}
    assert changes == {
        ("changed", "a.txt", None),
        ("renamed", "x/b-new.pdf", "b.pdf"),
        ("added", "d.xlsx", None),
        ("deleted", "c.doc", None),
    }


def test_list_tree_reads_names_and_sizes(tmp_path: Path) -> None:
    (tmp_path / "Clients").mkdir()
    (tmp_path / "Clients" / "list.xlsx").write_bytes(b"x" * 42)
    (tmp_path / "System Volume Information").mkdir()
    (tmp_path / "System Volume Information" / "x").write_bytes(b"1")
    listing, complete = files.list_tree(tmp_path)
    assert complete and list(listing) == ["Clients/list.xlsx"] and listing["Clients/list.xlsx"].size == 42


def test_copies_to_and_from_a_usb_drive_are_sent_once_copying_settles(tmp_path: Path) -> None:
    usb = tmp_path / "usb"
    home = tmp_path / "home" / "Desktop"
    usb.mkdir()
    home.mkdir(parents=True)
    (usb / "old.txt").write_bytes(b"already there")
    (usb / "photo.jpg").write_bytes(b"p" * 300)
    clock = Clock(1_000_000.0)
    drive = Peripheral("k-usb", "storage", "Kingston DataTraveler", drive="U:", size_bytes=64_000_000_000)

    def list_tree(root: Path, **kw: Any) -> tuple[files.Listing, bool]:
        return files.list_tree(usb if str(root).startswith("U:") else root, **kw)

    probe = Probe(TOUCHPAD)
    events: list[dict[str, Any]] = []
    w = PeripheralWatcher(
        events.append, probe, store(tmp_path), clock=clock, list_tree=list_tree,
        user_folders=lambda: [("Desktop", home)],
    )  # fmt: skip
    w.set_policy(DevicePolicy(track_devices=True, track_usb_files=True))
    w.scan()
    probe.devices.append(drive)
    w.scan()  # connected: the starting point
    assert [e["type"] for e in events] == ["device.connected"]
    (usb / "Clients").mkdir()
    (usb / "Clients" / "list.xlsx").write_bytes(b"x" * 1000)
    (usb / "old.txt").unlink()
    (home / "photo.jpg").write_bytes(b"p" * 300)  # copied from the USB drive to the Desktop
    (home / "notes.txt").write_bytes(b"mine")  # unrelated: never reported
    clock.now += 5
    w.scan()
    assert [e["type"] for e in events] == ["device.connected"]  # still settling
    clock.now += 20
    w.scan()
    sent = [e for e in events if e["type"] == "usb.files"]
    assert len(sent) == 1
    report = sent[0]
    assert report["name"] == "Kingston DataTraveler"
    assert {(f["action"], f["path"]) for f in report["files"]} == {
        ("added", "Clients/list.xlsx"),
        ("deleted", "old.txt"),
        ("copied_to_computer", "Desktop/photo.jpg"),
    }
    assert report["counts"] == {"added": 1, "deleted": 1, "copied_to_computer": 1}
    assert report["bytes_to_usb"] == 1000 and report["bytes_from_usb"] == 300
    probe.devices.remove(drive)
    clock.now += 5
    w.scan()
    assert events[-1]["type"] == "device.disconnected"


# --- phones ---------------------------------------------------------------------------------------------------


def test_files_copied_to_and_from_a_phone(tmp_path: Path) -> None:
    from app.peripherals.phone import _wanted, phone_made

    home = tmp_path / "Desktop"
    home.mkdir()
    clock = Clock(2_000_000.0)
    phone_files: dict[str, files.Listing] = {
        "2717:FF48": {
            "Internal shared storage/Download/old.pdf": files.FileInfo(100, 1),
            "Internal shared storage/DCIM/Camera/IMG_1.jpg": files.FileInfo(3_000, 1),
        }
    }
    redmi = Peripheral("k-phone", "phone", "Redmi Note 8", hardware_id="2717:FF48")
    probe = Probe(TOUCHPAD)
    events: list[dict[str, Any]] = []
    w = PeripheralWatcher(
        events.append, probe, store(tmp_path), clock=clock, user_folders=lambda: [("Desktop", home)],
        phones=lambda: {k: dict(v) for k, v in phone_files.items()},
    )  # fmt: skip
    w.set_policy(DevicePolicy(track_devices=True, track_usb_files=True))
    w.scan()
    probe.devices.append(redmi)
    w.scan()  # plugged in: the first read
    clock.now += 25
    w.scan()  # the same files again: the starting point is settled
    listing = phone_files["2717:FF48"]
    # Computer → phone: a client list lands in the phone's Download folder; the phone also takes a photo.
    listing["Internal shared storage/Download/Client_List.xlsx"] = files.FileInfo(2_100, 5)
    listing["Internal shared storage/DCIM/Camera/IMG_2.jpg"] = files.FileInfo(4_000, 5)
    # Phone → computer: the old PDF is copied to the Desktop.
    (home / "old.pdf").write_bytes(b"x" * 100)
    clock.now += 25
    w.scan()
    clock.now += 30
    w.scan()
    sent = [e for e in events if e["type"] == "usb.files"]
    assert len(sent) == 1 and sent[0]["kind"] == "phone" and sent[0]["name"] == "Redmi Note 8"
    assert {(f["action"], f["path"]) for f in sent[0]["files"]} == {
        ("copied_to_phone", "Internal shared storage/Download/Client_List.xlsx"),
        ("copied_from_phone", "Desktop/old.pdf"),
    }
    assert sent[0]["bytes_to_usb"] == 2_100 and sent[0]["bytes_from_usb"] == 100
    # Only the folders where copied files land are read; photos the phone takes are never "copied".
    assert _wanted("Download/a.pdf") and _wanted("Android/media/com.whatsapp/WhatsApp/Media/x.pdf")
    assert not _wanted("Android/data/com.game/cache.bin") and not _wanted("Alarms/ring.mp3")
    assert phone_made("Internal shared storage/DCIM/Camera/IMG_2.jpg")


def test_a_phone_shown_partly_at_first_is_not_reported_as_new_files(tmp_path: Path) -> None:
    clock = Clock(3_000_000.0)
    full = {f"WhatsApp Business/Media/doc{i}.pdf": files.FileInfo(i, 0) for i in range(10)}
    reads = [dict(list(full.items())[:4]), dict(full), dict(full), dict(full)]
    redmi = Peripheral("k-phone", "phone", "Redmi 9", hardware_id="2717:FF40")
    events: list[dict[str, Any]] = []
    w = PeripheralWatcher(
        events.append, Probe(redmi), store(tmp_path), clock=clock, user_folders=list,
        phones=lambda: {"2717:FF40": reads.pop(0) if len(reads) > 1 else reads[0]},
    )  # fmt: skip
    w.set_policy(DevicePolicy(track_devices=True, track_usb_files=True))
    for _ in range(5):
        w.scan()
        clock.now += 25
    assert [e for e in events if e["type"] == "usb.files"] == []
