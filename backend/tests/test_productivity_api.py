"""Phase 8: productivity API — rules (company/department/team/role), reports from real agent data, access."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from bson import ObjectId
from fastapi.testclient import TestClient

from tests.conftest import register
from tests.org_helpers import Workspace, auth
from tests.test_agent_api import AgentClient, enrol_member, event, iso

DAY = (datetime.now(UTC) - timedelta(days=1)).replace(
    hour=0, minute=0, second=0, microsecond=0
)  # yesterday, UTC


def at(hour: float) -> datetime:
    return DAY + timedelta(hours=hour)


def segment(
    start: datetime, minutes: float, app: str, name: str, domain: str | None = None
) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "session_id": str(uuid.uuid4()),
        "app_id": app,
        "app_name": name,
        "started_at": iso(start),
        "ended_at": iso(start + timedelta(minutes=minutes)),
        "active_seconds": int(minutes * 60 * 0.8),
        "activity_level": 80,
    }
    if domain:
        fields["domain"] = domain
    return event("activity.segment", start + timedelta(minutes=minutes), **fields)


def workday(agent: AgentClient) -> None:
    """09:00-12:00 and 13:00-15:00 at work; idle 10:30-11:00; a mix of applications and websites."""
    s1, s2 = str(uuid.uuid4()), str(uuid.uuid4())
    events = [
        event("session.started", at(9), session_id=s1),
        event("presence.changed", at(10.5), session_id=s1, status="idle"),
        event("presence.changed", at(11), session_id=s1, status="active"),
        event(
            "session.stopped", at(12), session_id=s1, reason="user", active_seconds=9000, idle_seconds=1800
        ),
        event("session.started", at(13), session_id=s2),
        event("session.stopped", at(15), session_id=s2, reason="user", active_seconds=7200, idle_seconds=0),
        segment(at(9), 15, "code.exe", "Visual Studio Code"),
        segment(at(9.25), 15, "code.exe", "Visual Studio Code"),  # 30 minutes of focus
        segment(at(9.5), 20, "chrome.exe", "Google Chrome", "github.com"),
        segment(at(9 + 50 / 60), 10, "chrome.exe", "Google Chrome", "netflix.com"),
        segment(at(10), 20, "slack.exe", "Slack"),
        segment(at(13), 30, "notion.exe", "Notion"),  # unclassified
    ]
    response = agent.events(*events)
    assert response.status_code == 200 and response.json()["rejected"] == [], response.text


def report(ws: Workspace, employee_id: str, token: str | None = None) -> Any:
    day = DAY.date().isoformat()
    return ws.get(f"/productivity/employees/{employee_id}", token=token, start=day, end=day)


def add_rule(ws: Workspace, token: str | None = None, **body: Any) -> Any:
    return ws.post("/productivity/rules", body, token=token)


# --------------------------------------------------------------------------- rules


def test_rule_management_validation_permissions_and_audit(ws: Workspace, sync_db: Any) -> None:
    member = ws.member("Rita Rules")
    team = ws.team("Platform")
    dept = ws.department("Engineering")

    assert (
        add_rule(ws, token=member.token, kind="app", pattern="code.exe", category="productive").status_code
        == 403
    )
    assert ws.get("/productivity/rules", token=member.token).status_code == 403

    created = add_rule(
        ws, kind="website", pattern="https://www.GitHub.com/org/repo?q=1", category="productive"
    )
    assert created.status_code == 201 and created.json()["pattern"] == "github.com"
    assert add_rule(ws, kind="website", pattern="github.com", category="neutral").status_code == 409
    assert add_rule(ws, kind="website", pattern="localhost", category="neutral").status_code == 422
    assert add_rule(ws, kind="app", pattern="slack.exe", category="neutral", scope="team").status_code == 422
    assert (
        add_rule(
            ws, kind="app", pattern="slack.exe", category="neutral", scope="team", scope_id=str(ObjectId())
        ).status_code
        == 400
    )
    team_rule = add_rule(
        ws, kind="app", pattern="Slack.EXE", category="productive", scope="team", scope_id=team["id"]
    )
    assert team_rule.status_code == 201 and team_rule.json()["scope_ref"]["name"] == "Platform"
    role_rule = add_rule(
        ws, kind="app", pattern="slack.exe", category="unproductive", scope="role", role="EMPLOYEE"
    )
    dept_rule = add_rule(
        ws, kind="app", pattern="slack.exe", category="neutral", scope="department", scope_id=dept["id"]
    )
    assert role_rule.status_code == 201 and dept_rule.status_code == 201

    rid = created.json()["id"]
    updated = ws.patch(f"/productivity/rules/{rid}", {"category": "neutral", "note": "Mostly reading"})
    assert updated.json()["category"] == "neutral"
    assert ws.client.delete(f"/api/productivity/rules/{rid}", headers=auth(ws.admin.token)).status_code == 204
    assert len(ws.get("/productivity/rules").json()) == 3

    loaded = ws.post("/productivity/rules/recommended", {}).json()
    assert loaded["added"] > 10 and ws.post("/productivity/rules/recommended", {}).json()["added"] == 0
    actions = {a["action"] for a in sync_db["audit_logs"].find({"action": {"$regex": "^productivity\\."}})}
    assert {
        "productivity.rule_created",
        "productivity.rule_updated",
        "productivity.rule_deleted",
        "productivity.recommended_rules_loaded",
    } <= actions


# --------------------------------------------------------------------------- reports from real agent data


def test_employee_report_metrics_scores_focus_and_insights(ws: Workspace) -> None:
    ws.patch("/companies/current/activity-policy", {"track_websites": True})
    member, agent = enrol_member(ws, "Petra Product")
    for kind, pattern, category in [
        ("app", "code.exe", "productive"),
        ("app", "slack.exe", "neutral"),
        ("website", "github.com", "productive"),
        ("website", "netflix.com", "unproductive"),
    ]:
        assert add_rule(ws, kind=kind, pattern=pattern, category=category).status_code == 201
    workday(agent)

    body = report(ws, member.employee_id).json()
    t = body["totals"]
    assert t["work_seconds"] == 5 * 3600
    assert t["idle_seconds"] == 30 * 60 and t["active_seconds"] == 4.5 * 3600
    assert t["away_seconds"] == 3600  # the lunch break between sessions
    assert t["productive_seconds"] == (30 + 20) * 60  # code + github
    assert t["unproductive_seconds"] == 10 * 60 and t["neutral_seconds"] == 20 * 60
    assert t["unclassified_seconds"] == 30 * 60  # notion
    assert t["focus_sessions"] == 1 and t["focus_seconds"] >= 30 * 60

    activity, share = body["scores"]["activity_score"], body["scores"]["productive_share"]
    assert activity["value"] == 90 and activity["formula"].startswith("Active time")
    assert {c["key"]: c["seconds"] for c in activity["components"]} == {
        "active_seconds": 16200,
        "work_seconds": 18000,
    }
    assert share["value"] == round(100 * 50 / 80) and share["coverage"] == round(100 * 80 / 110)
    assert "not a performance rating" in share["interpretation"]
    assert (
        body["task_completion"]["available"] is True and body["task_completion"]["value"] is None
    )  # no tasks yet
    assert "not a measure of anyone's performance" in body["disclaimer"]

    usage = {u["key"]: u for u in body["usage"]}
    assert usage["github.com"]["category"] == "productive" and usage["github.com"]["kind"] == "website"
    assert usage["notion.exe"]["category"] == "unclassified" and usage["notion.exe"]["rule_scope"] is None
    assert "chrome.exe" not in usage  # all browser time was attributed to websites
    (focus,) = body["focus_sessions"]
    assert "Visual Studio Code" in focus["top_apps"]
    assert all(i["metrics"] for i in body["insights"])
    assert len(body["days"]) == 1 and body["days"][0]["activity_score"] == 90

    unclassified = ws.get(
        "/productivity/unclassified", start=DAY.date().isoformat(), end=DAY.date().isoformat()
    ).json()
    assert [u["key"] for u in unclassified] == ["notion.exe"]


def test_rules_resolve_per_employee_by_team_department_and_role(ws: Workspace) -> None:
    team = ws.team("Support")
    dept = ws.department("Sales")
    in_team, team_agent = enrol_member(ws, "Tia Team", team_id=team["id"])
    in_dept, dept_agent = enrol_member(ws, "Dan Dept", department_id=dept["id"])
    manager, manager_agent = enrol_member(ws, "Moe Manager", role="MANAGER")
    add_rule(ws, kind="app", pattern="slack.exe", category="neutral")
    add_rule(ws, kind="app", pattern="slack.exe", category="productive", scope="team", scope_id=team["id"])
    add_rule(
        ws, kind="app", pattern="slack.exe", category="unproductive", scope="department", scope_id=dept["id"]
    )
    add_rule(ws, kind="app", pattern="slack.exe", category="productive", scope="role", role="MANAGER")
    for agent in (team_agent, dept_agent, manager_agent):
        agent.events(segment(at(10), 30, "slack.exe", "Slack"))

    day = DAY.date().isoformat()
    rows = {
        r["employee"]["id"]: r["metrics"]
        for r in ws.get("/productivity/team", start=day, end=day).json()["rows"]
    }
    assert rows[in_team.employee_id]["productive_seconds"] == 1800
    assert rows[in_dept.employee_id]["unproductive_seconds"] == 1800
    assert rows[manager.employee_id]["productive_seconds"] == 1800
    team_only = ws.get("/productivity/team", start=day, end=day, team_id=team["id"]).json()
    assert [r["employee"]["id"] for r in team_only["rows"]] == [in_team.employee_id]


def test_websites_are_dropped_unless_the_policy_tracks_them(ws: Workspace, sync_db: Any) -> None:
    member, agent = enrol_member(ws, "Wes Web")
    agent.events(segment(at(9), 10, "msedge.exe", "Microsoft Edge", "example.com"))
    stored = sync_db["activity_segments"].find_one({"employee_id": ObjectId(member.employee_id)})
    assert (
        stored["domain"] is None
        and sync_db["website_daily"].count_documents({"employee_id": ObjectId(member.employee_id)}) == 0
    )

    ws.patch(
        "/companies/current/activity-policy", {"track_websites": True, "excluded_apps": ["bank.example"]}
    )
    agent.events(
        segment(at(10), 10, "msedge.exe", "Microsoft Edge", "WWW.Example.COM"),
        segment(at(11), 10, "msedge.exe", "Microsoft Edge", "online.bank.example"),
    )
    domains = sorted(
        d["domain"] or "-"
        for d in sync_db["activity_segments"].find({"employee_id": ObjectId(member.employee_id)})
    )
    assert domains == ["-", "-", "example.com"]  # normalised; excluded domain dropped
    bad = agent.events(segment(at(12), 5, "msedge.exe", "Microsoft Edge", "https://evil.com/path"))
    assert bad.status_code == 422  # only bare host names are accepted


def test_access_rules_for_reports(ws: Workspace, client: TestClient) -> None:
    manager = ws.member("Max Lead", role="MANAGER")
    report_member, _ = enrol_member(ws, "Rae Report", manager_employee_id=manager.employee_id)
    outsider, _ = enrol_member(ws, "Oli Out")
    day = DAY.date().isoformat()

    assert report(ws, report_member.employee_id, token=report_member.token).status_code == 200  # own figures
    assert report(ws, outsider.employee_id, token=report_member.token).status_code == 404
    assert ws.get("/productivity/team", token=report_member.token, start=day, end=day).status_code == 403
    assert report(ws, report_member.employee_id, token=manager.token).status_code == 200
    assert report(ws, outsider.employee_id, token=manager.token).status_code == 404
    rival = str(register(client, company_name="Rival Productivity")["access_token"])
    assert report(ws, report_member.employee_id, token=rival).status_code == 404
    too_long = ws.get("/productivity/team", start=(DAY - timedelta(days=40)).date().isoformat(), end=day)
    assert too_long.status_code == 400 and too_long.json()["error"]["code"] == "range_too_long"


def test_trend_buckets_for_the_dashboard(ws: Workspace) -> None:
    _, agent = enrol_member(ws, "Tre Trend")
    add_rule(ws, kind="app", pattern="code.exe", category="productive")
    add_rule(ws, kind="app", pattern="slack.exe", category="neutral")
    workday(agent)
    daily = ws.get("/productivity/trend", period="daily").json()
    assert len(daily["points"]) == 14
    yesterday = next(p for p in daily["points"] if p["start"] == DAY.date().isoformat())
    assert yesterday["work_seconds"] == 5 * 3600 and yesterday["productive_seconds"] == 30 * 60
    # Only 50 of 110 tracked minutes are covered by rules: the share is withheld rather than guessed.
    assert yesterday["productive_share"] is None and yesterday["activity_score"] == 90
    assert len(ws.get("/productivity/trend", period="weekly").json()["points"]) == 12
    monthly = ws.get("/productivity/trend", period="monthly").json()["points"]
    assert len(monthly) == 12 and monthly[-1]["start"].endswith("-01")


# --------------------------------------------------------------------------- Phase 12


def test_work_profiles_change_classification_for_their_members(ws: Workspace, sync_db: Any) -> None:
    supporter, agent = enrol_member(ws, "Sam Support")
    colleague, colleague_agent = enrol_member(ws, "Cleo Colleague")
    assert add_rule(ws, kind="app", pattern="slack.exe", category="neutral").status_code == 201
    workday(agent)
    workday(colleague_agent)

    templates = {t["key"]: t for t in ws.get("/productivity/profile-templates").json()}
    assert set(templates) == {"developer", "designer", "accountant", "sales", "support"}
    assert any(
        r["pattern"] == "linkedin.com" and r["category"] == "productive" for r in templates["sales"]["rules"]
    )

    assert ws.post("/productivity/profiles", {"name": "Nope"}, token=supporter.token).status_code == 403
    assert ws.post("/productivity/profiles", {"name": "X1", "template": "astronaut"}).status_code == 400
    created = ws.post("/productivity/profiles", {"name": "Support", "template": "support"})
    assert created.status_code == 201, created.text
    profile = created.json()
    assert profile["rule_count"] == len(templates["support"]["rules"]) and profile["members"] == []
    assert ws.post("/productivity/profiles", {"name": "support"}).status_code == 409  # names are unique

    before = report(ws, supporter.employee_id).json()["totals"]["productive_seconds"]
    put = ws.client.put(
        f"/api/productivity/profiles/{profile['id']}/members",
        json={"employee_ids": [supporter.employee_id]},
        headers=auth(ws.admin.token),
    )
    assert [m["id"] for m in put.json()["members"]] == [supporter.employee_id]

    mine = report(ws, supporter.employee_id).json()
    assert mine["work_profile"]["name"] == "Support"
    slack = next(u for u in mine["usage"] if u["key"] == "slack.exe")
    assert slack["category"] == "productive" and slack["rule_scope"] == "profile"
    assert mine["totals"]["productive_seconds"] == before + 20 * 60
    theirs = report(ws, colleague.employee_id).json()
    assert theirs["work_profile"] is None
    assert next(u for u in theirs["usage"] if u["key"] == "slack.exe")["category"] == "neutral"

    rules = ws.get("/productivity/rules").json()
    assert any(r["scope"] == "profile" and r["scope_ref"]["name"] == "Support" for r in rules)
    missing = add_rule(ws, kind="app", pattern="zoom.exe", category="productive", scope="profile")
    assert missing.status_code == 422  # needs the profile

    deleted = ws.client.delete(f"/api/productivity/profiles/{profile['id']}", headers=auth(ws.admin.token))
    assert deleted.status_code == 204
    assert not [r for r in ws.get("/productivity/rules").json() if r["scope"] == "profile"]
    after = report(ws, supporter.employee_id).json()
    assert after["work_profile"] is None and after["totals"]["productive_seconds"] == before
    actions = {e["action"] for e in sync_db["audit_logs"].find({"target_type": "work_profile"})}
    assert actions >= {
        "productivity.profile_created",
        "productivity.profile_members_changed",
        "productivity.profile_deleted",
    }


def test_new_scores_summary_groups_projects_and_trends(ws: Workspace) -> None:
    dept = ws.department("Delivery")
    member, agent = enrol_member(ws, "Gia Group", department_id=dept["id"])
    outsider, outsider_agent = enrol_member(ws, "Nia Nodept")
    assert add_rule(ws, kind="app", pattern="code.exe", category="productive").status_code == 201
    workday(agent)
    workday(outsider_agent)
    project = ws.post("/projects", {"name": "Signals", "member_ids": [member.employee_id]}).json()
    task = ws.post(
        "/tasks", {"project_id": project["id"], "title": "Ship it", "assignee_ids": [member.employee_id]}
    ).json()
    logged = ws.post(
        f"/tasks/{task['id']}/time", {"minutes": 90, "day": DAY.date().isoformat()}, token=member.token
    )
    assert logged.status_code == 201, logged.text

    body = report(ws, member.employee_id).json()
    assert set(body["scores"]) == {"activity_score", "productive_share", "focus_score", "work_utilization"}
    assert body["scores"]["work_utilization"]["value"] == round(100 * 90 / 300)  # 90 min on tasks of 5 h work
    assert {line["key"] for line in body["summary"]} >= {
        "active",
        "task_completion",
        "productive",
        "extended_idle",
    }
    assert body["totals"]["extended_idle_seconds"] == 30 * 60  # the 10:30-11:00 idle stretch
    (signal,) = body["projects"]
    assert signal["name"] == "Signals" and signal["task_seconds"] == 90 * 60 and signal["progress"] == 0

    day = DAY.date().isoformat()
    groups = ws.get("/productivity/groups", by="department", start=day, end=day).json()
    names = [r["group"]["name"] if r["group"] else None for r in groups["rows"]]
    assert names[-1] is None and "Delivery" in names  # by name, people without a department last
    delivery = next(r for r in groups["rows"] if r["group"] and r["group"]["name"] == "Delivery")
    assert delivery["people"] == 1 and delivery["people_with_data"] == 1
    assert set(delivery["scores"]) == {
        "activity_score",
        "productive_share",
        "focus_score",
        "work_utilization",
    }
    filtered = ws.get("/productivity/team", start=day, end=day, department_id=dept["id"]).json()
    assert [r["employee"]["id"] for r in filtered["rows"]] == [member.employee_id]
    assert filtered["projects"][0]["name"] == "Signals"
    assert "focus_score" in filtered["rows"][0] and "work_utilization" in filtered["rows"][0]

    daily = ws.get("/productivity/trend", period="daily", department_id=dept["id"]).json()
    assert daily["focus_available"] is True
    point = next(p for p in daily["points"] if p["start"] == day)
    assert point["people"] == 1 and point["task_seconds"] == 90 * 60 and point["work_utilization"] == 30
    monthly = ws.get("/productivity/trend", period="monthly").json()
    assert monthly["focus_available"] is False and all(p["focus_score"] is None for p in monthly["points"])

    # Without View activity: only your own trend.
    assert ws.get("/productivity/trend", token=member.token).status_code == 403
    assert (
        ws.get("/productivity/trend", token=member.token, employee_id=member.employee_id).status_code == 200
    )
    assert (
        ws.get("/productivity/trend", token=member.token, employee_id=outsider.employee_id).status_code == 404
    )
    assert ws.get("/productivity/groups", token=member.token, start=day, end=day).status_code == 403
