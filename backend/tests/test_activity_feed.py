"""Phase 3: organisation activity feed (backs the dashboard timeline in live mode)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import register
from tests.org_helpers import Workspace


def actions(feed: list[dict[str, object]]) -> list[object]:
    return [item["action"] for item in feed]


def test_feed_lists_workforce_events_newest_first(ws: Workspace) -> None:
    dept = ws.department("Feed Dept")
    hire = ws.employee("Fiona Feed", department_id=dept["id"])
    ws.post(f"/employees/{hire['id']}/status", {"status": "on_leave"})
    ws.post(f"/employees/{hire['id']}/devices", {"name": "Fiona laptop", "os": "windows"})

    feed = ws.get("/activity/feed").json()
    assert actions(feed)[:4] == [
        "device.registered",
        "employee.status_changed",
        "employee.created",
        "department.created",
    ]
    status_event = feed[1]
    assert status_event["subject"] == {"employee_id": hire["id"], "name": "Fiona Feed"}
    assert status_event["actor"]["name"] == "Ada Admin"
    assert status_event["metadata"] == {"from": "active", "to": "on_leave"}
    assert feed[3]["metadata"] == {"name": "Feed Dept"}
    # Security events never appear in the workforce feed.
    assert not {"auth.login", "auth.login_failed", "company.registered"} & set(actions(feed))


def test_feed_respects_manager_scope_and_team_filter(ws: Workspace) -> None:
    manager = ws.member("Mona Manager", role="MANAGER")
    squad = ws.team("Feed Squad")
    report = ws.employee("Rory Report", manager_employee_id=manager.employee_id, team_id=squad["id"])
    outsider = ws.employee("Olga Outsider")

    feed = ws.get("/activity/feed", token=manager.token, limit=50).json()
    subjects = {item["subject"]["employee_id"] for item in feed if item["subject"]}
    assert report["id"] in subjects
    assert outsider["id"] not in subjects
    assert "team.created" not in actions(feed)  # structure events are company-wide only

    team_feed = ws.get("/activity/feed", team_id=squad["id"]).json()
    assert {item["subject"]["employee_id"] for item in team_feed} == {report["id"]}


def test_feed_requires_employee_view(ws: Workspace) -> None:
    member = ws.member("Eli Employee")
    assert ws.get("/activity/feed", token=member.token).status_code == 403
    assert ws.get("/activity/feed", limit=500).status_code == 422


def test_feed_is_tenant_isolated(ws: Workspace, client: TestClient) -> None:
    ws.employee("Secret Sam")
    rival = register(client, company_name="Rival Feed Co")
    feed = ws.get("/activity/feed", token=str(rival["access_token"])).json()
    assert all(item["subject"] is None or item["subject"]["name"] != "Secret Sam" for item in feed)
    assert actions(feed) == []
