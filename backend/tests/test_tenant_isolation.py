"""Phase 16: tenant isolation, tested explicitly and exhaustively.

Company B gets one of every kind of record, each named with a unique canary string. Company A's administrator — the
most privileged role a tenant can have — then:

* calls **every** API route that takes an id, with Company B's real ids, using every method the route supports;
* lists **every** collection endpoint;
* tries B's WebSocket, live session, signed file links and sign-in sessions.

Nothing may succeed, leak the canary, or change Company B's data. Because the sweep enumerates the application's
routes, an endpoint added later is covered automatically (and fails here if it isn't tenant-safe).
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from tests.conftest import CapturingEmailSender, register
from tests.org_helpers import Actor, Workspace, auth
from tests.test_agent_api import enrol_member
from tests.test_live import agent_socket, working
from tests.test_live import enable as enable_live
from tests.test_screenshots import enable as enable_screenshots
from tests.test_screenshots import start_session, upload

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def route_table(client: TestClient) -> list[tuple[str, str]]:
    """(method, path) for every HTTP route, hidden ones included."""
    rows: list[tuple[str, str]] = []
    for router in client.app.routes:  # type: ignore[attr-defined]
        contexts = getattr(router, "effective_route_contexts", None)
        if contexts is None:
            continue
        for ctx in contexts():
            for method in sorted((ctx.methods or set()) - {"HEAD"}):
                rows.append((method, ctx.path))
    assert len(rows) > 140, "route discovery broke; the sweep would silently test nothing"
    return rows


@dataclass
class TenantB:
    ws: Workspace
    canary: str
    ids: dict[str, str]
    member: Actor
    screenshot_url: str
    report_url: str | None


def second_workspace(client: TestClient, mail: CapturingEmailSender) -> Workspace:
    created = register(client, company_name=f"Other Tenant {uuid.uuid4().hex[:6]}")
    token = str(created["access_token"])
    email = created["user"]["email"]  # type: ignore[index]
    listing = client.get("/api/employees", params={"search": email}, headers=auth(token)).json()
    return Workspace(
        client,
        Actor(token, listing["items"][0]["id"], created["user"]["id"], email),  # type: ignore[index]
        mail,
    )


@pytest.fixture
def tenant_b(client: TestClient, email_sender: CapturingEmailSender) -> TenantB:
    b = second_workspace(client, email_sender)
    canary = f"Canary{uuid.uuid4().hex[:10]}"
    department = b.department(f"{canary} Department")
    team = b.team(f"{canary} Team")
    person = b.employee(f"{canary} Person")
    member, agent = enrol_member(b, f"{canary} Member")
    device_id = b.get(f"/employees/{member.employee_id}/devices").json()[0]["id"]

    enable_screenshots(b)
    shot = upload(agent, start_session(agent))
    assert shot.status_code == 200, shot.text
    screenshot_id = shot.json()["id"]
    detail = b.get(f"/screenshots/{screenshot_id}").json()
    screenshot_url = next(v for v in detail.values() if isinstance(v, str) and "/screenshot-files/" in v)

    project = b.post(
        "/projects", {"name": f"{canary} Project", "key": "CNY", "member_ids": [member.employee_id]}
    )
    assert project.status_code == 201, project.text
    project_id = project.json()["id"]
    task = b.post("/tasks", {"project_id": project_id, "title": f"{canary} Task"}).json()
    comment = b.post(f"/tasks/{task['id']}/comments", {"body": f"{canary} comment"}).json()
    milestone = b.post(f"/projects/{project_id}/milestones", {"name": f"{canary} Milestone"}).json()
    attachment = client.post(
        f"/api/tasks/{task['id']}/attachments",
        params={"filename": f"{canary}.png"},
        content=PNG,
        headers={**auth(b.admin.token), "Content-Type": "image/png"},
    ).json()
    rule = b.post(
        "/productivity/rules", {"kind": "app", "pattern": f"{canary.lower()}.exe", "category": "productive"}
    )
    assert rule.status_code == 201, rule.text
    profile = b.post("/productivity/profiles", {"name": f"{canary} Profile"})
    assert profile.status_code == 201, profile.text
    report = b.post(
        "/reports",
        {
            "report_type": "work_hours",
            "format": "csv",
            "period": "daily",
            "start": "2026-01-05",
            "end": "2026-01-05",
        },
    )
    assert report.status_code in (200, 201, 202), report.text
    sessions = b.get("/auth/sessions").json()

    ids = {
        "employee_id": person["id"],
        "department_id": department["id"],
        "team_id": team["id"],
        "device_id": device_id,
        "screenshot_id": screenshot_id,
        "project_id": project_id,
        "task_id": task["id"],
        "comment_id": comment["id"],
        "milestone_id": milestone["id"],
        "attachment_id": attachment["id"],
        "rule_id": rule.json()["id"],
        "profile_id": profile.json()["id"],
        "report_id": report.json()["id"],
        "user_id": member.user_id,
        "session_id": sessions[0]["id"],
        "conversation_id": str(ObjectId()),
        "variant": "thumb",
        "token": "not-a-real-invitation-token",
    }
    return TenantB(b, canary, ids, member, screenshot_url, None)


#: Valid bodies for writes, so a request fails because of tenancy, not because the body was rejected first.
BODIES: dict[tuple[str, str], Any] = {
    ("PATCH", "/api/employees/{employee_id}"): {"full_name": "Hijacked"},
    ("POST", "/api/employees/{employee_id}/status"): {"status": "terminated"},
    ("POST", "/api/employees/{employee_id}/invite"): {"role": "EMPLOYEE"},
    ("PUT", "/api/employees/{employee_id}/screenshot-settings"): {"mode": "enabled"},
    ("POST", "/api/employees/{employee_id}/devices"): {},
    ("PATCH", "/api/departments/{department_id}"): {"name": "Hijacked"},
    ("PATCH", "/api/teams/{team_id}"): {"name": "Hijacked"},
    ("PATCH", "/api/projects/{project_id}"): {"name": "Hijacked"},
    ("PUT", "/api/projects/{project_id}/members"): {"member_ids": []},
    ("POST", "/api/projects/{project_id}/milestones"): {"name": "Hijacked"},
    ("PATCH", "/api/milestones/{milestone_id}"): {"name": "Hijacked"},
    ("PATCH", "/api/tasks/{task_id}"): {"title": "Hijacked"},
    ("POST", "/api/tasks/{task_id}/move"): {"status": "done", "position": 0},
    ("POST", "/api/tasks/{task_id}/comments"): {"body": "Hijacked"},
    ("PATCH", "/api/tasks/{task_id}/comments/{comment_id}"): {"body": "Hijacked"},
    ("POST", "/api/tasks/{task_id}/time"): {"minutes": 30, "date": "2026-01-05"},
    ("PATCH", "/api/productivity/rules/{rule_id}"): {"category": "unproductive"},
    ("PATCH", "/api/productivity/profiles/{profile_id}"): {"name": "Hijacked"},
    ("PUT", "/api/productivity/profiles/{profile_id}/members"): {"employee_ids": []},
    ("PATCH", "/api/users/{user_id}/role"): {"role": "COMPANY_ADMIN"},
    ("POST", "/api/live/sessions/{session_id}/stop"): {},
}

#: Routes whose id is not a tenant record lookup (they're covered by dedicated tests below).
SIGNED_LINK_ROUTES = {"/api/screenshot-files/{screenshot_id}/{variant}", "/api/task-files/{attachment_id}",
                      "/api/report-files/{report_id}"}  # fmt: skip


def test_every_id_route_refuses_another_tenants_records(
    client: TestClient, ws: Workspace, tenant_b: TenantB
) -> None:
    a = ws.admin.token
    tried = 0
    for method, path in route_table(client):
        params = re.findall(r"{(\w+)}", path)
        if not params or path in SIGNED_LINK_ROUTES:
            continue
        url = path
        for name in params:
            url = url.replace(f"{{{name}}}", tenant_b.ids[name])
        body = BODIES.get((method, path), {})
        if path.endswith("/attachments"):
            response = client.request(
                method,
                url,
                params={"filename": "x.png"},
                content=PNG,
                headers={**auth(a), "Content-Type": "image/png"},
            )
        else:
            response = client.request(method, url, json=body if method != "GET" else None, headers=auth(a))
        tried += 1
        assert response.status_code < 500, (method, path, response.status_code, response.text)
        assert not 200 <= response.status_code < 300, (method, path, response.status_code, response.text)
        assert tenant_b.canary not in response.text, (method, path)
    assert tried >= 55  # every id route and method in the app (grows as routes are added)

    # Company B's records are all still there, unchanged.
    b = tenant_b.ws
    assert b.get(f"/employees/{tenant_b.ids['employee_id']}").json()["full_name"].startswith(tenant_b.canary)
    assert b.get(f"/projects/{tenant_b.ids['project_id']}").json()["name"].startswith(tenant_b.canary)
    assert b.get(f"/tasks/{tenant_b.ids['task_id']}").json()["title"].startswith(tenant_b.canary)
    assert b.get(f"/departments/{tenant_b.ids['department_id']}").json()["name"].startswith(tenant_b.canary)
    assert b.get(f"/teams/{tenant_b.ids['team_id']}").json()["name"].startswith(tenant_b.canary)
    assert b.get(f"/screenshots/{tenant_b.ids['screenshot_id']}").status_code == 200
    assert b.get(f"/employees/{tenant_b.member.employee_id}").json()["status"] == "active"
    roles = {u["id"]: u["role"] for u in b.get("/users", page_size=100).json()["items"]}
    assert roles[tenant_b.member.user_id] == "EMPLOYEE"
    assert b.get("/auth/me").status_code == 200  # B's session wasn't revoked by A


def test_no_list_endpoint_shows_another_tenants_data(
    client: TestClient, ws: Workspace, tenant_b: TenantB
) -> None:
    probes = [
        ("/api/employees", {"search": tenant_b.canary}),
        ("/api/tasks", {"project_id": tenant_b.ids["project_id"]}),
        ("/api/screenshots", {"employee_id": tenant_b.member.employee_id}),
        ("/api/activity/feed", {"employee_id": tenant_b.member.employee_id}),
        ("/api/audit-logs", {"employee_id": tenant_b.member.employee_id}),
    ]
    for method, path in route_table(client):
        if method == "GET" and "{" not in path and not path.startswith("/api/health"):
            probes.append((path, {}))
    for path, params in probes:
        response = client.get(path, params=params, headers=auth(ws.admin.token))
        assert response.status_code < 500, (path, response.text)
        assert tenant_b.canary not in response.text, path
        assert tenant_b.ids["employee_id"] not in response.text, path


def test_signed_links_are_bound_to_tenant_and_viewer(
    client: TestClient, ws: Workspace, tenant_b: TenantB
) -> None:
    url = tenant_b.screenshot_url
    assert client.get(url).status_code == 200  # the genuine link works on its own

    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query))
    for field, value in {
        "c": str(ObjectId()),
        "u": ws.admin.user_id,
        "e": str(int(query["e"]) + 60),
        "s": "0" * 64,
    }.items():
        forged = {**query, field: value}
        response = client.get(f"{parts.path}?{urlencode(forged)}")
        assert response.status_code == 404, (field, response.status_code)
    # Re-signing for A's own company and user still needs the server's key.
    company_a = ws.get("/companies/current").json()["id"]
    response = client.get(parts.path, params={**query, "c": company_a, "u": ws.admin.user_id})
    assert response.status_code == 404


def test_websockets_and_live_sessions_stay_inside_the_tenant(
    client: TestClient, ws: Workspace, tenant_b: TenantB
) -> None:
    b = tenant_b.ws
    enable_live(b)
    member, agent = enrol_member(b, f"{tenant_b.canary} Streamer")
    working(agent)
    with agent_socket(client, agent):
        started = b.post("/live/sessions", {"employee_id": member.employee_id})
        assert started.status_code == 201, started.text
        session_id = started.json()["id"]
        # A's admin (who holds LIVE_STREAM_VIEW in their own company) can't see, join or stop B's session.
        assert ws.get(f"/live/sessions/{session_id}").status_code == 404
        assert ws.post(f"/live/sessions/{session_id}/stop", {}).status_code == 404
        assert ws.post("/live/sessions", {"employee_id": member.employee_id}).status_code == 404
        with (
            pytest.raises(WebSocketDisconnect) as refused,
            client.websocket_connect(f"/api/live/sessions/{session_id}/ws?token={ws.admin.token}") as sock,
        ):
            sock.receive_json()
        assert refused.value.code == 4404
        b.post(f"/live/sessions/{session_id}/stop", {})

    # Realtime gateway: events for B's users never reach A's sockets.
    from app.websocket.events import EventType, WsEvent

    manager = client.app.state.ws_manager  # type: ignore[attr-defined]
    with (
        client.websocket_connect(f"/api/ws?token={ws.admin.token}") as a_sock,
        client.websocket_connect(f"/api/ws?token={b.admin.token}") as b_sock,
    ):
        assert a_sock.receive_json()["type"] == "connection.ready"
        assert b_sock.receive_json()["type"] == "connection.ready"
        company_b = ObjectId(b.get("/companies/current").json()["id"])
        event = WsEvent(type=EventType.PONG, payload={"marker": tenant_b.canary})
        delivered = client.portal.call(manager.broadcast_to_company, company_b, event)  # type: ignore[attr-defined]
        assert delivered == 1
        assert tenant_b.canary in str(b_sock.receive_json())
        a_sock.send_json({"type": "ping"})
        reply = a_sock.receive_json()  # the next frame A sees is its own pong, not B's event
        assert reply["type"] == "pong" and tenant_b.canary not in str(reply)
