"""Phase 5: activity tracking — policy, batched segment ingest, rollups, privacy, reports."""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from bson import ObjectId
from fastapi.testclient import TestClient

from tests.conftest import register
from tests.org_helpers import Workspace, auth
from tests.test_agent_api import enrol_member, event, iso


def segment(
    start: datetime,
    seconds: int,
    *,
    app_id: str = "code.exe",
    app_name: str = "Visual Studio Code",
    title: str | None = None,
    active: int | None = None,
    level: int = 80,
    session: str | None = None,
) -> dict[str, Any]:
    end = start + timedelta(seconds=seconds)
    return event(
        "activity.segment",
        end,
        session_id=session or str(uuid.uuid4()),
        app_id=app_id,
        app_name=app_name,
        window_title=title,
        started_at=iso(start),
        ended_at=iso(end),
        active_seconds=seconds if active is None else active,
        activity_level=level,
    )


def today_report(ws: Workspace, token: str | None = None, **params: Any) -> dict[str, Any]:
    today = datetime.now(UTC).date().isoformat()
    response = ws.get("/activity/applications", token=token, start=today, end=today, **params)
    assert response.status_code == 200, response.text
    return response.json()  # type: ignore[no-any-return]


# --------------------------------------------------------------------------- policy


def test_policy_defaults_visibility_and_delivery_to_agent(ws: Workspace) -> None:
    member, agent = enrol_member(ws, "Policy Pia")
    defaults = ws.get("/companies/current/activity-policy", token=member.token).json()
    assert defaults == {
        "track_applications": True,
        "capture_window_titles": False,
        "track_websites": False,
        "excluded_apps": [],
    }

    assert (
        ws.patch(
            "/companies/current/activity-policy", {"capture_window_titles": True}, token=member.token
        ).status_code
        == 403
    )
    updated = ws.patch(
        "/companies/current/activity-policy",
        {"capture_window_titles": True, "excluded_apps": [" Spotify ", "spotify", "Steam"]},
    ).json()
    assert updated["capture_window_titles"] is True
    assert updated["excluded_apps"] == ["Spotify", "Steam"]  # trimmed, de-duplicated, sorted

    # Agents receive the policy on their next heartbeat.
    policy = agent.heartbeat().json()["policy"]["activity"]
    assert policy == updated


# --------------------------------------------------------------------------- ingest, batching, rollups


def test_batched_segments_are_stored_and_rolled_up(ws: Workspace, sync_db: Any) -> None:
    member, agent = enrol_member(ws, "Batch Ben")
    start = datetime.now(UTC) - timedelta(hours=1)
    apps = [
        ("code.exe", "Visual Studio Code"),
        ("chrome.exe", "Google Chrome"),
        ("excel.exe", "Microsoft Excel"),
    ]
    batch = [
        segment(
            start + timedelta(seconds=30 * i), 30, app_id=apps[i % 3][0], app_name=apps[i % 3][1], active=20
        )
        for i in range(120)
    ]

    result = agent.events(*batch)  # one HTTP request for 120 activity events
    assert result.status_code == 200
    assert result.json() == {"accepted": 120, "duplicates": 0, "rejected": []}

    employee = {"employee_id": ObjectId(member.employee_id)}
    assert sync_db["activity_segments"].count_documents(employee) == 120
    assert (
        sync_db["agent_events"].count_documents({**employee, "type": "activity.segment"}) == 0
    )  # no double write
    assert sync_db["activity_daily"].count_documents(employee) <= 6  # 3 apps x at most 2 local days

    report = today_report(ws, employee_id=member.employee_id)
    by_app = {a["app_name"]: a for a in report["applications"]}
    assert set(by_app) == {"Visual Studio Code", "Google Chrome", "Microsoft Excel"}
    assert report["total_seconds"] == 3600
    assert report["active_seconds"] == 2400
    assert by_app["Google Chrome"]["seconds"] == 1200 and by_app["Google Chrome"]["employees"] == 1


def test_resending_a_batch_is_idempotent(ws: Workspace) -> None:
    member, agent = enrol_member(ws, "Retry Rui")
    start = datetime.now(UTC) - timedelta(minutes=30)
    batch = [segment(start + timedelta(minutes=i), 60) for i in range(10)]
    assert agent.events(*batch).json()["accepted"] == 10
    again = agent.events(*batch).json()
    assert again == {"accepted": 0, "duplicates": 10, "rejected": []}
    partially_new = agent.events(*batch[:5], segment(start + timedelta(minutes=20), 60)).json()
    assert partially_new == {"accepted": 1, "duplicates": 5, "rejected": []}
    assert today_report(ws, employee_id=member.employee_id)["total_seconds"] == 660  # never double counted


def test_segment_crossing_midnight_is_split_between_days(ws: Workspace) -> None:
    member, agent = enrol_member(ws, "Night Nia")
    midnight = datetime.combine(datetime.now(UTC).date() - timedelta(days=1), datetime.min.time(), tzinfo=UTC)
    agent.events(segment(midnight - timedelta(minutes=10), 1200, active=600))
    for day, expected in ((midnight.date() - timedelta(days=1), 600), (midnight.date(), 600)):
        report = ws.get(
            "/activity/applications",
            start=day.isoformat(),
            end=day.isoformat(),
            employee_id=member.employee_id,
        ).json()
        assert report["total_seconds"] == expected, (day, report)
        assert report["active_seconds"] == 300


# --------------------------------------------------------------------------- privacy


def test_window_titles_follow_policy_and_are_redacted(ws: Workspace) -> None:
    member, agent = enrol_member(ws, "Title Tom")
    day = datetime.now(UTC).date()
    start = datetime.now(UTC) - timedelta(minutes=40)
    agent.events(segment(start, 60, title="Budget.xlsx - Excel"))
    stored = ws.get(f"/employees/{member.employee_id}/activity", day=day.isoformat()).json()["segments"]
    assert stored[-1]["window_title"] is None  # titles are off by default

    ws.patch("/companies/current/activity-policy", {"capture_window_titles": True})
    agent.events(
        segment(
            start + timedelta(minutes=2),
            60,
            title="Invoice 4111 1111 1111 1111 for jane@acme.com - https://pay.example.com/x?id=9",
        ),
        segment(
            start + timedelta(minutes=4),
            60,
            app_id="1password.exe",
            app_name="1Password",
            title="Bank login - Vault",
        ),
        segment(
            start + timedelta(minutes=6),
            60,
            app_id="msedge.exe",
            app_name="Microsoft Edge",
            title="Search - [InPrivate] - Microsoft Edge",
        ),
        segment(
            start + timedelta(minutes=8),
            60,
            app_id="outlook.exe",
            app_name="Outlook",
            title="RE: salary review - Outlook",
        ),
    )
    titles = [
        s["window_title"]
        for s in ws.get(f"/employees/{member.employee_id}/activity", day=day.isoformat()).json()["segments"]
    ]
    assert titles[-4] == "Invoice [number] for [email] - [link]"
    assert titles[-3:] == [None, None, None]  # password manager, private browsing, e-mail: never stored


def test_excluded_apps_and_disabled_tracking_are_refused(ws: Workspace) -> None:
    member, agent = enrol_member(ws, "Excluded Eli")
    ws.patch("/companies/current/activity-policy", {"excluded_apps": ["Spotify"]})
    start = datetime.now(UTC) - timedelta(minutes=10)
    result = agent.events(
        segment(start, 60, app_id="spotify.exe", app_name="Spotify"), segment(start, 60)
    ).json()
    assert result["accepted"] == 1
    assert [r["reason"] for r in result["rejected"]] == ["excluded_application"]

    ws.patch("/companies/current/activity-policy", {"track_applications": False})
    result = agent.events(segment(start + timedelta(minutes=2), 60)).json()
    assert result["rejected"][0]["reason"] == "tracking_disabled"
    assert today_report(ws, employee_id=member.employee_id)["total_seconds"] == 60


def test_segment_validation(ws: Workspace) -> None:
    _, agent = enrol_member(ws, "Valid Val")
    start = datetime.now(UTC) - timedelta(minutes=5)
    bad_order = segment(start, 60)
    bad_order["started_at"], bad_order["ended_at"] = bad_order["ended_at"], bad_order["started_at"]
    too_long = segment(start - timedelta(hours=5), 5 * 3600)
    over_level = segment(start, 60, level=101)
    with_keys = segment(start, 60)
    with_keys["keystrokes"] = "hunter2"
    too_active = segment(start, 60, active=600)
    for bad in (bad_order, too_long, over_level, with_keys, too_active):
        assert agent.events(bad).status_code == 422, bad


# --------------------------------------------------------------------------- presence & reports


def test_current_application_in_presence(ws: Workspace) -> None:
    member, agent = enrol_member(ws, "Current Cal")
    session = str(uuid.uuid4())
    agent.events(event("session.started", session_id=session))
    beat = agent.client.post(
        "/api/agent/heartbeat",
        json={
            "presence": "active",
            "session_id": session,
            "agent_version": "0.2.0",
            "sent_at": iso(datetime.now(UTC)),
            "current_app": "Figma",
        },
        headers=auth(agent.token),
    )
    assert beat.status_code == 200
    row = next(
        r for r in ws.get("/presence").json()["employees"] if r["employee"]["id"] == member.employee_id
    )
    assert row["current_app"] == "Figma"

    ws.patch("/companies/current/activity-policy", {"track_applications": False})
    agent.client.post(
        "/api/agent/heartbeat",
        json={
            "presence": "active",
            "session_id": session,
            "agent_version": "0.2.0",
            "sent_at": iso(datetime.now(UTC)),
            "current_app": "Figma",
        },
        headers=auth(agent.token),
    )
    row = next(
        r for r in ws.get("/presence").json()["employees"] if r["employee"]["id"] == member.employee_id
    )
    assert row["current_app"] is None


def test_activity_access_scope_and_tenancy(ws: Workspace, client: TestClient) -> None:
    manager = ws.member("Mae Manager", role="MANAGER")
    report_member, report_agent = enrol_member(ws, "Rex Report", manager_employee_id=manager.employee_id)
    outsider, outsider_agent = enrol_member(ws, "Ola Outside")
    start = datetime.now(UTC) - timedelta(minutes=20)
    report_agent.events(segment(start, 300))
    outsider_agent.events(segment(start, 900))
    day = datetime.now(UTC).date().isoformat()

    # Employees always see their own activity; never anyone else's.
    assert (
        ws.get(
            f"/employees/{report_member.employee_id}/activity", token=report_member.token, day=day
        ).status_code
        == 200
    )
    assert (
        ws.get(f"/employees/{outsider.employee_id}/activity", token=report_member.token, day=day).status_code
        == 404
    )
    assert ws.get("/activity/applications", token=report_member.token, start=day, end=day).status_code == 403

    # Managers: only their reporting line.
    assert today_report(ws, token=manager.token)["total_seconds"] == 300
    assert (
        ws.get(f"/employees/{outsider.employee_id}/activity", token=manager.token, day=day).status_code == 404
    )

    rival = str(register(client, company_name="Rival Activity")["access_token"])
    assert today_report(ws, token=rival)["total_seconds"] == 0
    assert ws.get(f"/employees/{report_member.employee_id}/activity", token=rival, day=day).status_code == 404


def test_report_range_validation(ws: Workspace) -> None:
    today = date.today()
    assert (
        ws.get(
            "/activity/applications", start=today.isoformat(), end=(today - timedelta(days=1)).isoformat()
        ).status_code
        == 400
    )
    too_long = ws.get(
        "/activity/applications", start=(today - timedelta(days=120)).isoformat(), end=today.isoformat()
    )
    assert too_long.status_code == 400 and too_long.json()["error"]["code"] == "range_too_long"
