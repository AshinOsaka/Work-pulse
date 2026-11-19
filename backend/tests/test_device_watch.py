"""Devices plugged in, USB file copies and automated input, reported by the desktop agent (1.0.2+)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
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
    assert connected == ["Mouse connected — Rahul Usb", "USB drive connected — Rahul Usb"]
    pen_alert = next(n for n in by_type["device_connected"] if "USB drive" in n["title"])
    assert "SanDisk Cruzer Blade (32 GB)" in pen_alert["body"] and "was plugged into" in pen_alert["body"]
    mouse_alert = next(n for n in by_type["device_connected"] if "Mouse" in n["title"])
    assert "1A86:E026" in mouse_alert["body"] and "jiggler" in mouse_alert["body"]
    files_alert = by_type["usb_files"][0]
    assert files_alert["title"] == "Files copied with USB — Rahul Usb"
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
        "Possible automated mouse movement — Arjun Jiggle",
        "Software-generated input — Arjun Jiggle",
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


# --- 1.0.3: unanswered checks count as idle, phone files, agent updates, low input -------------------------------


def test_an_unanswered_check_counts_as_idle_and_leaves_the_app_totals(ws: Workspace, client: TestClient) -> None:
    from tests.test_activity_tracking import segment, today_report
    from tests.test_agent_api import event

    _, agent = enrol_member(ws, "Ivan Idle")
    now = datetime.now(UTC).replace(microsecond=0)
    if now.hour < 3:
        pytest.skip("needs two hours of today behind it (UTC)")
    session = str(uuid.uuid4())
    assert agent.events(event("session.started", now - timedelta(hours=2), session_id=session)).status_code == 200
    assert agent.events(segment(now - timedelta(minutes=90), 3600, session=session)).status_code == 200
    before = today_report(ws)
    code = lambda report: next(a for a in report["applications"] if a["app_id"] == "code.exe")  # noqa: E731
    assert code(before)["seconds"] >= 3600
    check = {
        "check_id": str(uuid.uuid4()),
        "kind": "hardware",
        "started_at": iso(now - timedelta(minutes=80)),
        "asked_at": iso(now - timedelta(minutes=65)),
        "minutes": 30,
        "max_span_px": 3,
    }
    agent.events(ev("automation.check", now - timedelta(minutes=62), outcome="unanswered", **check))
    ended = ev("automation.check", now - timedelta(minutes=50), outcome="ended", ended_at=iso(now - timedelta(minutes=50)), **check)
    assert agent.events(ended).status_code == 200
    agent.events(ev("automation.check", now - timedelta(minutes=49), outcome="ended", ended_at=iso(now - timedelta(minutes=50)), **check))  # repeated: applied once
    after = today_report(ws)
    assert round(code(before)["seconds"] - code(after)["seconds"]) == 1800  # 30 minutes taken out of the app time
    rows = [r for r in ws.get("/automation/checks", start=now.date().isoformat(), end=now.date().isoformat()).json() if r["employee"] == "Ivan Idle"]
    assert rows[0]["status"] == "unanswered" and rows[0]["idle_minutes"] == 30


def test_phone_file_copies_alert(ws: Workspace, client: TestClient) -> None:
    policy(ws, track_devices=True, track_usb_files=True)
    manager = ws.member("Pam Phones", role="MANAGER")
    _, agent = enrol_member(ws, "Pete Phone", manager_employee_id=manager.employee_id)
    now = datetime.now(UTC)
    phone = {"device_key": "phone1234", "kind": "phone", "name": "Redmi Note 8", "hardware_id": "2717:FF48"}
    agent.events(ev("device.connected", now - timedelta(minutes=5), **phone))
    files = [
        {"action": "copied_to_phone", "path": "Download/Client_List.xlsx", "size": 2_100_000, "at": iso(now)},
        {"action": "copied_from_phone", "path": "Desktop/IMG_1.jpg", "size": 300_000, "at": iso(now)},
    ]
    report = ev(
        "usb.files", now, **phone, started_at=iso(now), ended_at=iso(now),
        counts={"copied_to_phone": 1, "copied_from_phone": 1}, bytes_to_usb=2_100_000, bytes_from_usb=300_000,
        files=files,
    )  # fmt: skip
    assert agent.events(report).status_code == 200
    drain(client)
    alert = next(n for n in notes(ws, manager.token) if n["type"] == "usb_files")
    assert alert["title"] == "Files copied with phone — Pete Phone"
    assert "Client_List.xlsx" in alert["body"] and "1 file copied to it" in alert["body"]


def test_update_status_and_the_versions_list(ws: Workspace, client: TestClient, settings: Any, monkeypatch: Any) -> None:
    monkeypatch.setattr(settings, "agent_version", "1.0.3")
    monkeypatch.setattr(settings, "agent_download_url", "https://example.com/WorkPulseAgentSetup-1.0.3.exe")
    monkeypatch.setattr(settings, "agent_sha256", "a" * 64)
    _, agent = enrol_member(ws, "Uma Update")
    now = datetime.now(UTC)
    assert agent.events(ev("agent.update", now, state="failed", version="1.0.3", reason="The download failed (no internet connection or the link is not reachable)")).status_code == 200
    drain(client)
    listing = ws.get("/agent/versions").json()
    assert listing["latest"] == "1.0.3"
    row = next(c for c in listing["computers"] if c["employee"] == "Uma Update")
    assert row["status"] == "failed" and "no internet" in row["update_reason"]
    assert any(n["title"] == "WorkPulse update failed — Uma Update" for n in notes(ws))
    # It installs: the heartbeat reports the new version, and the computer is up to date.
    agent.client.post(
        "/api/agent/heartbeat", json={"agent_version": "1.0.3", "sent_at": iso(datetime.now(UTC))},
        headers=auth(agent.token),
    )  # fmt: skip
    row = next(c for c in ws.get("/agent/versions").json()["computers"] if c["employee"] == "Uma Update")
    assert row["status"] == "latest" and row["updated_at"] is not None and row["update_reason"] is None


def test_low_keyboard_mouse_use_in_a_work_app_is_flagged() -> None:
    from bson import ObjectId

    from app.services.auto_reports.figures import Figures, PersonReport, Usage
    from app.services.auto_reports.insights import action_items

    crm = Usage("website", "crm", "crm.osakagroup.com", 7800, "productive", active=620)  # 2h 10m, 8% input
    code = Usage("app", "code", "Visual Studio Code", 9000, "productive", active=6000)  # busy: fine
    p = PersonReport(ObjectId(), "Rahul", "r@example.com", None, None, Figures(), Figures(), usage=[crm, code])
    assert [u.name for u in p.low_activity()] == ["crm.osakagroup.com"] and crm.input_share == 8
    assert any("crm.osakagroup.com open 2h 10m, input 8%" in item for item in action_items([p]))
