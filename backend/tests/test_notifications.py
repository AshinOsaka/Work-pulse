"""Phase 14: alerts & notifications — sources, recipients and scope, preferences, throttling, realtime, centre API."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from bson import ObjectId
from fastapi.testclient import TestClient

from app.models.notification import NotificationType
from app.services.notifications.notifier import BURST_LIMIT, AlertEvent
from tests.org_helpers import Workspace, auth
from tests.test_agent_api import enrol_member, event, iso
from tests.test_live import agent_socket, enable, start, viewer_socket, working


def drain(client: TestClient) -> None:
    client.portal.call(client.app.state.notifier.drain)  # type: ignore[attr-defined]


def notes(ws: Workspace, token: str | None = None, **params: Any) -> list[dict[str, Any]]:
    return ws.get("/notifications", token=token, page_size=100, **params).json()["items"]  # type: ignore[no-any-return]


def prefs(ws: Workspace, token: str, types: dict[str, dict[str, bool]], **extra: Any) -> Any:
    return ws.client.put(
        "/api/notifications/preferences", json={"types": types, **extra}, headers=auth(token)
    )


def company_id(sync_db: Any, user_id: str) -> ObjectId:
    return sync_db["users"].find_one({"_id": ObjectId(user_id)})["company_id"]  # type: ignore[no-any-return]


def test_live_sessions_notify_administrators_but_not_the_person_viewed(ws: Workspace, client: TestClient) -> None:
    enable(ws)
    member, agent = enrol_member(ws, "Vera Viewed")
    other_admin = ws.member("Ada Second", role="COMPANY_ADMIN")
    working(agent)
    with (
        client.websocket_connect(f"/api/ws?token={other_admin.token}") as admin_ws,
        agent_socket(client, agent) as agent_ws,
    ):
        assert admin_ws.receive_json()["type"] == "connection.ready"
        sid = start(ws, member.employee_id).json()["id"]
        with viewer_socket(client, sid, ws.admin.token) as viewer:
            viewer.send_json({"type": "state", "state": "connected"})
            pushed = admin_ws.receive_json()
            assert pushed["type"] == "notification.created"
            assert pushed["payload"]["notification"]["type"] == "live_session_started"
            assert "is viewing Vera Viewed's screen live" in pushed["payload"]["notification"]["title"]
            viewer.send_json({"type": "stop"})
            viewer.receive_json()
            agent_ws.receive_json()
    drain(client)
    # The person viewed gets no notification (their tray icon shows LIVE instead); other admins are told.
    assert notes(ws, member.token) == []
    assert {n["type"] for n in notes(ws, other_admin.token)} == {"live_session_started", "live_session_ended"}
    assert notes(ws) == []  # the viewer isn't told about their own action


def test_shift_alerts_respect_scope_opt_in_freshness_and_once_a_day(
    ws: Workspace, client: TestClient, email_sender: Any
) -> None:
    manager = ws.member("Mara Manager", role="MANAGER")
    outsider = ws.member("Omar Outside", role="MANAGER")
    member, agent = enrol_member(ws, "Sid Shift", manager_employee_id=manager.employee_id)
    on = {"in_app": True, "email": True}
    for who in (manager, outsider):
        assert prefs(ws, who.token, {"shift_started": on, "shift_ended": on}).status_code == 200
    sent_before = len(email_sender.messages)

    s1, s2 = str(uuid.uuid4()), str(uuid.uuid4())
    agent.events(event("session.started", session_id=s1))
    agent.events(event("session.stopped", session_id=s1, reason="user", active_seconds=60, idle_seconds=0))
    agent.events(event("session.started", session_id=s2))  # second start the same day: no new "started"
    stale = datetime.now(UTC) - timedelta(hours=3)
    agent.events(
        event(
            "session.stopped",
            stale,
            session_id=str(uuid.uuid4()),
            reason="user",
            active_seconds=60,
            idle_seconds=0,
        )
    )
    drain(client)

    mine = notes(ws, manager.token)
    assert sorted(n["type"] for n in mine) == ["shift_ended", "shift_started"]
    assert next(n for n in mine if n["type"] == "shift_started")["employee"]["name"] == "Sid Shift"
    assert notes(ws, outsider.token) == []  # not in their reporting line
    assert notes(ws, member.token) == []  # employees don't get shift alerts about themselves
    new_mail = email_sender.messages[sent_before:]
    assert len(new_mail) == 2 and all(m.to == manager.email for m in new_mail)
    assert new_mail[0].subject.startswith("[WorkPulse] Sid Shift")

    # Defaults: shift alerts are off until someone opts in.
    assert notes(ws) == []


def test_closing_the_agent_or_turning_start_up_off_alerts_the_people_who_view_activity(
    ws: Workspace, client: TestClient
) -> None:
    manager = ws.member("Mara Closer", role="MANAGER")
    outsider = ws.member("Omar Elsewhere", role="MANAGER")
    member, agent = enrol_member(ws, "Abhi Agent", manager_employee_id=manager.employee_id)
    now = datetime.now(UTC)

    # Quit from the tray (0.8.7 says so), End Task found on the next start, and start-up switched off.
    quit_at, killed_at = now - timedelta(minutes=5), iso(now - timedelta(minutes=1))
    assert agent.events(event("agent.stopped", quit_at, reason="tray_quit")).status_code == 200
    assert agent.events(event("agent.closed", now, stopped_at=killed_at)).status_code == 200
    assert agent.events(event("agent.protection", now, what="startup_disabled")).status_code == 200
    # An old agent's plain "quit" and anything uploaded late stay silent.
    agent.events(event("agent.stopped", now, reason="quit"))
    agent.events(event("agent.closed", now - timedelta(hours=3), stopped_at=iso(now - timedelta(hours=3))))
    bad = agent.events(event("agent.protection", now, what="something_else"))
    assert bad.status_code == 422
    drain(client)

    mine = {n["type"]: n for n in notes(ws, manager.token)}
    assert set(mine) == {"agent_closed", "agent_protection"}
    # Closed twice within the throttle window: one alert with a count, showing the latest.
    assert mine["agent_closed"]["count"] == 2
    assert mine["agent_closed"]["title"] == "WorkPulse was force-closed on Abhi Agent's computer"
    assert "End Task" in mine["agent_closed"]["body"]
    assert mine["agent_protection"]["title"] == "WorkPulse start-up was turned off on Abhi Agent's computer"
    assert notes(ws, outsider.token) == []  # not in their reporting line
    assert notes(ws, member.token) == []  # never sent to the person themselves
    assert {n["type"] for n in notes(ws)} >= {"agent_closed", "agent_protection"}  # admins: on by default

    # Each is on the activity timeline, with how it happened (the late one too: it did happen).
    feed = [f for f in ws.get("/activity/feed", limit=50).json() if f["action"].startswith("agent.")]
    hows = sorted(f["metadata"].get("how") or f["metadata"].get("what") for f in feed)
    assert hows == ["startup_disabled", "tray", "unexpected", "unexpected"]


def test_repeats_are_folded_and_bursts_go_quiet(
    ws: Workspace, client: TestClient, sync_db: Any, email_sender: Any
) -> None:
    member = ws.member("Rex Repeat")
    on = {"in_app": True, "email": True}
    assert prefs(ws, ws.admin.token, {"shift_ended": on}).status_code == 200
    dispatcher = client.app.state.notification_dispatcher  # type: ignore[attr-defined]
    cid = company_id(sync_db, ws.admin.user_id)
    sent_before = len(email_sender.messages)

    def ended(employee: str, subject: str | None = None) -> AlertEvent:
        return AlertEvent(
            company_id=cid,
            type=NotificationType.SHIFT_ENDED,
            title="{employee} stopped work",
            body="A work session ended.",
            employee_id=ObjectId(employee),
            subject=subject,
            permission=None,
            user_ids=[ObjectId(ws.admin.user_id)],
        )

    for _ in range(3):
        client.portal.call(dispatcher.handle, ended(member.employee_id))
    (only,) = notes(ws)
    assert only["count"] == 3 and only["read"] is False
    assert len(email_sender.messages) - sent_before == 1  # repeats never re-email

    ws.post("/notifications/mark", {"ids": [only["id"]], "read": True})
    client.portal.call(dispatcher.handle, ended(member.employee_id))
    (again,) = notes(ws)
    assert again["count"] == 4 and again["read"] is False  # a new occurrence surfaces it again

    for i in range(BURST_LIMIT + 5):
        client.portal.call(dispatcher.handle, ended(member.employee_id, subject=f"burst-{i}"))
    assert ws.get("/notifications/unread-count").json()["unread"] == BURST_LIMIT + 6  # nothing is lost…
    assert len(email_sender.messages) - sent_before <= BURST_LIMIT  # …but nobody is flooded


def test_scanner_finds_offline_idle_stale_overdue_and_deadlines_once(
    ws: Workspace, client: TestClient, sync_db: Any
) -> None:
    gone, _ = enrol_member(ws, "Gus Gone")
    stale, _ = enrol_member(ws, "Sal Stale")
    idle, _ = enrol_member(ws, "Ida Idle")
    assert prefs(ws, ws.admin.token, {"extended_idle": {"in_app": True, "email": False}}).status_code == 200
    now = datetime.now(UTC)
    devices = sync_db["devices"]
    devices.update_one(
        {"employee_id": ObjectId(gone.employee_id)},
        {
            "$set": {
                "current_session_id": "s-1",
                "last_seen_at": now - timedelta(minutes=10),
                "agent_stopped_at": None,
            }
        },
    )
    devices.update_one(
        {"employee_id": ObjectId(stale.employee_id)}, {"$set": {"last_seen_at": now - timedelta(hours=30)}}
    )
    devices.update_one(
        {"employee_id": ObjectId(idle.employee_id)},
        {
            "$set": {
                "current_session_id": "s-2",
                "last_seen_at": now,
                "presence": "idle",
                "presence_since": now - timedelta(minutes=45),
            }
        },
    )
    project = ws.post(
        "/projects",
        {
            "name": "Deadline",
            "key": "DL",
            "member_ids": [gone.employee_id],
            "due_date": (now + timedelta(days=1)).date().isoformat(),
        },
    ).json()
    yesterday = (now - timedelta(days=1)).date().isoformat()
    ws.post(
        "/tasks",
        {
            "project_id": project["id"],
            "title": "Late work",
            "assignee_ids": [gone.employee_id],
            "due_date": yesterday,
        },
    )

    scanner = client.app.state.alert_scanner  # type: ignore[attr-defined]
    client.portal.call(scanner.scan_once)
    client.portal.call(scanner.scan_once)  # a second pass announces nothing new
    drain(client)

    admin_types = sorted(n["type"] for n in notes(ws))
    assert admin_types.count("employee_offline") == 1
    assert admin_types.count("device_offline") == 1
    assert admin_types.count("extended_idle") == 1
    assert admin_types.count("project_deadline") == 1
    offline = next(n for n in notes(ws, type="employee_offline"))
    assert offline["employee"]["name"] == "Gus Gone" and offline["severity"] == "warning"
    (overdue,) = notes(ws, gone.token, type="task_overdue")
    assert overdue["title"].startswith("DL-") and overdue["link"].startswith(
        f"/projects/{project['id']}?task="
    )
    assert notes(ws, gone.token, type="employee_offline") == []  # activity alerts need View activity


def test_uninstall_and_sign_out_are_reported_at_once(ws: Workspace, client: TestClient) -> None:
    _gone, gone_agent = enrol_member(ws, "Una Uninstall")
    _left, left_agent = enrol_member(ws, "Sid Signout")
    now = datetime.now(UTC)
    assert gone_agent.events(event("agent.stopped", now, reason="uninstall")).status_code == 200
    assert left_agent.events(event("agent.stopped", now, reason="sign_out")).status_code == 200
    drain(client)
    titles = {n["title"] for n in notes(ws, type="agent_closed")}
    assert titles == {
        "WorkPulse was uninstalled on Una Uninstall's computer",
        "Sid Signout signed out of WorkPulse",
    }
    feed = [f for f in ws.get("/activity/feed", limit=50).json() if f["action"] == "agent.closed"]
    assert sorted(f["metadata"]["how"] for f in feed) == ["sign_out", "uninstall"]


def test_start_of_day_check_finds_computers_that_have_not_reported(
    ws: Workspace, client: TestClient, sync_db: Any
) -> None:
    absent, _ = enrol_member(ws, "Abe Absent")
    early, _ = enrol_member(ws, "Eva Early")
    leave, _ = enrol_member(ws, "Lou Leave")
    newbie, _ = enrol_member(ws, "Ned New")
    day = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    devices = sync_db["devices"]

    def device(member: Any, created: datetime, seen: datetime) -> None:
        devices.update_one(
            {"employee_id": ObjectId(member.employee_id)},
            {"$set": {"status": "active", "created_at": created, "last_seen_at": seen}},
        )

    device(absent, day - timedelta(days=5), day - timedelta(hours=10))  # last seen yesterday evening
    device(early, day - timedelta(days=5), day + timedelta(hours=8, minutes=55))
    device(leave, day - timedelta(days=5), day - timedelta(days=3))
    device(newbie, day + timedelta(hours=8), day + timedelta(hours=8))  # set up this morning: not counted
    sync_db["employees"].update_one({"_id": ObjectId(leave.employee_id)}, {"$set": {"status": "on_leave"}})
    scanner = client.app.state.alert_scanner  # type: ignore[attr-defined]

    def scan(at: datetime) -> list[dict[str, Any]]:
        client.portal.call(scanner.scan_once, at)
        drain(client)
        return notes(ws, type="not_started")

    assert scan(day + timedelta(hours=10)) == []  # off until an administrator switches it on
    settings = {
        "timezone": "UTC",
        "work_days": [1, 2, 3, 4, 5, 6, 7],
        "start_check_enabled": True,
        "start_check_time": "09:00",
        "start_check_grace_minutes": 30,
    }
    saved = ws.patch("/companies/current", settings)
    assert saved.status_code == 200 and saved.json()["start_check_time"] == "09:00"
    assert ws.patch("/companies/current", {"start_check_time": "9am"}).status_code == 422
    assert ws.patch("/companies/current", {"start_check_grace_minutes": 0}).status_code == 422

    assert scan(day + timedelta(hours=9, minutes=20)) == []  # still within the grace minutes
    (alert,) = scan(day + timedelta(hours=9, minutes=31))
    assert alert["title"] == "Abe Absent hasn't started WorkPulse today"
    assert "09:00" in alert["body"]
    assert len(scan(day + timedelta(hours=10))) == 1  # once per person per day

    # A holiday, and the hours long after the start, stay quiet.
    sync_db["notifications"].delete_many({"type": "not_started"})
    sync_db["companies"].update_one(
        {"_id": company_id(sync_db, ws.admin.user_id)}, {"$set": {"holidays": [day.date().isoformat()]}}
    )
    assert scan(day + timedelta(hours=9, minutes=45)) == []
    sync_db["companies"].update_one({"_id": company_id(sync_db, ws.admin.user_id)}, {"$set": {"holidays": []}})
    assert scan(day + timedelta(hours=15)) == []


def test_centre_filters_marks_preferences_and_privacy(
    ws: Workspace, client: TestClient, sync_db: Any
) -> None:
    member = ws.member("Paz Private")
    dispatcher = client.app.state.notification_dispatcher  # type: ignore[attr-defined]
    cid = company_id(sync_db, ws.admin.user_id)
    for type_, subject in (
        (NotificationType.TASK_OVERDUE, "t1"),
        (NotificationType.PROJECT_DEADLINE, "p1"),
        (NotificationType.TASK_OVERDUE, "t2"),
    ):
        client.portal.call(
            dispatcher.handle,
            AlertEvent(
                company_id=cid,
                type=type_,
                title="T",
                body="B",
                subject=subject,
                user_ids=[ObjectId(ws.admin.user_id)],
                employee_id=ObjectId(member.employee_id),
            ),
        )
    page = ws.get("/notifications", type="task_overdue").json()
    assert page["total"] == 2 and page["unread"] == 3
    assert len(notes(ws, severity="warning")) == 3
    assert len(notes(ws, employee_id=member.employee_id)) == 3
    marked = ws.post("/notifications/mark", {"all": True, "type": "task_overdue", "read": True}).json()
    assert marked == {"updated": 2, "unread": 1}
    assert len(notes(ws, read=False)) == 1 and len(notes(ws, read=True)) == 2
    assert ws.post("/notifications/mark", {"all": True, "read": True}).json()["unread"] == 0
    assert notes(ws, member.token) == []  # nobody sees anyone else's notifications

    member_prefs = ws.get("/notifications/preferences", token=member.token).json()
    by_type = {t["type"]: t for t in member_prefs["types"]}
    assert by_type["employee_offline"]["applies"] is False and by_type["task_overdue"]["applies"] is True
    assert by_type["task_overdue"]["channels"] == {"in_app": True, "email": False}  # e-mail is opt-in
    assert {c["key"]: c["available"] for c in member_prefs["channels"]}["slack"] is False
    updated = prefs(
        ws, member.token, {"task_overdue": {"in_app": False, "email": True}}, throttle_minutes=120
    ).json()
    assert updated["throttle_minutes"] == 120
    assert {t["type"]: t for t in updated["types"]}["task_overdue"]["channels"] == {
        "in_app": False,
        "email": True,
    }
    assert prefs(ws, member.token, {}, throttle_minutes=1).status_code == 422
