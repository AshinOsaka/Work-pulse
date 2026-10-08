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
from tests.test_agent_api import enrol_member, event
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


def test_live_sessions_notify_the_person_viewed_in_realtime(ws: Workspace, client: TestClient) -> None:
    enable(ws)
    member, agent = enrol_member(ws, "Vera Viewed")
    other_admin = ws.member("Ada Second", role="COMPANY_ADMIN")
    working(agent)
    with (
        client.websocket_connect(f"/api/ws?token={member.token}") as member_ws,
        agent_socket(client, agent) as agent_ws,
    ):
        assert member_ws.receive_json()["type"] == "connection.ready"
        sid = start(ws, member.employee_id).json()["id"]
        with viewer_socket(client, sid, ws.admin.token) as viewer:
            viewer.send_json({"type": "state", "state": "connected"})
            pushed = member_ws.receive_json()
            assert pushed["type"] == "notification.created"
            assert pushed["payload"]["notification"]["type"] == "live_session_started"
            assert "is viewing Vera Viewed's screen live" in pushed["payload"]["notification"]["title"]
            assert pushed["payload"]["unread_count"] == 1
            viewer.send_json({"type": "stop"})
            viewer.receive_json()
            agent_ws.receive_json()
    drain(client)
    assert {n["type"] for n in notes(ws, member.token)} == {"live_session_started", "live_session_ended"}
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
