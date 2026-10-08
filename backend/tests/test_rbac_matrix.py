"""Phase 16: role-based access control, checked role by role for every protected area.

Expectations are derived from the permission catalogue (`ROLE_CATALOG`), so this matrix can't drift from the policy:
a role without the permission gets 403; a role with it gets through authorisation (any non-403, non-5xx answer).
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.auth.permissions import Permission, Role, permissions_for_role
from tests.conftest import unique_email
from tests.org_helpers import Actor, Workspace, auth
from tests.test_agent_api import enrol_member
from tests.test_live import agent_socket, working
from tests.test_live import enable as enable_live

D = "2026-01-05"


def matrix(target: Actor) -> list[tuple[str, str, Any, Permission]]:
    """(method, path, body, permission) for each protected area named in the security requirements."""
    return [
        # Employees
        ("GET", "/api/employees", None, Permission.EMPLOYEE_VIEW),
        ("POST", "/api/employees", {"full_name": "New Person", "email": unique_email("rbac")}, Permission.EMPLOYEE_MANAGE),
        ("POST", "/api/departments", {"name": f"Dept {unique_email('d')[:8]}"}, Permission.EMPLOYEE_MANAGE),
        # Screenshots
        ("GET", "/api/screenshots", None, Permission.SCREENSHOT_VIEW),
        ("PATCH", "/api/companies/current/screenshot-policy", {"interval_minutes": 15}, Permission.POLICY_MANAGE),
        # Live streaming (WebRTC sessions are created here; signalling is checked separately below)
        ("GET", "/api/live/employees", None, Permission.LIVE_STREAM_VIEW),
        ("POST", "/api/live/sessions", {"employee_id": target.employee_id}, Permission.LIVE_STREAM_VIEW),
        ("PATCH", "/api/companies/current/live-policy", {"max_session_minutes": 20}, Permission.POLICY_MANAGE),
        # Activity
        ("GET", "/api/presence", None, Permission.ACTIVITY_VIEW),
        ("GET", "/api/activity/applications", {"start": D, "end": D}, Permission.ACTIVITY_VIEW),
        ("PATCH", "/api/companies/current/activity-policy", {"track_applications": True}, Permission.POLICY_MANAGE),
        ("POST", "/api/productivity/rules", {"kind": "app", "pattern": "rbac.exe", "category": "neutral"}, Permission.POLICY_MANAGE),
        # Reports
        ("GET", "/api/reports", None, Permission.REPORT_VIEW),
        (
            "POST",
            "/api/reports",
            {"report_type": "work_hours", "format": "csv", "period": "daily", "start": D, "end": D},
            Permission.REPORT_EXPORT,
        ),
        ("GET", "/api/assistant/status", None, Permission.REPORT_VIEW),
        # Projects
        ("POST", "/api/projects", {"name": "RBAC project", "member_ids": []}, Permission.PROJECT_MANAGE),
        # Users, roles and the audit trail
        ("GET", "/api/users", None, Permission.USER_MANAGE),
        ("GET", "/api/roles", None, Permission.USER_MANAGE),
        ("PATCH", f"/api/users/{target.user_id}/role", {"role": "EMPLOYEE"}, Permission.USER_MANAGE),
        ("POST", f"/api/users/{target.user_id}/sessions/revoke", {}, Permission.USER_MANAGE),
        ("GET", "/api/audit-logs", None, Permission.AUDIT_LOG_VIEW),
    ]  # fmt: skip


@pytest.mark.parametrize("role", [Role.EMPLOYEE, Role.TEAM_LEAD, Role.MANAGER, Role.COMPANY_ADMIN])
def test_permission_matrix(ws: Workspace, client: TestClient, role: Role) -> None:
    actor = (
        ws.admin if role == Role.COMPANY_ADMIN else ws.member(f"Rita {role.value.title()}", role=role.value)
    )
    target = ws.member("Tom Target")
    enable_live(ws)  # so a refusal can only come from the role, not from the workspace policy
    granted = permissions_for_role(role)
    for method, path, body, permission in matrix(target):
        if method == "GET":
            response = client.get(path, params=body, headers=auth(actor.token))
        else:
            response = client.request(method, path, json=body, headers=auth(actor.token))
        assert response.status_code < 500, (role, method, path, response.text)
        if permission in granted:
            assert response.status_code != 403, (role, method, path, response.text)
        else:
            assert response.status_code == 403, (role, method, path, response.status_code)
            assert response.json()["error"]["code"] in ("insufficient_permissions", "forbidden")


def test_employees_only_see_themselves(ws: Workspace, client: TestClient) -> None:
    employee = ws.member("Erin Employee")
    colleague = ws.member("Cal Colleague")
    # Their own records work; anyone else's are "not found" (existence isn't disclosed).
    assert client.get("/api/me/monitoring", headers=auth(employee.token)).status_code == 200
    assert client.get(
        f"/api/employees/{colleague.employee_id}", headers=auth(employee.token)
    ).status_code in (403, 404)
    assert client.get(f"/api/productivity/employees/{colleague.employee_id}", params={"start": D, "end": D}, headers=auth(employee.token)).status_code in (403, 404)  # fmt: skip
    assert client.get("/api/privacy/monitoring-policy", headers=auth(employee.token)).status_code == 200


def test_live_signalling_requires_the_permission_and_the_requesting_viewer(
    ws: Workspace, client: TestClient
) -> None:
    enable_live(ws)
    member, agent = enrol_member(ws, "Sid Streamer")
    lead = ws.member("Liv Lead", role="TEAM_LEAD")
    other_manager = ws.member("Mo Manager", role="MANAGER")
    working(agent)
    with agent_socket(client, agent):
        started = ws.post("/live/sessions", {"employee_id": member.employee_id})
        assert started.status_code == 201, started.text
        session_id = started.json()["id"]
        # No LIVE_STREAM_VIEW: refused at the handshake.
        with (
            pytest.raises(WebSocketDisconnect) as no_permission,
            client.websocket_connect(f"/api/live/sessions/{session_id}/ws?token={lead.token}") as sock,
        ):
            sock.receive_json()
        assert no_permission.value.code == 4403
        # Has the permission, but isn't the viewer who requested this session.
        with (
            pytest.raises(WebSocketDisconnect) as not_theirs,
            client.websocket_connect(
                f"/api/live/sessions/{session_id}/ws?token={other_manager.token}"
            ) as sock,
        ):
            sock.receive_json()
        assert not_theirs.value.code == 4404
        # No token at all.
        with (
            pytest.raises(WebSocketDisconnect) as anonymous,
            client.websocket_connect(f"/api/live/sessions/{session_id}/ws") as sock,
        ):
            sock.receive_json()
        assert anonymous.value.code == 4401
        ws.post(f"/live/sessions/{session_id}/stop", {})
