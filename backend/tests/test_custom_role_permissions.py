"""Custom roles with chosen permissions: e.g. an HR Manager who manages employees but sees no screenshots."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.org_helpers import Workspace

HR = ["EMPLOYEE_VIEW", "EMPLOYEE_MANAGE", "REPORT_VIEW", "REPORT_EXPORT"]


def test_a_custom_role_grants_exactly_the_chosen_permissions(ws: Workspace, client: TestClient) -> None:
    created = ws.post("/roles", {"name": "HR Manager", "base_level": "MANAGER", "permissions": HR})
    assert created.status_code == 201, created.text
    role = created.json()
    assert role["key"] == "HR_MANAGER" and sorted(role["permissions"]) == sorted(HR)

    hr = ws.member("Hana HR")
    assert ws.patch(f"/users/{hr.user_id}/role", {"role": "HR_MANAGER"}).status_code == 200

    me = ws.get("/auth/me", token=hr.token).json()
    assert sorted(me["permissions"]) == sorted(HR)
    # Can do what was ticked: add an employee (Manage employees)...
    added = ws.post("/employees", {"full_name": "New Starter", "email": "new.starter@example.com"}, token=hr.token)
    assert added.status_code == 201, added.text
    # ...and nothing that wasn't, even though a Manager could: screenshots, live view.
    assert ws.get("/screenshots", token=hr.token).status_code == 403
    assert ws.get("/live/sessions", token=hr.token).status_code in (403, 404)

    # Changing the role's permissions applies on the next request.
    changed = ws.patch("/roles/HR_MANAGER", {"permissions": ["EMPLOYEE_VIEW"]})
    assert changed.status_code == 200 and changed.json()["permissions"] == ["EMPLOYEE_VIEW"]
    assert ws.get("/auth/me", token=hr.token).json()["permissions"] == ["EMPLOYEE_VIEW"]
    again = ws.post("/employees", {"full_name": "Second", "email": "second.starter@example.com"}, token=hr.token)
    assert again.status_code == 403


def test_without_a_choice_a_custom_role_gets_its_base_level_permissions(ws: Workspace) -> None:
    role = ws.post("/roles", {"name": "Supervisor", "base_level": "TEAM_LEAD"}).json()
    lead = next(r for r in ws.get("/roles").json()["roles"] if r["key"] == "TEAM_LEAD")
    assert sorted(role["permissions"]) == sorted(lead["permissions"])


def test_nobody_grants_a_permission_they_do_not_hold(ws: Workspace) -> None:
    # A role with Manage users but not Audit log: a member of it can't create a role that has Audit log.
    ws.post("/roles", {"name": "People Ops", "base_level": "MANAGER", "permissions": ["USER_MANAGE", "EMPLOYEE_VIEW"]})
    ops = ws.member("Omar Ops")
    ws.patch(f"/users/{ops.user_id}/role", {"role": "PEOPLE_OPS"})
    refused = ws.post("/roles", {"name": "Auditor", "base_level": "EMPLOYEE", "permissions": ["AUDIT_LOG_VIEW"]}, token=ops.token)
    assert refused.status_code == 403
    assert refused.json()["error"]["code"] == "permission_not_grantable"


def test_a_company_can_re_tick_built_in_roles_except_company_admin(ws: Workspace, client: TestClient) -> None:
    from tests.conftest import register

    lead = ws.member("Lena Lead", role="TEAM_LEAD")
    assert "SCREENSHOT_VIEW" in ws.get("/auth/me", token=lead.token).json()["permissions"]

    # Take screenshots away from every Team Lead in this workspace.
    standard = next(r for r in ws.get("/roles").json()["roles"] if r["key"] == "TEAM_LEAD")
    assert standard["editable"] is True and standard["customized"] is False
    fewer = [p for p in standard["permissions"] if p != "SCREENSHOT_VIEW"]
    changed = ws.patch("/roles/TEAM_LEAD", {"permissions": fewer})
    assert changed.status_code == 200, changed.text
    assert changed.json()["customized"] is True and "SCREENSHOT_VIEW" not in changed.json()["permissions"]
    assert "SCREENSHOT_VIEW" not in ws.get("/auth/me", token=lead.token).json()["permissions"]
    assert ws.get("/screenshots", token=lead.token).status_code == 403
    keys = [r["key"] for r in ws.get("/roles").json()["roles"]]
    assert keys.count("TEAM_LEAD") == 1  # the company's version replaces the standard one in the list

    # Another workspace's Team Leads are untouched.
    other = register(client, company_name="Other Lead Co")
    other_roles = client.get("/api/roles", headers={"Authorization": f"Bearer {other['access_token']}"}).json()
    assert "SCREENSHOT_VIEW" in next(r for r in other_roles["roles"] if r["key"] == "TEAM_LEAD")["permissions"]

    # Back to the standard permissions.
    reset = ws.patch("/roles/TEAM_LEAD", {"permissions": standard["default_permissions"]})
    assert reset.json()["customized"] is False
    assert "SCREENSHOT_VIEW" in ws.get("/auth/me", token=lead.token).json()["permissions"]

    # Company Admin always keeps everything; names and levels of built-ins don't change; they can't be deleted.
    assert ws.patch("/roles/COMPANY_ADMIN", {"permissions": ["EMPLOYEE_VIEW"]}).status_code == 409
    assert ws.patch("/roles/MANAGER", {"name": "Boss"}).status_code == 400
    assert ws.delete("/roles/MANAGER").status_code == 409
