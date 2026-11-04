"""Attendance report: active time per person against the company's required hours, per day."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from tests.org_helpers import Workspace
from tests.test_agent_api import enrol_member, event

# Monday to Friday 7h 50m, Saturday 5h 20m, Sunday off.
REQUIRED = [470, 470, 470, 470, 470, 320, 0]


def _past_monday() -> datetime:
    """A Monday at least a week ago, 00:00 UTC (the test workspace's timezone is UTC)."""
    today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return today - timedelta(days=today.weekday() + 7)


def test_required_hours_are_saved_and_validated(ws: Workspace) -> None:
    assert ws.get("/companies/current").json()["required_minutes"] == [0] * 7
    saved = ws.patch("/companies/current", {"required_minutes": REQUIRED})
    assert saved.status_code == 200, saved.text
    assert saved.json()["required_minutes"] == REQUIRED
    assert ws.patch("/companies/current", {"required_minutes": [470] * 6}).status_code == 422
    assert ws.patch("/companies/current", {"required_minutes": [2000] + [0] * 6}).status_code == 422


def test_report_compares_active_time_with_required_hours(ws: Workspace) -> None:
    ws.patch("/companies/current", {"required_minutes": REQUIRED, "work_days": [1, 2, 3, 4, 5, 6]})
    member, agent = enrol_member(ws, "Attendance Anu")
    monday = _past_monday()

    # Monday: signed in 09:30-18:00 (8h 30m), 8h active, 30m idle -> meets 7h 50m.
    sid = str(uuid.uuid4())
    agent.events(
        event("session.started", monday + timedelta(hours=9.5), session_id=sid),
        event(
            "session.stopped",
            monday + timedelta(hours=18),
            session_id=sid,
            reason="user",
            active_seconds=8 * 3600,
            idle_seconds=1800,
        ),
    )
    # Wednesday: 09:30-13:30, 3h 30m active -> short. Tuesday: nothing -> absent.
    sid2 = str(uuid.uuid4())
    wednesday = monday + timedelta(days=2)
    agent.events(
        event("session.started", wednesday + timedelta(hours=9.5), session_id=sid2),
        event(
            "session.stopped",
            wednesday + timedelta(hours=13.5),
            session_id=sid2,
            reason="user",
            active_seconds=3.5 * 3600,
            idle_seconds=1800,
        ),
    )

    start, end = monday.date().isoformat(), (monday + timedelta(days=6)).date().isoformat()
    report = ws.get("/presence/attendance/report", start=start, end=end, employee_id=member.employee_id)
    assert report.status_code == 200, report.text
    (row,) = report.json()["rows"]
    days = {d["day"]: d for d in row["days"]}

    mon = days[start]
    assert mon["status"] == "met"
    assert mon["active_seconds"] == 8 * 3600 and mon["work_seconds"] == 8.5 * 3600
    assert mon["expected_seconds"] == 470 * 60
    assert mon["first_in"].startswith(f"{start}T09:30") and mon["last_out"].startswith(f"{start}T18:00")
    assert len(mon["sessions"]) == 1

    assert days[(monday + timedelta(days=1)).date().isoformat()]["status"] == "absent"
    assert days[wednesday.date().isoformat()]["status"] == "short"
    assert days[(monday + timedelta(days=5)).date().isoformat()]["expected_seconds"] == 320 * 60  # Saturday
    assert days[(monday + timedelta(days=6)).date().isoformat()]["status"] == "holiday"  # Sunday off

    assert row["logged_seconds"] == round(11.5 * 3600)
    assert row["expected_seconds"] == 5 * 470 * 60 + 320 * 60
    assert row["working_days"] == 6 and row["holidays"] == 1
    assert row["untracked_days"] == 4  # Tue, Thu, Fri, Sat
    assert row["days_met"] == 1


def test_a_standard_employee_sees_only_their_own_row(ws: Workspace) -> None:
    member, _ = enrol_member(ws, "Self Sana")
    enrol_member(ws, "Other Omar")
    today = datetime.now(UTC).date().isoformat()
    own = ws.get("/presence/attendance/report", token=member.token, start=today, end=today)
    assert own.status_code == 200, own.text
    assert [r["employee"]["id"] for r in own.json()["rows"]] == [member.employee_id]
    # The admin sees everyone active.
    assert len(ws.get("/presence/attendance/report", start=today, end=today).json()["rows"]) >= 2


def test_report_range_validation(ws: Workspace) -> None:
    today = datetime.now(UTC).date()
    bad = ws.get(
        "/presence/attendance/report", start=today.isoformat(), end=(today - timedelta(days=1)).isoformat()
    )
    assert bad.status_code == 400
