"""Phase 9: projects & tasks — access, subtasks, board, timer, comments, attachments, dashboards, productivity."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from bson import ObjectId
from fastapi.testclient import TestClient

from tests.conftest import register
from tests.org_helpers import Actor, Workspace, auth


def project(ws: Workspace, name: str, members: list[Actor], token: str | None = None, **extra: Any) -> Any:
    return ws.post(
        "/projects", {"name": name, "member_ids": [m.employee_id for m in members], **extra}, token=token
    )


def task(ws: Workspace, project_id: str, title: str, token: str | None = None, **extra: Any) -> Any:
    return ws.post("/tasks", {"project_id": project_id, "title": title, **extra}, token=token)


def put(ws: Workspace, path: str, body: dict[str, Any], token: str | None = None) -> Any:
    return ws.client.put(f"/api{path}", json=body, headers=auth(token or ws.admin.token))


def delete(ws: Workspace, path: str, token: str | None = None) -> Any:
    return ws.client.delete(f"/api{path}", headers=auth(token or ws.admin.token))


def today() -> date:
    return datetime.now(UTC).date()


# --------------------------------------------------------------------------- projects & access


def test_projects_access_and_keys(ws: Workspace, client: TestClient) -> None:
    alice = ws.member("Alice Member")
    bob = ws.member("Bob Outsider")
    created = project(ws, "Website Redesign", [alice])
    assert created.status_code == 201, created.text
    p = created.json()
    assert p["key"] == "WR" and {m["full_name"] for m in p["members"]} >= {"Alice Member"}
    assert project(ws, "Mobile App", [], key="WR").status_code == 409
    assert project(ws, "Website Revamp", []).json()["key"] != "WR"  # auto key de-duplicated
    assert project(ws, "Not allowed", [], token=alice.token).status_code == 403

    assert [x["id"] for x in ws.get("/projects", token=alice.token).json()] == [p["id"]]
    assert ws.get("/projects", token=bob.token).json() == []
    assert ws.get(f"/projects/{p['id']}", token=bob.token).status_code == 404
    rival = str(register(client, company_name="Rival Projects")["access_token"])
    assert ws.get(f"/projects/{p['id']}", token=rival).status_code == 404

    lead = ws.member("Lena Lead", role="TEAM_LEAD")
    report = ws.member("Rex Report", manager_employee_id=lead.employee_id)
    q = project(ws, "Lead visible", [report]).json()
    assert q["id"] in {x["id"] for x in ws.get("/projects", token=lead.token).json()}  # via a report in scope
    assert (
        task(ws, q["id"], "Lead can manage", token=lead.token, assignee_ids=[report.employee_id]).status_code
        == 201
    )

    removed = put(ws, f"/projects/{p['id']}/members", {"member_ids": []}).json()
    assert [m["full_name"] for m in removed["members"]] == ["Ada Admin"] or removed[
        "members"
    ] == []  # owner stays
    archived = ws.patch(f"/projects/{p['id']}", {"status": "archived"}).json()
    assert archived["status"] == "archived" and p["id"] not in {x["id"] for x in ws.get("/projects").json()}
    assert task(ws, p["id"], "Too late").json()["error"]["code"] == "project_archived"


def test_tasks_subtasks_assignment_rules_and_filters(ws: Workspace) -> None:
    alice, carl = ws.member("Alice Doer"), ws.member("Carl Colleague")
    p = project(ws, "Platform", [alice, carl], key="PLT").json()

    t1 = task(
        ws,
        p["id"],
        "Write API",
        assignee_ids=[alice.employee_id],
        priority="high",
        due_date=str(today() - timedelta(days=1)),
    ).json()
    assert (
        t1["reference"] == "PLT-1"
        and t1["overdue"] is True
        and t1["assignees"][0]["full_name"] == "Alice Doer"
    )
    own = task(ws, p["id"], "Alice's own", token=alice.token, assignee_ids=[alice.employee_id])
    assert own.status_code == 201 and own.json()["reference"] == "PLT-2"
    assert (
        task(ws, p["id"], "Assign Carl", token=alice.token, assignee_ids=[carl.employee_id]).status_code
        == 403
    )
    outsider = ws.member("Olga Outside")
    assert (
        task(ws, p["id"], "Non-member", assignee_ids=[outsider.employee_id]).json()["error"]["code"]
        == "not_a_member"
    )

    sub = task(ws, p["id"], "Design schema", parent_id=t1["id"])
    assert sub.status_code == 201
    assert (
        task(ws, p["id"], "Too deep", parent_id=sub.json()["id"]).json()["error"]["code"]
        == "nesting_too_deep"
    )
    board = ws.get("/tasks", project_id=p["id"]).json()
    first = next(t for t in board if t["id"] == t1["id"])
    assert first["subtask_total"] == 1 and first["subtask_done"] == 0
    assert all(t["parent_id"] is None for t in board)

    mine = ws.get("/tasks", token=alice.token, assignee="me").json()
    assert {t["title"] for t in mine} == {"Write API", "Alice's own"}
    assert [t["title"] for t in ws.get("/tasks", project_id=p["id"], due="overdue").json()] == ["Write API"]
    assert [t["title"] for t in ws.get("/tasks", project_id=p["id"], search="api").json()] == ["Write API"]

    # Carl may read but not edit Alice's task; Alice may edit her own.
    assert ws.patch(f"/tasks/{t1['id']}", {"title": "Hacked"}, token=carl.token).status_code == 403
    updated = ws.patch(
        f"/tasks/{t1['id']}",
        {"title": "Write the API", "priority": "urgent", "clear_due_date": True},
        token=alice.token,
    ).json()
    assert updated["title"] == "Write the API" and updated["due_date"] is None and updated["overdue"] is False
    detail = ws.get(f"/tasks/{t1['id']}").json()
    kinds = [a["kind"] for a in detail["activity"]]
    assert {"created", "renamed", "priority_changed", "due_changed", "subtask_added"} <= set(kinds)
    assert [s["title"] for s in detail["subtasks"]] == ["Design schema"]

    assert delete(ws, f"/tasks/{t1['id']}", token=carl.token).status_code == 403
    assert delete(ws, f"/tasks/{t1['id']}").status_code == 204
    assert ws.get(f"/tasks/{sub.json()['id']}").status_code == 404  # subtasks go with their parent


def test_board_moves_and_completion(ws: Workspace, sync_db: Any) -> None:
    alice = ws.member("Alice Board")
    p = project(ws, "Board", [alice], key="BRD").json()
    a, b, c = (task(ws, p["id"], name, assignee_ids=[alice.employee_id]).json() for name in ("A", "B", "C"))

    ws.post(f"/tasks/{c['id']}/move", {"status": "TODO", "index": 0})
    order = [t["title"] for t in ws.get("/tasks", project_id=p["id"], status="TODO").json()]
    assert order == ["C", "A", "B"]

    moved = ws.post(f"/tasks/{a['id']}/move", {"status": "IN_REVIEW", "index": 0}, token=alice.token).json()
    assert moved["status"] == "IN_REVIEW"
    done = ws.post(f"/tasks/{a['id']}/move", {"status": "COMPLETED", "index": 0}, token=alice.token).json()
    assert done["completed_at"] is not None
    reopened = ws.patch(f"/tasks/{a['id']}", {"status": "BLOCKED"}).json()
    assert reopened["completed_at"] is None
    statuses = [
        x["data"].get("to")
        for x in ws.get(f"/tasks/{a['id']}").json()["activity"]
        if x["kind"] == "status_changed"
    ]
    assert statuses == ["BLOCKED", "COMPLETED", "IN_REVIEW"]
    progress = ws.get(f"/projects/{p['id']}").json()["stats"]
    assert progress["total"] == 3 and progress["by_status"]["BLOCKED"] == 1
    del b


# --------------------------------------------------------------------------- timer and time


def test_timer_one_at_a_time_switching_rollup_and_manual_time(ws: Workspace, sync_db: Any) -> None:
    alice = ws.member("Alice Timer")
    p = project(ws, "Timers", [alice], key="TIM").json()
    t1 = task(ws, p["id"], "First", assignee_ids=[alice.employee_id]).json()
    t2 = task(ws, p["id"], "Second", assignee_ids=[alice.employee_id]).json()

    started = ws.post(f"/tasks/{t1['id']}/timer/start", {}, token=alice.token).json()
    assert started["running"] and started["task"]["id"] == t1["id"]
    assert ws.get(f"/tasks/{t1['id']}").json()["status"] == "IN_PROGRESS"  # starting work moves it along
    # Backdate the running entry by 25 minutes, then switch: the first entry closes with the time.
    sync_db["time_entries"].update_one(
        {"employee_id": ObjectId(alice.employee_id), "ended_at": None},
        {"$set": {"started_at": datetime.now(UTC) - timedelta(minutes=25)}},
    )
    switched = ws.post(f"/tasks/{t2['id']}/timer/start", {}, token=alice.token).json()
    assert switched["task"]["id"] == t2["id"]
    assert (
        sync_db["time_entries"].count_documents(
            {"employee_id": ObjectId(alice.employee_id), "ended_at": None}
        )
        == 1
    )
    first = ws.get(f"/tasks/{t1['id']}").json()
    assert 24 * 60 <= first["time_spent_seconds"] <= 26 * 60 and first["timer_running"] is False

    # Completing the task stops its running timer.
    ws.patch(f"/tasks/{t2['id']}", {"status": "COMPLETED"}, token=alice.token)
    assert ws.get("/me/timer", token=alice.token).json()["running"] is False
    assert (
        ws.post(f"/tasks/{t2['id']}/timer/start", {}, token=alice.token).json()["error"]["code"]
        == "task_completed"
    )

    logged = ws.post(
        f"/tasks/{t1['id']}/time", {"minutes": 30, "day": str(today()), "note": "Pairing"}, token=alice.token
    )
    assert logged.status_code == 201 and logged.json()["source"] == "manual"
    assert (
        ws.post(
            f"/tasks/{t1['id']}/time",
            {"minutes": 30, "day": str(today() + timedelta(days=2))},
            token=alice.token,
        ).status_code
        == 400
    )
    detail = ws.get(f"/tasks/{t1['id']}").json()
    assert detail["time_spent_seconds"] >= 55 * 60 and len(detail["time_entries"]) == 2
    assert ws.get("/me/timer", token=alice.token).json()["today_seconds"] >= 55 * 60

    stranger = ws.member("Sam Stranger")
    assert ws.post(f"/tasks/{t1['id']}/timer/start", {}, token=stranger.token).status_code == 404


# --------------------------------------------------------------------------- comments & attachments


def test_comments(ws: Workspace) -> None:
    alice, carl = ws.member("Alice Talk"), ws.member("Carl Talk")
    p = project(ws, "Talk", [alice, carl], key="TLK").json()
    t = task(ws, p["id"], "Discuss", assignee_ids=[alice.employee_id]).json()
    c = ws.post(f"/tasks/{t['id']}/comments", {"body": "  Looks good  "}, token=carl.token).json()
    assert c["body"] == "Looks good" and c["author"]["full_name"] == "Carl Talk"
    assert (
        ws.patch(f"/tasks/{t['id']}/comments/{c['id']}", {"body": "Edited"}, token=alice.token).status_code
        == 403
    )
    edited = ws.patch(
        f"/tasks/{t['id']}/comments/{c['id']}", {"body": "Looks great"}, token=carl.token
    ).json()
    assert edited["edited_at"] is not None
    assert ws.get(f"/tasks/{t['id']}").json()["comment_count"] == 1
    assert delete(ws, f"/tasks/{t['id']}/comments/{c['id']}", token=carl.token).status_code == 204
    assert ws.get(f"/tasks/{t['id']}").json()["comment_count"] == 0


def test_attachments_are_private_signed_and_removable(
    ws: Workspace, client: TestClient, sync_db: Any, storage_dir: str
) -> None:
    alice, carl = ws.member("Alice Files"), ws.member("Carl Files")
    p = project(ws, "Files", [alice, carl], key="FIL").json()
    t = task(ws, p["id"], "Spec", assignee_ids=[alice.employee_id]).json()
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 64
    up = client.post(
        f"/api/tasks/{t['id']}/attachments",
        params={"filename": "../../etc/screen shot.png"},
        content=png,
        headers={**auth(alice.token), "Content-Type": "image/png"},
    )
    assert up.status_code == 201, up.text
    a = up.json()
    assert a["filename"] == ".._.._etc_screen shot.png" and a["size_bytes"] == len(png)
    doc = sync_db["task_attachments"].find_one({"_id": ObjectId(a["id"])})
    assert png not in Path(storage_dir, doc["object_key"]).read_bytes()  # encrypted at rest

    got = client.get(a["download_url"])
    assert (
        got.status_code == 200
        and got.content == png
        and got.headers["content-disposition"].startswith("inline")
    )
    pdf_like = client.post(
        f"/api/tasks/{t['id']}/attachments",
        params={"filename": "run.html"},
        content=b"<script>x</script>",
        headers={**auth(alice.token), "Content-Type": "text/html"},
    ).json()
    html = client.get(pdf_like["download_url"])
    assert html.headers["content-type"] == "application/octet-stream" and html.headers[
        "content-disposition"
    ].startswith("attachment")

    parsed = urlparse(a["download_url"])
    query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
    assert client.get(parsed.path, params={**query, "s": "0" * 64}).status_code == 404
    assert client.get(parsed.path, params={**query, "u": carl.user_id}).status_code == 404

    assert delete(ws, f"/tasks/{t['id']}/attachments/{a['id']}", token=carl.token).status_code == 403
    too_big = client.post(
        f"/api/tasks/{t['id']}/attachments",
        params={"filename": "big.bin"},
        content=b"0" * (9 * 1024 * 1024 + 1),
        headers=auth(alice.token),
    )
    assert too_big.status_code == 413
    assert delete(ws, f"/tasks/{t['id']}/attachments/{a['id']}", token=alice.token).status_code == 204
    assert client.get(a["download_url"]).status_code == 404


# --------------------------------------------------------------------------- dashboards & productivity


def test_my_work_summary_and_productivity_integration(ws: Workspace, sync_db: Any) -> None:
    alice = ws.member("Alice Busy")
    p = project(ws, "Delivery", [alice], key="DLV").json()
    yesterday, tomorrow = today() - timedelta(days=1), today() + timedelta(days=1)
    late = task(ws, p["id"], "Late one", assignee_ids=[alice.employee_id], due_date=str(yesterday)).json()
    now_task = task(ws, p["id"], "Today's", assignee_ids=[alice.employee_id], due_date=str(today())).json()
    soon = task(ws, p["id"], "Soon", assignee_ids=[alice.employee_id], due_date=str(tomorrow)).json()
    busy = task(
        ws,
        p["id"],
        "Started early",
        assignee_ids=[alice.employee_id],
        due_date=str(tomorrow),
        status="IN_PROGRESS",
    ).json()
    done = task(ws, p["id"], "Done on time", assignee_ids=[alice.employee_id], due_date=str(tomorrow)).json()
    ws.patch(f"/tasks/{done['id']}", {"status": "COMPLETED"})
    ws.post(f"/tasks/{now_task['id']}/timer/start", {}, token=alice.token)

    work = ws.get("/me/work", token=alice.token).json()
    assert work["current_task"]["id"] == now_task["id"] and work["timer"]["running"]
    assert [t["id"] for t in work["overdue"]] == [late["id"]]
    assert now_task["id"] in {t["id"] for t in work["today"]} and soon["id"] in {
        t["id"] for t in work["upcoming"]
    }
    # In-progress work shows under Today only, even when it's due later this week.
    assert busy["id"] in {t["id"] for t in work["today"]}
    assert busy["id"] not in {t["id"] for t in work["upcoming"]}
    assert work["counts"]["overdue"] == 1 and work["counts"]["completed_today"] == 1

    sync_db["time_entries"].update_one(
        {"employee_id": ObjectId(alice.employee_id), "ended_at": None},
        {"$set": {"started_at": datetime.now(UTC) - timedelta(minutes=40)}},
    )
    ws.post("/me/timer/stop", {}, token=alice.token)
    summary = ws.get("/work/summary", start=str(yesterday), end=str(today())).json()
    row = next(m for m in summary["members"] if m["employee"]["id"] == alice.employee_id)
    assert row["completed_in_period"] == 1 and row["overdue"] == 1 and row["time_spent_seconds"] >= 39 * 60
    assert summary["on_time_rate"] == 100 and summary["completed"] >= 1
    assert (
        ws.get("/work/summary", start=str(today()), end=str(today() - timedelta(days=3))).status_code == 400
    )

    report = ws.get(
        f"/productivity/employees/{alice.employee_id}", start=str(yesterday), end=str(today())
    ).json()
    tc = report["task_completion"]
    assert tc["available"] and tc["completed"] == 1 and tc["due_open"] == 2  # late one + today's
    assert tc["value"] == 33 and "Tasks completed" in tc["formula"]
    assert report["totals"]["task_seconds"] >= 39 * 60 and report["totals"]["tasks_completed"] == 1
    assert any("logged on tasks" in i["title"] for i in report["insights"])


# --------------------------------------------------------------------------- Phase 11: milestones, labels, timeline


def test_milestones_progress_permissions_and_release_on_delete(ws: Workspace, client: TestClient) -> None:
    alice = ws.member("Mia Member")
    p = project(ws, "Launch", [alice], key="LCH").json()
    other = project(ws, "Elsewhere", [alice], key="ELS").json()

    assert ws.post(f"/projects/{p['id']}/milestones", {"name": "Nope"}, token=alice.token).status_code == 403
    due = str(today() - timedelta(days=1))
    m = ws.post(f"/projects/{p['id']}/milestones", {"name": "Beta", "due_date": due}).json()
    assert m["total"] == 0 and m["progress"] == 0 and m["overdue"] is True and m["can_manage"] is True
    foreign = ws.post(f"/projects/{other['id']}/milestones", {"name": "Other"}).json()

    t1 = task(ws, p["id"], "One", milestone_id=m["id"]).json()
    task(ws, p["id"], "Two", milestone_id=m["id"])
    task(ws, p["id"], "Sub", parent_id=t1["id"], milestone_id=m["id"])  # subtasks don't count
    assert t1["milestone_id"] == m["id"]
    bad = task(ws, p["id"], "Wrong project", milestone_id=foreign["id"])
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "invalid_reference"
    ws.patch(f"/tasks/{t1['id']}", {"status": "COMPLETED"})

    listed = ws.get(f"/projects/{p['id']}/milestones", token=alice.token).json()
    assert [(x["name"], x["total"], x["completed"], x["progress"]) for x in listed] == [("Beta", 2, 1, 50)]
    assert listed[0]["can_manage"] is False  # members see milestones but don't manage them
    assert [t["title"] for t in ws.get("/tasks", project_id=p["id"], milestone_id=m["id"]).json()] == [
        "One",
        "Two",
    ]
    assert ws.get("/tasks", project_id=p["id"], milestone_id="none").json() == []

    closed = ws.patch(f"/milestones/{m['id']}", {"closed": True, "due_date": None}).json()
    assert closed["closed"] and closed["closed_at"] and closed["due_date"] is None and not closed["overdue"]
    assert ws.patch(f"/milestones/{m['id']}", {"name": "x"}, token=alice.token).status_code == 403
    outsider = ws.member("Out Sider")
    assert ws.patch(f"/milestones/{m['id']}", {"name": "x"}, token=outsider.token).status_code == 404

    # Moving a task out of the milestone is logged; deleting the milestone keeps its tasks.
    ws.patch(f"/tasks/{t1['id']}", {"milestone_id": None})
    detail = ws.get(f"/tasks/{t1['id']}").json()
    assert detail["milestone_id"] is None
    assert any(a["kind"] == "milestone_changed" and a["data"]["from"] == "Beta" for a in detail["activity"])
    assert delete(ws, f"/milestones/{m['id']}").status_code == 204
    remaining = ws.get("/tasks", project_id=p["id"]).json()
    assert {t["title"] for t in remaining} == {"One", "Two"} and all(
        t["milestone_id"] is None for t in remaining
    )
    assert ws.get(f"/projects/{p['id']}/milestones").json() == []


def test_labels_are_normalised_filterable_and_counted(ws: Workspace) -> None:
    p = project(ws, "Labels", [], key="LBL").json()
    t = task(ws, p["id"], "Tagged", labels=["  Bug ", "bug", "Front  End"]).json()
    assert t["labels"] == ["bug", "front end"]
    task(ws, p["id"], "Also a bug", labels=["bug"])
    assert task(ws, p["id"], "Too many", labels=[f"l{i}" for i in range(11)]).status_code == 422
    assert task(ws, p["id"], "Comma", labels=["a,b"]).status_code == 422

    assert [x["title"] for x in ws.get("/tasks", project_id=p["id"], label="BUG").json()] == [
        "Tagged",
        "Also a bug",
    ]
    assert ws.get(f"/projects/{p['id']}/labels").json() == [
        {"name": "bug", "count": 2},
        {"name": "front end", "count": 1},
    ]
    updated = ws.patch(f"/tasks/{t['id']}", {"labels": ["Bug", "urgent-fix"]}).json()
    assert updated["labels"] == ["bug", "urgent-fix"]
    activity = ws.get(f"/tasks/{t['id']}").json()["activity"]
    change = next(a for a in activity if a["kind"] == "labels_changed")
    assert change["data"] == {"added": ["urgent-fix"], "removed": ["front end"]}
    assert ws.patch(f"/tasks/{t['id']}", {"labels": None}).json()["labels"] == []


def test_start_dates_for_the_timeline(ws: Workspace) -> None:
    p = project(ws, "Timeline", [], key="TML").json()
    start, due = today(), today() + timedelta(days=5)
    t = task(ws, p["id"], "Spans", start_date=str(start), due_date=str(due)).json()
    assert (t["start_date"], t["due_date"]) == (str(start), str(due))
    late = task(ws, p["id"], "Backwards", start_date=str(due), due_date=str(start))
    assert late.status_code == 400 and late.json()["error"]["code"] == "invalid_dates"
    assert ws.patch(f"/tasks/{t['id']}", {"start_date": str(due + timedelta(days=1))}).status_code == 400
    assert ws.patch(f"/tasks/{t['id']}", {"due_date": str(start - timedelta(days=1))}).status_code == 400
    assert ws.patch(f"/tasks/{t['id']}", {"start_date": None}).json()["start_date"] is None
    assert ws.patch(f"/tasks/{t['id']}", {"title": "Still dated"}).json()["due_date"] == str(due)


def test_dashboard_lists_my_tasks_recent_blocked_and_overdue(ws: Workspace) -> None:
    bea = ws.member("Bea Busy")
    p = project(ws, "Ops", [bea], key="OPS").json()
    mine = {"assignee_ids": [bea.employee_id]}
    late = task(ws, p["id"], "Late", due_date=str(today() - timedelta(days=2)), **mine).json()
    stuck = task(ws, p["id"], "Stuck", status="BLOCKED", **mine).json()
    later = task(ws, p["id"], "Later", due_date=str(today() + timedelta(days=20)), **mine).json()
    done = task(ws, p["id"], "Done", **mine).json()
    ws.patch(f"/tasks/{done['id']}", {"status": "COMPLETED"})

    work = ws.get("/me/work", token=bea.token).json()
    assert [t["id"] for t in work["assigned"]] == [
        late["id"],
        later["id"],
        stuck["id"],
    ]  # overdue, dated, undated
    assert [t["id"] for t in work["recently_completed"]] == [done["id"]]
    assert work["counts"]["blocked"] == 1

    summary = ws.get("/work/summary", start=str(today() - timedelta(days=6)), end=str(today())).json()
    assert summary["blocked"] == 1 and [t["id"] for t in summary["blocked_tasks"]] == [stuck["id"]]
    assert [t["id"] for t in summary["overdue_tasks"]] == [late["id"]]
    row = next(m for m in summary["members"] if m["employee"]["id"] == bea.employee_id)
    assert row["blocked"] == 1 and row["overdue"] == 1
