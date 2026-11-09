"""Time claims: meetings and other work away from the computer, the daily limit, review, and attendance."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient

from tests.org_helpers import Workspace
from tests.test_agent_api import enrol_member, event


def drain(client: TestClient) -> None:
    client.portal.call(client.app.state.notifier.drain)  # type: ignore[attr-defined]


def _day(days_ago: int) -> str:
    return (datetime.now(UTC) - timedelta(days=days_ago)).date().isoformat()


def claim(ws: Workspace, token: str, day: str, start: str, end: str, **fields: Any) -> Any:
    body = {"day": day, "start_time": start, "end_time": end, "kind": "client_meeting", "with_whom": "ABC Ltd"}
    return ws.post("/time-claims", {**body, **fields}, token=token)


def notifications(ws: Workspace, token: str) -> list[dict[str, Any]]:
    drain(ws.client)
    return ws.get("/notifications", token=token).json()["items"]  # type: ignore[no-any-return]


def test_within_the_daily_limit_counts_at_once_and_managers_are_told(ws: Workspace) -> None:
    member = ws.member("Meeting Mia")
    day = _day(2)
    first = claim(ws, member.token, day, "10:00", "11:00", note="Project demo")
    assert first.status_code == 201, first.text
    body = first.json()
    assert body["status"] == "approved" and body["auto_approved"] is True and body["minutes"] == 60
    assert body["can_delete"] is True and body["can_review"] is False  # nobody reviews their own time

    # 1h + 1h is still within the default 2 hours.
    assert claim(ws, member.token, day, "14:00", "15:00").json()["status"] == "approved"
    # Over the limit for that day (2h already logged): waits for a manager.
    third = claim(ws, member.token, day, "16:00", "16:30")
    assert third.json()["status"] == "pending" and third.json()["auto_approved"] is False

    items = notifications(ws, ws.admin.token)
    logged = [n for n in items if n["type"] == "time_claim_logged"]
    assert len(logged) == 3
    assert any("asks you to approve 30m" in n["title"] for n in logged)
    assert any("Client meeting with ABC Ltd" in n["body"] and "Project demo" in n["body"] for n in logged)
    assert ws.get("/time-claims/pending-count").json() == {"pending": 1}


def test_validation_overlap_and_dates(ws: Workspace) -> None:
    member = ws.member("Rules Ravi")
    day = _day(1)
    assert claim(ws, member.token, day, "10:00", "11:00").status_code == 201
    overlap = claim(ws, member.token, day, "10:30", "11:30")
    assert overlap.status_code == 409 and overlap.json()["error"]["code"] == "overlap"
    assert claim(ws, member.token, day, "12:00", "11:00").json()["error"]["code"] == "invalid_range"
    assert claim(ws, member.token, day, "12:00", "12:02").json()["error"]["code"] == "too_short"
    assert claim(ws, member.token, _day(10), "10:00", "11:00").json()["error"]["code"] == "too_old"
    assert claim(ws, member.token, _day(-1), "10:00", "11:00").json()["error"]["code"] == "future_day"
    assert claim(ws, member.token, day, "10:00", "11:00", with_whom="  ").status_code == 422


def test_review_rules(ws: Workspace) -> None:
    ws.patch("/companies/current", {"time_claim_auto_minutes": 0})  # every claim needs approval
    member = ws.member("Review Rani")
    other = ws.member("Other Omar")
    day = _day(1)
    pending = claim(ws, member.token, day, "09:00", "12:00").json()
    assert pending["status"] == "pending"

    # A standard employee can't review anyone's time, and only sees their own.
    denied = ws.post(f"/time-claims/{pending['id']}/review", {"decision": "approve"}, token=other.token)
    assert denied.status_code in (403, 404)
    assert ws.get("/time-claims", token=other.token).json()["items"] == []

    listing = ws.get("/time-claims", status="pending").json()
    assert [c["id"] for c in listing["items"]] == [pending["id"]] and listing["items"][0]["can_review"] is True

    approved = ws.post(f"/time-claims/{pending['id']}/review", {"decision": "approve"})
    assert approved.status_code == 200 and approved.json()["status"] == "approved"
    assert approved.json()["reviewed_by"]
    # Reviewed time can't be deleted by the employee any more; a manager can still reject it.
    assert ws.delete(f"/time-claims/{pending['id']}", token=member.token).status_code == 403
    rejected = ws.post(f"/time-claims/{pending['id']}/review", {"decision": "reject", "note": "Not a meeting"})
    assert rejected.json()["status"] == "rejected" and rejected.json()["review_note"] == "Not a meeting"

    # Both decisions on the same claim fold into one notification that shows the latest.
    (told,) = [n for n in notifications(ws, member.token) if n["type"] == "time_claim_reviewed"]
    assert told["count"] == 2 and "rejected" in told["title"] and "Not a meeting" in told["body"]

    # Unreviewed time can be deleted by its owner, and only by them.
    mine = claim(ws, member.token, _day(2), "09:00", "10:00").json()
    assert ws.delete(f"/time-claims/{mine['id']}", token=other.token).status_code == 404
    assert ws.delete(f"/time-claims/{mine['id']}", token=member.token).status_code == 204


def test_daily_limit_setting_is_validated(ws: Workspace) -> None:
    assert ws.get("/companies/current").json()["time_claim_auto_minutes"] == 120
    assert ws.patch("/companies/current", {"time_claim_auto_minutes": 90}).json()["time_claim_auto_minutes"] == 90
    assert ws.patch("/companies/current", {"time_claim_auto_minutes": 1000}).status_code == 422


def test_approved_time_counts_in_attendance_without_double_counting(ws: Workspace) -> None:
    """A 2h meeting during a signed-in day: its idle part moves to active; productivity doesn't change."""
    ws.patch("/companies/current", {"required_minutes": [480] * 7, "work_days": [1, 2, 3, 4, 5, 6, 7]})
    member, agent = enrol_member(ws, "Attendance Anu")
    day = _day(2)
    midnight = datetime.fromisoformat(f"{day}T00:00:00+00:00")
    sid = str(uuid.uuid4())

    # Signed in 09:00-17:00 (8h). 13:00-15:00 was a meeting: no input except 30m of typing in a 14:00-14:30
    # segment that was fully active. Everything else had input.
    def segment(start_h: float, hours: float, active_seconds: int) -> dict[str, Any]:
        start = midnight + timedelta(hours=start_h)
        return {
            "session_id": sid,
            "app_id": "code.exe",
            "app_name": "VS Code",
            "started_at": start.isoformat(),
            "ended_at": (start + timedelta(hours=hours)).isoformat(),
            "active_seconds": active_seconds,
            "activity_level": 50,
        }

    agent.events(
        event("session.started", midnight + timedelta(hours=9), session_id=sid),
        event("activity.segment", midnight + timedelta(hours=13), **segment(9, 4, 4 * 3600)),
        event("activity.segment", midnight + timedelta(hours=14.5), **segment(14, 0.5, 1800)),
        event("activity.segment", midnight + timedelta(hours=17), **segment(15, 2, 2 * 3600)),
        event(
            "session.stopped",
            midnight + timedelta(hours=17),
            session_id=sid,
            reason="user",
            active_seconds=round(6.5 * 3600),
            idle_seconds=round(1.5 * 3600),
        ),
    )

    def attendance() -> dict[str, Any]:
        rows = ws.get("/presence/attendance/report", start=day, end=day, employee_id=member.employee_id).json()
        return rows["rows"][0]  # type: ignore[no-any-return]

    def productivity_active() -> int:
        body = ws.get(f"/productivity/employees/{member.employee_id}", start=day, end=day).json()
        return int(body["totals"]["active_seconds"])

    before, productivity_before = attendance(), productivity_active()
    assert before["days"][0]["active_seconds"] == round(6.5 * 3600) and before["days"][0]["status"] == "short"

    made = claim(ws, member.token, day, "13:00", "15:00")
    assert made.json()["status"] == "approved"
    after = attendance()
    today = after["days"][0]
    # 2h claimed, 30m of it was already active at the computer: 1h 30m more.
    assert today["meeting_seconds"] == 90 * 60
    assert today["active_seconds"] == round(6.5 * 3600) + 90 * 60 and today["status"] == "met"
    assert today["idle_seconds"] == 0
    assert today["work_seconds"] == before["days"][0]["work_seconds"]
    assert after["meeting_seconds"] == 90 * 60 and after["logged_seconds"] == 8 * 3600
    assert productivity_active() == productivity_before  # productivity is untouched

    # Rejected time stops counting.
    ws.post(f"/time-claims/{made.json()['id']}/review", {"decision": "reject"})
    assert attendance()["days"][0]["meeting_seconds"] == 0


def test_a_day_away_from_the_computer_is_not_absent(ws: Workspace) -> None:
    """A field visit with the laptop closed: the whole claim counts, and the day isn't marked absent."""
    ws.patch("/companies/current", {"required_minutes": [120] * 7, "work_days": [1, 2, 3, 4, 5, 6, 7]})
    member = ws.member("Field Farah")
    day = _day(3)
    assert claim(ws, member.token, day, "10:00", "12:00", kind="field_visit").json()["status"] == "approved"
    row = ws.get("/presence/attendance/report", start=day, end=day, employee_id=member.employee_id).json()
    (only,) = row["rows"][0]["days"]
    assert only["meeting_seconds"] == 2 * 3600 and only["active_seconds"] == 2 * 3600
    assert only["status"] == "met" and only["idle_seconds"] == 0
