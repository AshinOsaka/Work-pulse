"""Phase 2: organisation management — employees, structure, scope, tenancy, roles."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import register, unique_email
from tests.org_helpers import Workspace, auth

# --------------------------------------------------------------------------- creation


def test_registration_creates_admin_employee(ws: Workspace) -> None:
    detail = ws.get(f"/employees/{ws.admin.employee_id}").json()
    assert detail["access"] == "active"
    assert detail["account"]["role"] == "COMPANY_ADMIN"
    assert "USER_MANAGE" in detail["permissions"]


def test_create_employee_with_relations(ws: Workspace) -> None:
    engineering = ws.department("Engineering")
    platform = ws.team("Platform", department_id=engineering["id"])
    created = ws.employee(
        "Grace Hopper",
        job_title="Staff Engineer",
        employee_code="EMP-001",
        team_id=platform["id"],
        manager_employee_id=ws.admin.employee_id,
        hired_on="2024-03-01",
        timezone="Europe/London",
    )
    assert created["team"]["name"] == "Platform"
    # The department is inferred from the team.
    assert created["department"]["name"] == "Engineering"
    assert created["manager"]["id"] == ws.admin.employee_id
    assert created["hired_on"] == "2024-03-01"
    assert created["access"] == "none"
    manager = ws.get(f"/employees/{ws.admin.employee_id}").json()
    assert created["id"] in [r["id"] for r in manager["direct_reports"]]


def test_create_employee_validation(ws: Workspace) -> None:
    sales = ws.department("Sales")
    support = ws.department("Support")
    team = ws.team("Inbound", department_id=sales["id"])

    invalid = ws.post("/employees", {"full_name": "X", "email": "nope"})
    assert invalid.status_code == 422
    messages = {d["field"]: d["message"] for d in invalid.json()["error"]["details"]}
    # Messages are written for end users, not developers.
    assert messages["full_name"] == "Must be at least 2 characters."
    assert messages["email"] == "Enter a valid email address."

    mismatch = ws.post(
        "/employees",
        {
            "full_name": "Ann Lee",
            "email": unique_email(),
            "department_id": support["id"],
            "team_id": team["id"],
        },
    )
    assert mismatch.status_code == 400
    assert mismatch.json()["error"]["code"] == "team_department_mismatch"

    missing = ws.post(
        "/employees", {"full_name": "Ann Lee", "email": unique_email(), "department_id": "0" * 24}
    )
    assert missing.json()["error"]["code"] == "invalid_department"

    first = ws.employee("Dup Person", employee_code="E-42")
    dup_email = ws.post("/employees", {"full_name": "Other", "email": first["email"].upper()})
    assert dup_email.status_code == 409
    assert dup_email.json()["error"]["code"] == "employee_email_taken"
    dup_code = ws.post("/employees", {"full_name": "Other", "email": unique_email(), "employee_code": "E-42"})
    assert dup_code.json()["error"]["code"] == "employee_code_taken"


def test_employee_timezone_defaults_to_workspace(ws: Workspace) -> None:
    ws.patch("/companies/current", {"timezone": "Asia/Tokyo"})
    assert ws.employee("Tz Default")["timezone"] == "Asia/Tokyo"
    assert ws.employee("Tz Explicit", timezone="Europe/Paris")["timezone"] == "Europe/Paris"


def test_manager_cycles_are_rejected(ws: Workspace) -> None:
    a = ws.employee("Alpha Lead")
    b = ws.employee("Beta Report", manager_employee_id=a["id"])
    c = ws.employee("Gamma Report", manager_employee_id=b["id"])
    cycle = ws.patch(f"/employees/{a['id']}", {"manager_employee_id": c["id"]})
    assert cycle.status_code == 400
    assert cycle.json()["error"]["code"] == "manager_cycle"
    self_managed = ws.patch(f"/employees/{a['id']}", {"manager_employee_id": a["id"]})
    assert self_managed.json()["error"]["code"] == "invalid_manager"


# --------------------------------------------------------------------------- listing


def test_listing_search_filter_sort_paginate(ws: Workspace) -> None:
    ops = ws.department("Operations")
    lead = ws.employee("Zed Manager", department_id=ops["id"])
    names = ["Amy Adams", "Bob Brown", "Cara Cole", "Dan Dorsey", "Eve Evans"]
    for name in names:
        ws.employee(name, department_id=ops["id"], manager_employee_id=lead["id"], job_title="Analyst")
    on_leave = ws.employee("Fay Field", job_title="Analyst")
    ws.post(f"/employees/{on_leave['id']}/status", {"status": "on_leave"})

    page1 = ws.get("/employees", department_id=ops["id"], page_size=4).json()
    assert page1["total"] == 6 and page1["pages"] == 2 and len(page1["items"]) == 4
    assert [e["full_name"] for e in page1["items"]] == ["Amy Adams", "Bob Brown", "Cara Cole", "Dan Dorsey"]
    page2 = ws.get("/employees", department_id=ops["id"], page_size=4, page=2).json()
    assert [e["full_name"] for e in page2["items"]] == ["Eve Evans", "Zed Manager"]

    desc = ws.get("/employees", department_id=ops["id"], sort="full_name", order="desc", page_size=1).json()
    assert desc["items"][0]["full_name"] == "Zed Manager"

    assert ws.get("/employees", search="cara").json()["total"] == 1
    assert ws.get("/employees", manager_id=lead["id"]).json()["total"] == 5
    analysts = ws.get("/employees", search="analyst", status=["on_leave"]).json()
    assert [e["full_name"] for e in analysts["items"]] == ["Fay Field"]
    both = ws.client.get(
        "/api/employees?status=active&status=on_leave&search=analyst", headers=auth(ws.admin.token)
    ).json()
    assert both["total"] == 6

    managers = ws.get("/employees/managers").json()
    assert lead["id"] in [m["id"] for m in managers]
    assert ws.get("/employees", sort="bogus").status_code == 422
    assert ws.get("/employees", page_size=1000).status_code == 422


# --------------------------------------------------------------------------- invitations & status


def test_invitation_flow(ws: Workspace) -> None:
    employee = ws.employee("Ivy Invite", invite=True, role="TEAM_LEAD")
    assert employee["access"] == "invited"
    token = ws.mail.last_token()

    login = ws.client.post("/api/auth/login", json={"email": employee["email"], "password": "anything-1234"})
    assert login.status_code == 401  # no password yet: indistinguishable from bad credentials

    preview = ws.client.get(f"/api/auth/invitations/{token}").json()
    assert preview["email"] == employee["email"] and preview["company_name"] == "Org Test Co"

    accepted = ws.client.post(
        "/api/auth/invitations/accept", json={"token": token, "password": "Accepted1Pass"}
    )
    assert accepted.status_code == 200
    assert accepted.json()["user"]["role"] == "TEAM_LEAD"
    assert accepted.json()["user"]["email_verified"] is True
    again = ws.client.post("/api/auth/invitations/accept", json={"token": token, "password": "Accepted1Pass"})
    assert again.status_code == 400

    detail = ws.get(f"/employees/{employee['id']}").json()
    assert detail["access"] == "active"
    resend = ws.post(f"/employees/{employee['id']}/invite", {"role": "EMPLOYEE"})
    assert resend.json()["error"]["code"] == "account_exists"


def test_resend_invitation_invalidates_previous_link(ws: Workspace) -> None:
    employee = ws.employee("Rex Resend")
    assert ws.post(f"/employees/{employee['id']}/invite", {"role": "EMPLOYEE"}).status_code == 200
    first = ws.mail.last_token()
    assert ws.post(f"/employees/{employee['id']}/invite", {"role": "EMPLOYEE"}).status_code == 200
    second = ws.mail.last_token()
    assert ws.client.get(f"/api/auth/invitations/{first}").status_code == 400
    assert ws.client.get(f"/api/auth/invitations/{second}").status_code == 200


def test_termination_revokes_access_and_reactivation_restores_it(ws: Workspace) -> None:
    member = ws.member("Tom Term")
    assert ws.get("/auth/me", token=member.token).status_code == 200

    terminated = ws.post(f"/employees/{member.employee_id}/status", {"status": "terminated"})
    assert terminated.status_code == 200
    assert terminated.json()["access"] == "deactivated"
    assert ws.get("/auth/me", token=member.token).status_code == 401
    relogin = ws.client.post("/api/auth/login", json={"email": member.email, "password": "Member1Password"})
    assert relogin.status_code == 403

    restored = ws.post(f"/employees/{member.employee_id}/status", {"status": "active"})
    assert restored.json()["access"] == "active"
    relogin = ws.client.post("/api/auth/login", json={"email": member.email, "password": "Member1Password"})
    assert relogin.status_code == 200

    own = ws.post(f"/employees/{ws.admin.employee_id}/status", {"status": "terminated"})
    assert own.json()["error"]["code"] == "cannot_change_own_status"


# --------------------------------------------------------------------------- authorization & scope


def test_employee_role_permissions(ws: Workspace) -> None:
    member = ws.member("Emma Employee")
    other = ws.employee("Other Person")

    assert ws.get("/employees", token=member.token).status_code == 403
    assert ws.get("/departments", token=member.token).status_code == 403
    assert ws.get("/people/summary", token=member.token).status_code == 403
    assert ws.get(f"/employees/{member.employee_id}", token=member.token).status_code == 200
    # Out-of-scope records are reported as not found (no existence disclosure).
    assert ws.get(f"/employees/{other['id']}", token=member.token).status_code == 404
    assert (
        ws.post(
            "/employees", {"full_name": "New Hire", "email": unique_email()}, token=member.token
        ).status_code
        == 403
    )
    assert (
        ws.patch(f"/employees/{member.employee_id}", {"job_title": "CEO"}, token=member.token).status_code
        == 403
    )
    assert ws.get("/users", token=member.token).status_code == 403


def test_manager_sees_only_reporting_tree_and_headed_department(ws: Workspace) -> None:
    manager = ws.member("Mia Manager", role="MANAGER")
    direct = ws.employee("Dee Direct", manager_employee_id=manager.employee_id)
    indirect = ws.employee("Ian Indirect", manager_employee_id=direct["id"])
    outsider = ws.employee("Oscar Outsider")

    listing = ws.get("/employees", token=manager.token, page_size=100).json()
    visible = {e["id"] for e in listing["items"]}
    assert visible == {manager.employee_id, direct["id"], indirect["id"]}
    assert ws.get(f"/employees/{indirect['id']}", token=manager.token).status_code == 200
    assert ws.get(f"/employees/{outsider['id']}", token=manager.token).status_code == 404
    assert ws.get(f"/employees/{outsider['id']}/devices", token=manager.token).status_code == 404

    # Managers can view but not manage employees.
    assert (
        ws.post("/employees", {"full_name": "Nope", "email": unique_email()}, token=manager.token).status_code
        == 403
    )
    assert (
        ws.post(
            f"/employees/{direct['id']}/status", {"status": "terminated"}, token=manager.token
        ).status_code
        == 403
    )

    # Heading a department brings its members into scope.
    finance = ws.department("Finance", head_employee_id=manager.employee_id)
    ws.patch(f"/employees/{outsider['id']}", {"department_id": finance["id"]})
    assert ws.get(f"/employees/{outsider['id']}", token=manager.token).status_code == 200
    summary = ws.get("/people/summary", token=manager.token).json()
    assert summary["total"] == 4


def test_team_lead_scope(ws: Workspace) -> None:
    lead = ws.member("Liam Lead", role="TEAM_LEAD")
    squad = ws.team("Squad", lead_employee_id=lead.employee_id)
    member = ws.employee("Sam Squad", team_id=squad["id"])
    stranger = ws.employee("Stan Stranger")

    visible = {e["id"] for e in ws.get("/employees", token=lead.token).json()["items"]}
    assert visible == {lead.employee_id, member["id"]}
    assert ws.get(f"/employees/{stranger['id']}", token=lead.token).status_code == 404


# --------------------------------------------------------------------------- tenant isolation


def test_tenant_isolation(ws: Workspace, client: TestClient) -> None:
    dept = ws.department("Secret Dept")
    team = ws.team("Secret Team", department_id=dept["id"])
    target = ws.member("Tara Target", team_id=team["id"])
    device = ws.post(f"/employees/{target.employee_id}/devices", {"name": "Tara laptop"}).json()

    other = register(client, company_name="Rival Corp")
    rival = str(other["access_token"])

    assert ws.get(f"/employees/{target.employee_id}", token=rival).status_code == 404
    assert ws.patch(f"/employees/{target.employee_id}", {"job_title": "Spy"}, token=rival).status_code == 404
    assert (
        ws.post(f"/employees/{target.employee_id}/status", {"status": "terminated"}, token=rival).status_code
        == 404
    )
    assert ws.get(f"/employees/{target.employee_id}/devices", token=rival).status_code == 404
    assert ws.post(f"/devices/{device['id']}/revoke", {}, token=rival).status_code == 404
    assert ws.get(f"/departments/{dept['id']}", token=rival).status_code == 404
    assert ws.client.delete(f"/api/teams/{team['id']}", headers=auth(rival)).status_code == 404
    assert ws.patch(f"/users/{target.user_id}/role", {"role": "MANAGER"}, token=rival).status_code == 404

    listing = ws.get("/employees", token=rival, page_size=100).json()
    assert target.employee_id not in {e["id"] for e in listing["items"]}
    assert listing["total"] == 1  # only the rival's own admin
    assert ws.get("/departments", token=rival).json() == []

    # Foreign references cannot be attached to the rival's records either.
    foreign_ref = ws.post(
        "/employees",
        {"full_name": "Cross Ref", "email": unique_email(), "department_id": dept["id"]},
        token=rival,
    )
    assert foreign_ref.json()["error"]["code"] == "invalid_department"
    foreign_manager = ws.post(
        "/employees",
        {"full_name": "Cross Ref", "email": unique_email(), "manager_employee_id": target.employee_id},
        token=rival,
    )
    assert foreign_manager.json()["error"]["code"] == "invalid_manager"


# --------------------------------------------------------------------------- roles


def test_role_management(ws: Workspace) -> None:
    member = ws.member("Rita Role")
    assert ws.get("/auth/me", token=member.token).json()["permissions"] == []

    promoted = ws.patch(f"/users/{member.user_id}/role", {"role": "MANAGER"})
    assert promoted.status_code == 200 and promoted.json()["role"] == "MANAGER"
    # Role changes apply on the very next request.
    assert "EMPLOYEE_VIEW" in ws.get("/auth/me", token=member.token).json()["permissions"]
    assert (
        ws.patch(f"/users/{ws.admin.user_id}/role", {"role": "EMPLOYEE"}, token=member.token).status_code
        == 403
    )

    own = ws.patch(f"/users/{ws.admin.user_id}/role", {"role": "MANAGER"})
    assert own.json()["error"]["code"] == "cannot_change_own_role"
    platform = ws.patch(f"/users/{member.user_id}/role", {"role": "SUPER_ADMIN"})
    assert platform.status_code == 403 and platform.json()["error"]["code"] == "role_not_assignable"

    # A second admin can be appointed and can then manage the first.
    second_admin = ws.member("Adam Admin", role="COMPANY_ADMIN")
    demote = ws.patch(f"/users/{ws.admin.user_id}/role", {"role": "MANAGER"}, token=second_admin.token)
    assert demote.status_code == 200

    users = ws.get("/users", token=second_admin.token, role="MANAGER").json()
    assert {u["email"] for u in users["items"]} == {member.email, ws.admin.email}


def test_invite_requires_user_manage_and_assignable_role(ws: Workspace) -> None:
    manager = ws.member("Max Manager", role="MANAGER")
    employee = ws.employee("Ned New")
    forbidden = ws.post(f"/employees/{employee['id']}/invite", {"role": "EMPLOYEE"}, token=manager.token)
    assert forbidden.status_code == 403
    too_high = ws.post(
        "/employees",
        {"full_name": "Sue Super", "email": unique_email(), "invite": True, "role": "SUPER_ADMIN"},
    )
    assert too_high.json()["error"]["code"] == "role_not_assignable"


# --------------------------------------------------------------------------- structure, devices, company


def test_departments_and_teams(ws: Workspace) -> None:
    eng = ws.department("Engineering Core", description="Builds things")
    dup = ws.post("/departments", {"name": "engineering core"})
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "department_name_taken"

    research = ws.department("Research")
    team = ws.team("Compilers", department_id=eng["id"])
    member = ws.employee("Ken Compiler", team_id=team["id"])
    assert member["department"]["id"] == eng["id"]

    departments = {d["name"]: d for d in ws.get("/departments").json()}
    assert departments["Engineering Core"]["employee_count"] == 1
    assert departments["Engineering Core"]["team_count"] == 1

    assert (
        ws.client.delete(f"/api/departments/{eng['id']}", headers=auth(ws.admin.token)).json()["error"][
            "code"
        ]
        == "department_in_use"
    )
    assert (
        ws.client.delete(f"/api/teams/{team['id']}", headers=auth(ws.admin.token)).json()["error"]["code"]
        == "team_in_use"
    )

    moved = ws.patch(f"/teams/{team['id']}", {"department_id": research["id"]})
    assert moved.json()["department"]["id"] == research["id"]
    assert ws.get(f"/employees/{member['id']}").json()["department"]["id"] == research["id"]

    ws.patch(f"/employees/{member['id']}", {"team_id": None, "department_id": None})
    assert ws.client.delete(f"/api/teams/{team['id']}", headers=auth(ws.admin.token)).status_code == 204
    assert ws.client.delete(f"/api/departments/{eng['id']}", headers=auth(ws.admin.token)).status_code == 204
    assert ws.get(f"/departments/{eng['id']}").status_code == 404


def test_device_registration_foundation(ws: Workspace) -> None:
    member = ws.member("Dora Device")
    registered = ws.post(
        f"/employees/{member.employee_id}/devices",
        {"name": "Dora's laptop", "hostname": "DORA-PC", "os": "windows"},
    )
    assert registered.status_code == 201
    body = registered.json()
    assert body["status"] == "pending"
    assert body["enrollment_code"].startswith("WP-") and len(body["enrollment_code"]) == 17

    own = ws.get(f"/employees/{member.employee_id}/devices", token=member.token).json()
    assert [d["id"] for d in own] == [body["id"]]
    assert "enrollment_code" not in own[0]
    assert (
        ws.post(f"/employees/{member.employee_id}/devices", {"name": "Mine"}, token=member.token).status_code
        == 403
    )

    revoked = ws.post(f"/devices/{body['id']}/revoke", {})
    assert revoked.json()["status"] == "revoked"
    assert ws.get(f"/employees/{member.employee_id}").json()["device_count"] == 0


def test_company_profile_update(ws: Workspace) -> None:
    updated = ws.patch(
        "/companies/current", {"name": "Org Test Renamed", "timezone": "America/New_York", "size": "51-200"}
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Org Test Renamed" and updated.json()["timezone"] == "America/New_York"
    assert ws.patch("/companies/current", {"timezone": "Mars/Base"}).status_code == 422
    member = ws.member("Paul Policy")
    assert ws.patch("/companies/current", {"name": "Hijack"}, token=member.token).status_code == 403


def test_people_summary(ws: Workspace) -> None:
    hr = ws.department("People Ops")
    ws.employee("Hana Hr", department_id=hr["id"])
    ws.employee("Pending Pete", invite=True)
    summary = ws.get("/people/summary").json()
    assert summary["total"] == 3
    assert summary["pending_invitations"] == 1
    assert {"name": "People Ops", "count": 1, "id": hr["id"]} in summary["departments"]
    assert summary["by_status"]["active"] == 3
