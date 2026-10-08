"""Seed a realistic workspace of N employees for load testing.

    python -m perf.seed --employees 1000            # database workpulse_perf_1000

What a workspace of N people gets (two weeks of history, ten working days):

* organisation: departments of ~100, teams of ~10 with leads, managers with reporting lines, one admin;
* a registered desktop agent per person, ~70% online right now with an open work session;
* per person per working day: one work session with presence changes, ~32 activity segments, daily app and
  website rollups;
* screenshots every 10 minutes for the last three working days (metadata only; no image files);
* projects with members and ~8 tasks per person, time entries, comments;
* alerts for the admin and managers, and an audit trail.

Documents are built with the application's own models, so their shape matches production. Passwords are hashed once
and shared (they're throwaway test accounts): random per run, or `PERF_PASSWORD`;
it is recorded in the perf database's `perf_meta` collection for the benchmark tools.
"""

from __future__ import annotations

import argparse
import os
import random
import secrets
import time
import uuid
from datetime import UTC, date, datetime, timedelta
from datetime import time as dtime
from typing import Any

from bson import ObjectId
from pymongo import MongoClient

from app.auth.permissions import Role
from app.core.security import hash_password
from app.models.activity import ActivitySegment
from app.models.agent import PresenceChange, WorkSession
from app.models.audit_log import AuditLog
from app.models.company import ActivityPolicy, Company, CompanyPlan, CompanyStatus, ScreenshotPolicy
from app.models.notification import Notification, NotificationType, Severity
from app.models.organization import Department, Device, DeviceStatus, Employee, PresenceState, Team
from app.models.productivity import Category, ProductivityRule, RuleKind
from app.models.screenshot import Screenshot
from app.models.user import User, UserStatus
from app.models.work import Project, Task, TaskComment, TaskPriority, TaskStatus, TimeEntry

APPS = [
    ("code.exe", "Visual Studio Code", Category.PRODUCTIVE),
    ("excel.exe", "Microsoft Excel", Category.PRODUCTIVE),
    ("winword.exe", "Microsoft Word", Category.PRODUCTIVE),
    ("figma.exe", "Figma", Category.PRODUCTIVE),
    ("outlook.exe", "Outlook", Category.NEUTRAL),
    ("ms-teams.exe", "Microsoft Teams", Category.NEUTRAL),
    ("slack.exe", "Slack", Category.NEUTRAL),
    ("chrome.exe", "Google Chrome", Category.NEUTRAL),
    ("msedge.exe", "Microsoft Edge", Category.NEUTRAL),
    ("explorer.exe", "File Explorer", Category.NEUTRAL),
    ("spotify.exe", "Spotify", Category.UNPRODUCTIVE),
    ("steam.exe", "Steam", Category.UNPRODUCTIVE),
]
DOMAINS = [
    "github.com",
    "docs.google.com",
    "stackoverflow.com",
    "jira.example.com",
    "youtube.com",
    "news.example.com",
]
FIRST = [
    "Ada",
    "Ben",
    "Cleo",
    "Dev",
    "Eli",
    "Fay",
    "Gus",
    "Hana",
    "Ivo",
    "Jun",
    "Kai",
    "Lea",
    "Max",
    "Nia",
    "Oz",
    "Pia",
]
LAST = [
    "Shah",
    "Okafor",
    "Lindqvist",
    "Moreau",
    "Tanaka",
    "Silva",
    "Novak",
    "Kumar",
    "Reyes",
    "Brennan",
    "Haddad",
]


def working_days(today: date, count: int) -> list[date]:
    days: list[date] = []
    d = today
    while len(days) < count:
        if d.weekday() < 5:
            days.append(d)
        d -= timedelta(days=1)
    return sorted(days)


def docs(models: list[Any]) -> list[dict[str, Any]]:
    return [m.to_document() for m in models]


def seed(employees: int, db_name: str, url: str) -> dict[str, Any]:
    rng = random.Random(employees)  # noqa: S311 - repeatable test data, not security
    client: MongoClient[dict[str, Any]] = MongoClient(url)
    client.drop_database(db_name)
    db = client[db_name]
    started = time.monotonic()
    now = datetime.now(UTC).replace(microsecond=0)
    today = now.date()
    days = working_days(today, 10)
    password = os.environ.get("PERF_PASSWORD") or secrets.token_urlsafe(16)
    pw = hash_password(password)
    counts: dict[str, int] = {}

    def insert(collection: str, rows: list[dict[str, Any]]) -> None:
        for i in range(0, len(rows), 20_000):
            db[collection].insert_many(rows[i : i + 20_000], ordered=False)
        counts[collection] = counts.get(collection, 0) + len(rows)

    company = Company(
        name=f"Perf {employees}",
        slug=f"perf-{employees}-{uuid.uuid4().hex[:6]}",
        status=CompanyStatus.ACTIVE,
        plan=CompanyPlan.ENTERPRISE,
        timezone="UTC",
        activity_policy=ActivityPolicy(
            track_applications=True, capture_window_titles=True, track_websites=True
        ),
        screenshot_policy=ScreenshotPolicy(
            enabled=True, interval_minutes=10, work_hours_only=False, retention_days=30
        ),
    )
    cid = company.id

    # --- organisation -------------------------------------------------------------------------------------------
    n_departments = max(1, employees // 100)
    departments = [Department(company_id=cid, name=f"Department {i + 1}") for i in range(n_departments)]
    teams: list[Team] = []
    for i in range(max(1, employees // 10)):
        teams.append(
            Team(company_id=cid, name=f"Team {i + 1}", department_id=departments[i % n_departments].id)
        )

    people: list[Employee] = []
    users: list[User] = []
    for i in range(employees):
        name = f"{FIRST[i % len(FIRST)]} {LAST[(i // len(FIRST)) % len(LAST)]} {i + 1}"
        email = f"perf{employees}.{i + 1}@example.com"
        team = teams[i % len(teams)]
        role = Role.EMPLOYEE
        if i == 0:
            role = Role.COMPANY_ADMIN
        elif i <= n_departments:
            role = Role.MANAGER
        elif i % 10 == 1:
            role = Role.TEAM_LEAD
        emp = Employee(
            company_id=cid,
            full_name=name,
            email=email,
            job_title="Engineer" if i % 3 else "Analyst",
            department_id=team.department_id,
            team_id=team.id,
            hired_on=now - timedelta(days=400 + i),
        )
        user = User(
            company_id=cid,
            email=email,
            full_name=name,
            password_hash=pw,
            role=role,
            status=UserStatus.ACTIVE,
            email_verified=True,
            password_changed_at=now,
            employee_id=emp.id,
        )
        emp.user_id = user.id
        people.append(emp)
        users.append(user)

    # Reporting lines: department managers (employees 1..D) manage their department's team leads; leads manage their team.
    managers = {departments[i].id: people[i + 1] for i in range(min(n_departments, employees - 1))}
    for d in departments:
        if d.id in managers:
            d.head_employee_id = managers[d.id].id
    leads: dict[ObjectId, Employee] = {}
    for p, u in zip(people, users, strict=True):
        if u.role == Role.TEAM_LEAD and p.team_id not in leads:
            leads[p.team_id] = p  # type: ignore[index]
    for t in teams:
        if t.id in leads:
            t.lead_employee_id = leads[t.id].id
    for p, u in zip(people, users, strict=True):
        if u.role == Role.COMPANY_ADMIN:
            continue
        if u.role == Role.MANAGER:
            p.manager_employee_id = people[0].id
        elif p.team_id in leads and leads[p.team_id] is not p:
            p.manager_employee_id = leads[p.team_id].id  # type: ignore[index]
        elif p.department_id in managers:
            p.manager_employee_id = managers[p.department_id].id  # type: ignore[index]

    db["companies"].insert_one(company.to_document())
    db["perf_meta"].insert_one({"password": password})  # disposable load-test database only
    insert("departments", docs(departments))
    insert("teams", docs(teams))
    insert("employees", docs(people))
    insert("users", docs(users))

    rules = [
        ProductivityRule(company_id=cid, kind=RuleKind.APP, pattern=app_id, category=cat)
        for app_id, _, cat in APPS
    ]
    insert("productivity_rules", docs(rules))

    # --- devices, sessions, activity ------------------------------------------------------------------------------
    devices: list[Device] = []
    sessions: list[dict[str, Any]] = []
    segments: list[dict[str, Any]] = []
    daily: dict[tuple[Any, ...], list[float]] = {}
    websites: dict[tuple[Any, ...], float] = {}
    shots: list[dict[str, Any]] = []
    online_now: set[ObjectId] = set()
    for p in people:
        online = rng.random() < 0.7
        device = Device(
            company_id=cid,
            employee_id=p.id,
            name=f"{p.full_name.split()[0]}-laptop",
            hostname=f"wp-{p.id}",
            os_version="Windows 11",
            agent_version="1.6.0",
            status=DeviceStatus.ACTIVE,
            enrolled_at=now - timedelta(days=60),
            last_seen_at=now - timedelta(seconds=rng.randint(5, 50)) if online else now - timedelta(hours=14),
            presence=PresenceState.ACTIVE if online else None,
            presence_since=now - timedelta(minutes=rng.randint(1, 90)) if online else None,
            current_app=APPS[rng.randrange(len(APPS))][1] if online else None,
            current_app_since=now - timedelta(minutes=rng.randint(1, 30)) if online else None,
        )
        devices.append(device)
        if online:
            online_now.add(p.id)
        for di, day in enumerate(days):
            is_today = day == today
            start = datetime.combine(day, dtime(8, rng.randint(0, 59)), UTC)
            end = start + timedelta(hours=8, minutes=rng.randint(0, 60))
            if is_today:
                if not online:
                    continue
                # Whatever the time of day the seed runs, today has a few hours of work leading up to now.
                start = now - timedelta(hours=rng.uniform(3, 7))
                end = now
            client_session = str(uuid.uuid4())
            changes = []
            t = start
            while t < end:
                changes.append(PresenceChange(at=t, status="active"))
                t += timedelta(minutes=rng.randint(30, 90))
                if t < end:
                    changes.append(PresenceChange(at=t, status="idle"))
                    t += timedelta(minutes=rng.randint(3, 15))
            span = int((end - start).total_seconds())
            ws = WorkSession(
                company_id=cid,
                employee_id=p.id,
                device_id=device.id,
                client_session_id=client_session,
                started_at=start,
                ended_at=None if is_today else end,
                end_reason=None if is_today else "signed_out",
                active_seconds=int(span * 0.85),
                idle_seconds=int(span * 0.15),
                presence_changes=changes,
            )
            if is_today:
                device.current_session_id = client_session
            sessions.append(ws.to_document())
            # ~15-minute foreground segments
            t = start
            while t < end:
                seg_end = min(end, t + timedelta(minutes=rng.randint(8, 22)))
                app_id, app_name, _ = APPS[rng.randrange(len(APPS))]
                dur = int((seg_end - t).total_seconds())
                active = int(dur * rng.uniform(0.6, 1.0))
                domain = rng.choice(DOMAINS) if app_id in ("chrome.exe", "msedge.exe") else None
                segments.append(
                    ActivitySegment(
                        company_id=cid,
                        employee_id=p.id,
                        device_id=device.id,
                        event_id=str(uuid.uuid4()),
                        session_id=client_session,
                        app_id=app_id,
                        app_name=app_name,
                        window_title=f"{app_name} - work item {rng.randint(1, 500)}",
                        domain=domain,
                        started_at=t,
                        ended_at=seg_end,
                        duration_seconds=dur,
                        active_seconds=active,
                        activity_level=rng.randint(20, 95),
                    ).to_document()
                )
                key = (p.id, day.isoformat(), app_id)
                acc = daily.setdefault(key, [0.0, 0.0])
                acc[0] += dur
                acc[1] += active
                if domain:
                    wkey = (p.id, day.isoformat(), app_id, domain)
                    websites[wkey] = websites.get(wkey, 0.0) + dur
                t = seg_end
            if di >= len(days) - 3:  # screenshots for the last three working days
                t = start
                while t < end:
                    shots.append(
                        Screenshot(
                            company_id=cid,
                            employee_id=p.id,
                            device_id=device.id,
                            client_id=str(uuid.uuid4()),
                            session_id=client_session,
                            captured_at=t,
                            width=1920,
                            height=1080,
                            object_key=f"perf/{cid}/{uuid.uuid4().hex}",
                            thumb_key=f"perf/{cid}/{uuid.uuid4().hex}-t",
                            size_bytes=180_000,
                            thumb_size_bytes=12_000,
                            expires_at=t + timedelta(days=30),
                        ).to_document()
                    )
                    t += timedelta(minutes=10)
        if len(segments) > 100_000:
            insert("activity_segments", segments)
            segments = []
    insert("devices", docs(devices))
    insert("work_sessions", sessions)
    insert("activity_segments", segments)
    insert("screenshots", shots)
    app_names = {a: n for a, n, _ in APPS}
    insert(
        "activity_daily",
        [
            {
                "_id": ObjectId(),
                "company_id": cid,
                "employee_id": e,
                "day": d,
                "app_id": a,
                "app_name": app_names[a],
                "seconds": round(v[0], 2),
                "active_seconds": round(v[1], 2),
                "created_at": now,
                "updated_at": now,
            }
            for (e, d, a), v in daily.items()
        ],
    )
    insert(
        "website_daily",
        [
            {
                "_id": ObjectId(),
                "company_id": cid,
                "employee_id": e,
                "day": d,
                "app_id": a,
                "domain": dom,
                "seconds": round(v, 2),
                "created_at": now,
                "updated_at": now,
            }
            for (e, d, a, dom), v in websites.items()
        ],
    )

    # --- projects & tasks -----------------------------------------------------------------------------------------
    projects: list[Project] = []
    tasks: list[Task] = []
    entries: list[TimeEntry] = []
    comments: list[TaskComment] = []
    for t in teams:
        members = [p.id for p in people if p.team_id == t.id]
        project = Project(
            company_id=cid,
            name=f"{t.name} roadmap",
            key=f"P{len(projects) + 1}",
            member_ids=members,
            owner_employee_id=members[0] if members else None,
        )
        projects.append(project)
        for n in range(len(members) * 8):
            assignee = members[n % len(members)]
            status = rng.choice(list(TaskStatus))
            due = now + timedelta(days=rng.randint(-10, 30))
            task = Task(
                company_id=cid,
                project_id=project.id,
                number=n + 1,
                title=f"Work item {n + 1}",
                status=status,
                priority=rng.choice(list(TaskPriority)),
                assignee_ids=[assignee],
                due_date=due,
                rank=float(n),
                completed_at=now - timedelta(days=rng.randint(0, 9))
                if status == TaskStatus.COMPLETED
                else None,
                time_spent_seconds=rng.randint(0, 20_000),
            )
            tasks.append(task)
            if n % 4 == 0:
                day = rng.choice(days)
                s = datetime.combine(day, dtime(10), UTC)
                entries.append(
                    TimeEntry(
                        company_id=cid,
                        task_id=task.id,
                        project_id=project.id,
                        employee_id=assignee,
                        started_at=s,
                        ended_at=s + timedelta(hours=1),
                        seconds=3600,
                    )
                )
            if n % 3 == 0:
                comments.append(
                    TaskComment(company_id=cid, task_id=task.id, author_employee_id=assignee, body="Update")
                )
        project.task_counter = len(members) * 8
    insert("projects", docs(projects))
    insert("tasks", docs(tasks))
    insert("time_entries", docs(entries))
    insert("task_comments", docs(comments))

    # --- alerts & audit trail ----------------------------------------------------------------------------------------
    recipients = [u for u in users if u.role in (Role.COMPANY_ADMIN, Role.MANAGER)]
    notes: list[Notification] = []
    for u in recipients:
        for k in range(min(employees * 2, 2000)):
            p = people[k % employees]
            at = now - timedelta(minutes=k * 7)
            notes.append(
                Notification(
                    company_id=cid,
                    recipient_user_id=u.id,
                    type=NotificationType.EXTENDED_IDLE if k % 2 else NotificationType.TASK_OVERDUE,
                    severity=Severity.WARNING if k % 2 else Severity.INFO,
                    title=f"{p.full_name} has been idle",
                    body="Idle for 35 minutes during a work session.",
                    employee_id=p.id,
                    employee_name=p.full_name,
                    subject_key=f"perf:{k}",
                    last_occurred_at=at,
                    read_at=at if k % 3 else None,
                    created_at=at,
                )
            )
    insert("notifications", docs(notes))
    audit: list[AuditLog] = []
    for k in range(employees * 20):
        p = users[k % employees]
        audit.append(
            AuditLog(
                company_id=cid,
                action=rng.choice(
                    ["auth.login", "screenshot.viewed", "employee.updated", "report.downloaded"]
                ),
                actor_user_id=users[0].id if k % 2 else p.id,
                subject_employee_id=p.employee_id,
                ip_address="10.0.0.1",
                user_agent="Mozilla/5.0 (Windows NT 10.0) Chrome/130.0",
                created_at=now - timedelta(minutes=k),
            )
        )
    insert("audit_logs", docs(audit))

    manager_user = next(u for u in users if u.role == Role.MANAGER) if employees > 1 else users[0]
    lead_user = next((u for u in users if u.role == Role.TEAM_LEAD), users[0])
    employee_user = next(u for u in users if u.role == Role.EMPLOYEE)
    summary = {
        "db": db_name,
        "employees": employees,
        "online_now": len(online_now),
        "seconds": round(time.monotonic() - started, 1),
        "admin": users[0].email,
        "manager": manager_user.email,
        "team_lead": lead_user.email,
        "employee": employee_user.email,
        "sample_employee_id": str(people[min(5, employees - 1)].id),
        "sample_project_id": str(projects[0].id),
        "counts": counts,
    }
    client.close()
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--employees", type=int, default=100)
    parser.add_argument("--db", default=None)
    parser.add_argument("--url", default=os.environ.get("MONGODB_URL", "mongodb://localhost:27017"))
    args = parser.parse_args()
    result = seed(args.employees, args.db or f"workpulse_perf_{args.employees}", args.url)
    for key, value in result.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
