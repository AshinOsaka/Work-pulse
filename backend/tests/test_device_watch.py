"""Devices plugged in, USB file copies and automated input, reported by the desktop agent (1.0.2+)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient

from tests.org_helpers import Workspace, auth
from tests.test_agent_api import enrol_member, iso
from tests.test_notifications import drain, notes


def ev(event_type: str, at: datetime | None = None, **fields: Any) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "type": event_type,
        "occurred_at": iso(at or datetime.now(UTC)),
        **fields,
    }


def policy(ws: Workspace, **changes: Any) -> dict[str, Any]:
    response = ws.client.patch(
        "/api/companies/current/activity-policy", json=changes, headers=auth(ws.admin.token)
    )
    assert response.status_code == 200, response.text
    return response.json()  # type: ignore[no-any-return]


PEN = {
    "device_key": "pen123456",
    "kind": "storage",
    "name": "SanDisk Cruzer Blade",
    "size_bytes": 32_000_000_000,
}
JIGGLER = {
    "device_key": "jig123456",
    "kind": "mouse",
    "name": "HID-compliant mouse",
    "hardware_id": "1A86:E026",
}
HEADSET = {"device_key": "head12345", "kind": "audio", "name": "USB Headset"}


def test_policy_defaults_and_agents_receive_the_settings(ws: Workspace) -> None:
    current = ws.get("/companies/current/activity-policy").json()
    assert current["ignore_software_input"] is True and current["detect_automation"] is True
    assert current["track_devices"] is False and current["track_usb_files"] is False
    # USB file tracking needs device tracking.
    saved = policy(ws, track_usb_files=True)
    assert saved["track_usb_files"] is False
    saved = policy(ws, track_devices=True, track_usb_files=True, presence_check_minutes=20)
    assert saved["track_devices"] and saved["track_usb_files"] and saved["presence_check_minutes"] == 20
    bad = ws.client.patch(
        "/api/companies/current/activity-policy",
        json={"device_alert_kinds": ["storage", "spaceship"]},
        headers=auth(ws.admin.token),
    )
    assert bad.status_code == 422
    _, agent = enrol_member(ws, "Pia Policy")
    heartbeat = agent.client.post(
        "/api/agent/heartbeat", json={"agent_version": "1.0.2"}, headers=auth(agent.token)
    )
    if heartbeat.status_code == 200 and "policy" in heartbeat.json():
        activity = heartbeat.json()["policy"]["activity"]
        assert activity["track_devices"] is True and activity["presence_check_minutes"] == 20


def test_devices_and_usb_files_are_recorded_and_alerted(ws: Workspace, client: TestClient) -> None:
    policy(
        ws,
        track_devices=True,
        track_usb_files=True,
        allowed_devices=[{"key": "head12345", "name": "Headset"}],
    )
    manager = ws.member("Mona Devices", role="MANAGER")
    outsider = ws.member("Otto Elsewhere", role="MANAGER")
    member, agent = enrol_member(ws, "Rahul Usb", manager_employee_id=manager.employee_id)
    now = datetime.now(UTC)
    plugged = now - timedelta(minutes=10)
    assert agent.events(ev("device.connected", plugged, **PEN)).status_code == 200
    assert agent.events(ev("device.connected", plugged, **JIGGLER)).status_code == 200
    assert agent.events(ev("device.connected", plugged, **HEADSET)).status_code == 200  # allowed: no alert
    files = [
        {
            "action": "added",
            "path": "Clients/list.xlsx",
            "size": 2_100_000,
            "at": iso(now - timedelta(minutes=6)),
        },
        {"action": "added", "path": "Proposal.pdf", "size": 850_000, "at": iso(now - timedelta(minutes=5))},
        {"action": "deleted", "path": "old.txt", "size": 10, "at": iso(now - timedelta(minutes=5))},
        {
            "action": "copied_to_computer",
            "path": "Desktop/photo.jpg",
            "size": 300,
            "at": iso(now - timedelta(minutes=5)),
        },
    ]
    report = ev(
        "usb.files",
        now - timedelta(minutes=4),
        **PEN,
        started_at=iso(now - timedelta(minutes=6)),
        ended_at=iso(now - timedelta(minutes=5)),
        counts={"added": 2, "deleted": 1, "copied_to_computer": 1},
        bytes_to_usb=2_950_000,
        bytes_from_usb=300,
        files=files,
    )
    assert agent.events(report).status_code == 200
    assert agent.events(ev("device.disconnected", now - timedelta(minutes=2), **PEN)).status_code == 200
    drain(client)

    mine = notes(ws, manager.token)
    by_type: dict[str, list[dict[str, Any]]] = {}
    for n in mine:
        by_type.setdefault(n["type"], []).append(n)
    connected = sorted(n["title"] for n in by_type["device_connected"])
    assert connected == ["Rahul Usb connected a USB drive", "Rahul Usb connected a mouse"]
    pen_alert = next(n for n in by_type["device_connected"] if "USB drive" in n["title"])
    assert "SanDisk Cruzer Blade (32 GB)" in pen_alert["body"] and "was plugged into" in pen_alert["body"]
    mouse_alert = next(n for n in by_type["device_connected"] if "mouse" in n["title"])
    assert "1A86:E026" in mouse_alert["body"] and "jiggler" in mouse_alert["body"]
    files_alert = by_type["usb_files"][0]
    assert files_alert["title"] == "Rahul Usb copied files with a USB drive"
    assert "2 files copied to it (3.0 MB)" in files_alert["body"] and "list.xlsx" in files_alert["body"]
    assert notes(ws, outsider.token) == []
    assert notes(ws, member.token) == []

    today = now.date().isoformat()
    rows = ws.get(
        "/devices/connections", start=(now - timedelta(days=1)).date().isoformat(), end=today
    ).json()
    assert {r["kind"] for r in rows} == {"storage", "mouse", "audio"}
    pen = next(r for r in rows if r["kind"] == "storage")
    assert pen["employee"] == "Rahul Usb" and pen["disconnected_at"] is not None
    assert pen["file_counts"] == {"added": 2, "deleted": 1, "copied_to_computer": 1}
    assert next(r for r in rows if r["kind"] == "audio")["allowed"] is True
    listed = ws.get(f"/devices/connections/{pen['id']}/files").json()
    assert [f["path"] for f in listed] == [f["path"] for f in files]
    # A manager outside the reporting line sees nothing.
    assert ws.get("/devices/connections", token=outsider.token, start=today, end=today).json() == []
    assert ws.get(f"/devices/connections/{pen['id']}/files", token=outsider.token).status_code == 404


def test_nothing_is_kept_while_device_tracking_is_off(ws: Workspace, client: TestClient) -> None:
    policy(ws, track_devices=False)
    _, agent = enrol_member(ws, "Nina Off")
    assert agent.events(ev("device.connected", None, **PEN)).status_code == 200
    drain(client)
    today = datetime.now(UTC).date().isoformat()
    assert [
        r
        for r in ws.get("/devices/connections", start=today, end=today).json()
        if r["employee"] == "Nina Off"
    ] == []


def test_automated_input_is_reported_once_with_start_and_end(ws: Workspace, client: TestClient) -> None:
    manager = ws.member("Mike Checks", role="MANAGER")
    _, agent = enrol_member(ws, "Arjun Jiggle", manager_employee_id=manager.employee_id)
    now = datetime.now(UTC)
    check_id = str(uuid.uuid4())
    base = {
        "check_id": check_id,
        "kind": "hardware",
        "started_at": iso(now - timedelta(minutes=19)),
        "asked_at": iso(now - timedelta(minutes=4)),
        "minutes": 18,
        "move_minutes": 18,
        "max_span_px": 3,
        "apps": ["Google Chrome"],
    }
    assert (
        agent.events(
            ev("automation.check", now - timedelta(minutes=1), outcome="unanswered", **base)
        ).status_code
        == 200
    )
    ended = {**base, "minutes": 40, "ended_at": iso(now)}
    assert agent.events(ev("automation.check", now, outcome="ended", **ended)).status_code == 200
    # Answered checks are kept but never alert.
    answered = {**base, "check_id": str(uuid.uuid4()), "ended_at": iso(now)}
    assert agent.events(ev("automation.check", now, outcome="confirmed", **answered)).status_code == 200
    software = {
        "check_id": str(uuid.uuid4()),
        "kind": "software",
        "started_at": iso(now - timedelta(minutes=12)),
        "minutes": 10,
    }
    assert agent.events(ev("automation.check", now, outcome="detected", **software)).status_code == 200
    drain(client)

    alerts = [n for n in notes(ws, manager.token) if n["type"] == "automation_suspected"]
    assert sorted(n["title"] for n in alerts) == [
        "Possible automated mouse movement on Arjun Jiggle's computer",
        "Software-made input on Arjun Jiggle's computer",
    ]
    hardware = next(n for n in alerts if "mouse movement" in n["title"])
    assert "no click, scroll or typing" in hardware["body"] and "Google Chrome" in hardware["body"]

    today = now.date().isoformat()
    rows = [
        r
        for r in ws.get(
            "/automation/checks", start=(now - timedelta(days=1)).date().isoformat(), end=today
        ).json()
        if r["employee"] == "Arjun Jiggle"
    ]
    assert sorted(r["status"] for r in rows) == ["answered", "software", "unanswered"]
    flagged = next(r for r in rows if r["status"] == "unanswered")
    assert flagged["minutes"] == 40 and flagged["ended_at"] is not None


def test_the_monitoring_notice_explains_the_new_checks(ws: Workspace) -> None:
    policy(ws, track_devices=True, track_usb_files=True)
    sections = {s["key"]: s for s in ws.get("/privacy/monitoring-policy").json()["sections"]}
    assert sections["automation"]["status"] == "on"
    assert any("Are you still working?" in w for w in sections["automation"]["what"])
    assert sections["devices"]["status"] == "on"
    assert any("ever opened" in s for s in sections["devices"]["safeguards"])
