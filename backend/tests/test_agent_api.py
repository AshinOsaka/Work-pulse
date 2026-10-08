"""Phase 4: desktop agent API — registration, device auth, heartbeat, events, presence."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient

from tests.conftest import register
from tests.org_helpers import Actor, Workspace, auth


def fingerprint(seed: str = "") -> str:
    return hashlib.sha256(f"test-machine-{seed or uuid.uuid4()}".encode()).hexdigest()


def device_info(fp: str | None = None, name: str = "Test laptop") -> dict[str, Any]:
    return {
        "name": name,
        "hostname": "TEST-PC",
        "os": "windows",
        "os_version": "11 23H2",
        "agent_version": "0.1.0",
        "fingerprint": fp or fingerprint(),
    }


def iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat()


class AgentClient:
    """Mimics the desktop agent: device credentials -> device token -> agent endpoints."""

    def __init__(self, client: TestClient, credentials: dict[str, Any]) -> None:
        self.client = client
        self.device_id = credentials["device_id"]
        self.secret = credentials["device_secret"]
        self.token = self.exchange().json()["access_token"]

    def exchange(self, secret: str | None = None) -> Any:
        return self.client.post(
            "/api/agent/token", json={"device_id": self.device_id, "device_secret": secret or self.secret}
        )

    def heartbeat(self, presence: str | None = None, session_id: str | None = None) -> Any:
        return self.client.post(
            "/api/agent/heartbeat",
            json={
                "presence": presence,
                "session_id": session_id,
                "agent_version": "0.1.0",
                "sent_at": iso(datetime.now(UTC)),
            },
            headers=auth(self.token),
        )

    def events(self, *events: dict[str, Any]) -> Any:
        return self.client.post("/api/agent/events", json={"events": list(events)}, headers=auth(self.token))


def event(kind: str, at: datetime | None = None, **fields: Any) -> dict[str, Any]:
    return {"id": str(uuid.uuid4()), "type": kind, "occurred_at": iso(at or datetime.now(UTC)), **fields}


def enrol_member(
    ws: Workspace, name: str, role: str = "EMPLOYEE", **fields: Any
) -> tuple[Actor, AgentClient]:
    member = ws.member(name, role=role, **fields)
    response = ws.client.post(
        "/api/agent/register",
        json={"email": member.email, "password": "Member1Password", "device": device_info()},
    )
    assert response.status_code == 200, response.text
    return member, AgentClient(ws.client, response.json())


def presence_row(ws: Workspace, employee_id: str, token: str | None = None) -> dict[str, Any]:
    overview = ws.get("/presence", token=token).json()
    return next(r for r in overview["employees"] if r["employee"]["id"] == employee_id)


# --------------------------------------------------------------------------- registration & auth


def test_register_exchange_and_identity(ws: Workspace) -> None:
    member = ws.member("Agent Alice")
    fp = fingerprint("alice")
    response = ws.client.post(
        "/api/agent/register",
        json={"email": member.email, "password": "Member1Password", "device": device_info(fp)},
    )
    assert response.status_code == 200
    creds = response.json()
    assert creds["employee"]["full_name"] == "Agent Alice"
    assert creds["company"]["name"] == "Org Test Co"
    assert creds["policy"]["heartbeat_interval_seconds"] > 0
    assert len(creds["device_secret"]) >= 32

    agent = AgentClient(ws.client, creds)
    me = ws.client.get("/api/agent/me", headers=auth(agent.token))
    assert me.status_code == 200 and me.json()["device_id"] == creds["device_id"]

    # The admin sees the device as active on the employee's profile.
    devices = ws.get(f"/employees/{member.employee_id}/devices").json()
    assert [d["status"] for d in devices] == ["active"]

    # Re-registering the same machine reuses the device and rotates the secret.
    again = ws.client.post(
        "/api/agent/register",
        json={"email": member.email, "password": "Member1Password", "device": device_info(fp)},
    ).json()
    assert again["device_id"] == creds["device_id"]
    assert agent.exchange().status_code == 401
    assert agent.exchange(again["device_secret"]).status_code == 200


def test_register_rejects_bad_credentials_and_invited_accounts(ws: Workspace) -> None:
    member = ws.member("Wrong Pass")
    bad = ws.client.post(
        "/api/agent/register",
        json={"email": member.email, "password": "nope-nope-1", "device": device_info()},
    )
    assert bad.status_code == 401 and bad.json()["error"]["code"] == "invalid_credentials"

    invited = ws.employee("Not Yet Joined", invite=True)
    pending = ws.client.post(
        "/api/agent/register",
        json={"email": invited["email"], "password": "whatever-123", "device": device_info()},
    )
    assert pending.status_code == 401


def test_user_and_device_tokens_are_not_interchangeable(ws: Workspace) -> None:
    _, agent = enrol_member(ws, "Token Tess")
    user_on_agent = ws.client.post(
        "/api/agent/heartbeat",
        json={"agent_version": "0.1.0", "sent_at": iso(datetime.now(UTC))},
        headers=auth(ws.admin.token),
    )
    assert user_on_agent.status_code == 401
    assert ws.client.get("/api/auth/me", headers=auth(agent.token)).status_code == 401
    assert ws.client.get("/api/employees", headers=auth(agent.token)).status_code == 401
    assert ws.client.post("/api/agent/heartbeat", json={}).status_code in (401, 422)


# --------------------------------------------------------------------------- heartbeat, events, presence


def test_heartbeat_sessions_and_presence(ws: Workspace) -> None:
    member, agent = enrol_member(ws, "Presence Pat")

    assert agent.heartbeat().status_code == 200
    row = presence_row(ws, member.employee_id)
    assert row["connected"] is True and row["status"] == "offline"  # online, but not working

    session = str(uuid.uuid4())
    start = datetime.now(UTC) - timedelta(minutes=30)
    started = event("session.started", start, session_id=session)
    result = agent.events(started).json()
    assert result == {"accepted": 1, "duplicates": 0, "rejected": []}
    assert agent.events(started).json()["duplicates"] == 1  # retries are idempotent

    row = presence_row(ws, member.employee_id)
    assert row["status"] == "active"
    assert row["session_started_at"] is not None
    assert row["device"]["name"] == "Test laptop"

    agent.events(event("presence.changed", session_id=session, status="idle"))
    assert presence_row(ws, member.employee_id)["status"] == "idle"
    counts = ws.get("/presence").json()["counts"]
    assert counts["idle"] >= 1 and counts["online"] >= 1

    agent.events(
        event("session.stopped", session_id=session, reason="user", active_seconds=1500, idle_seconds=300)
    )
    row = presence_row(ws, member.employee_id)
    assert row["status"] == "offline" and row["connected"] is True

    feed = ws.get("/activity/feed").json()
    actions = [item["action"] for item in feed]
    assert "work.session_started" in actions and "work.session_stopped" in actions
    # Feed entries carry when the work happened, not when the server received it (offline queues).
    started_entry = next(item for item in feed if item["action"] == "work.session_started")
    assert abs(datetime.fromisoformat(started_entry["occurred_at"]) - start) < timedelta(seconds=1)

    agent.events(event("agent.stopped", reason="quit"))
    assert presence_row(ws, member.employee_id)["connected"] is False


def test_events_are_metadata_only_and_validated(ws: Workspace) -> None:
    _, agent = enrol_member(ws, "Strict Sam")
    session = str(uuid.uuid4())
    with_content = event("session.started", session_id=session)
    with_content["window_title"] = "Quarterly results.xlsx"  # anything beyond the schema is refused
    assert agent.events(with_content).status_code == 422
    assert agent.events(event("keystrokes.captured", text="secret")).status_code == 422
    assert agent.events(event("presence.changed", session_id=session, status="sleeping")).status_code == 422

    far_future = event("session.started", datetime.now(UTC) + timedelta(days=2), session_id=session)
    result = agent.events(far_future).json()
    assert result["accepted"] == 0 and result["rejected"][0]["reason"] == "occurred_at_out_of_range"
    assert (
        agent.client.post("/api/agent/events", json={"events": []}, headers=auth(agent.token)).status_code
        == 422
    )


def test_lost_start_event_is_reconstructed(ws: Workspace) -> None:
    member, agent = enrol_member(ws, "Lossy Lou")
    agent.heartbeat()
    stop = event(
        "session.stopped",
        session_id=str(uuid.uuid4()),
        reason="recovered",
        active_seconds=3000,
        idle_seconds=600,
    )
    assert agent.events(stop).json()["accepted"] == 1
    hours = ws.get("/presence/work-hours", period="weekly").json()
    assert hours["current_hours"] + hours["previous_hours"] >= 0.99
    assert presence_row(ws, member.employee_id)["status"] == "offline"


def test_work_hours_by_period(ws: Workspace) -> None:
    _, agent = enrol_member(ws, "Hours Hana")
    session = str(uuid.uuid4())
    now = datetime.now(UTC)
    agent.events(
        event("session.started", now - timedelta(hours=2), session_id=session),
        event(
            "session.stopped",
            now - timedelta(hours=1),
            session_id=session,
            reason="user",
            active_seconds=3300,
            idle_seconds=300,
        ),
    )
    for period in ("daily", "weekly", "monthly"):
        summary = ws.get("/presence/work-hours", period=period).json()
        assert len(summary["history"]) == 8
        # The hour may straddle a period boundary; together the last two buckets hold it.
        assert abs(summary["current_hours"] + summary["previous_hours"] - 1.0) < 0.05, (period, summary)
    assert ws.get("/presence/work-hours", period="yearly").status_code == 422


# --------------------------------------------------------------------------- lifecycle & security


def test_revoked_device_loses_access_immediately(ws: Workspace) -> None:
    _, agent = enrol_member(ws, "Revoked Rita")
    assert agent.heartbeat().status_code == 200
    assert ws.post(f"/devices/{agent.device_id}/revoke", {}).status_code == 200
    assert agent.heartbeat().status_code == 401
    assert agent.heartbeat().json()["error"]["code"] == "device_revoked"
    assert agent.exchange().status_code == 401


def test_terminated_employee_device_is_blocked(ws: Workspace) -> None:
    member, agent = enrol_member(ws, "Leaving Leo")
    ws.post(f"/employees/{member.employee_id}/status", {"status": "terminated"})
    blocked = agent.heartbeat()
    assert blocked.status_code == 403 and blocked.json()["error"]["code"] == "employee_terminated"
    assert agent.exchange().status_code == 403


def test_enrolment_code_flow(ws: Workspace) -> None:
    employee = ws.employee("Kiosk Kim")  # no WorkPulse account needed for managed installs
    issued = ws.post(f"/employees/{employee['id']}/devices", {"name": "Front desk PC"}).json()
    code = issued["enrollment_code"].lower()  # codes are case-insensitive
    enrolled = ws.client.post(
        "/api/agent/enroll", json={"enrollment_code": code, "device": device_info(name="DESK-01")}
    )
    assert enrolled.status_code == 200, enrolled.text
    creds = enrolled.json()
    assert creds["device_id"] == issued["id"]
    assert creds["employee"]["full_name"] == "Kiosk Kim"

    agent = AgentClient(ws.client, creds)
    assert agent.heartbeat().status_code == 200
    device = ws.get(f"/employees/{employee['id']}/devices").json()[0]
    assert device["status"] == "active" and device["name"] == "Front desk PC"

    reused = ws.client.post("/api/agent/enroll", json={"enrollment_code": code, "device": device_info()})
    assert reused.status_code == 400 and reused.json()["error"]["code"] == "invalid_enrollment_code"


def test_presence_respects_scope_permissions_and_tenancy(ws: Workspace, client: TestClient) -> None:
    manager = ws.member("Manny Manager", role="MANAGER")
    report, report_agent = enrol_member(ws, "Rae Report", manager_employee_id=manager.employee_id)
    outsider, outsider_agent = enrol_member(ws, "Otto Outside")
    report_agent.heartbeat()
    outsider_agent.heartbeat()

    visible = {r["employee"]["id"] for r in ws.get("/presence", token=manager.token).json()["employees"]}
    assert report.employee_id in visible and outsider.employee_id not in visible

    assert ws.get("/presence", token=report.token).status_code == 403
    assert ws.get("/presence/work-hours", token=report.token).status_code == 403

    rival = str(register(client, company_name="Rival Presence")["access_token"])
    rival_view = ws.get("/presence", token=rival).json()
    assert report.employee_id not in {r["employee"]["id"] for r in rival_view["employees"]}
    assert rival_view["counts"]["online"] == 0
