"""Report builders: each report type turns the requester's scope and filters into typed columns and rows.

Every builder only sees employees the requester may see (the same access scope as the rest of WorkPulse),
and each type additionally requires the permission for its data (see `REPORT_TYPES`). Rows hold raw values
(seconds, datetimes, percentages); the writers decide how each format shows them.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta, tzinfo
from typing import Any, Literal
from zoneinfo import ZoneInfo

from bson import ObjectId

from app.auth.permissions import Permission
from app.auth.principal import Principal
from app.models.company import Company
from app.models.organization import Employee, EmployeeStatus
from app.models.report import ReportFilters, ReportType
from app.models.work import ProjectStatus, TaskStatus
from app.repositories.agent import WorkSessionRepository
from app.repositories.live import LiveSessionRepository
from app.repositories.organization import (
    DepartmentRepository,
    DeviceRepository,
    EmployeeRepository,
    TeamRepository,
)
from app.repositories.productivity import WorkProfileRepository
from app.repositories.screenshot import ScreenshotRepository
from app.repositories.user import UserRepository
from app.repositories.work import MilestoneRepository, ProjectRepository, TaskRepository, TimeEntryRepository
from app.services.access_scope import AccessScopeService
from app.services.productivity.engine import (
    Metrics,
    activity_score,
    focus_score,
    productive_share,
    task_completion,
    work_utilization,
)
from app.services.productivity.service import ProductivityService
from app.services.work.service import WorkService
from app.utils.time import utcnow

Kind = Literal["text", "int", "duration", "percent", "datetime", "date", "time"]
#: Focus and app switching need per-segment analysis; longer reports leave them out (and say so).
SEGMENT_LIMIT_DAYS = 31
MAX_LIST_ROWS = 200_000


@dataclass(frozen=True, slots=True)
class Column:
    key: str
    label: str
    kind: Kind = "text"


@dataclass
class ReportData:
    title: str
    columns: list[Column]
    rows: list[dict[str, Any]]
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ReportTypeInfo:
    key: ReportType
    label: str
    description: str
    #: Beyond REPORT_VIEW, the permission the underlying data needs.
    requires: Permission | None
    #: Which filters make sense for this type (the UI shows only these).
    filters: tuple[str, ...]


PEOPLE_FILTERS = ("employee", "department", "team", "role", "work_profile")
REPORT_TYPES: dict[ReportType, ReportTypeInfo] = {
    t.key: t
    for t in (
        ReportTypeInfo(
            ReportType.ATTENDANCE,
            "Attendance",
            "Per person and day: first start, last end and hours, from desktop-agent work sessions.",
            Permission.ACTIVITY_VIEW,
            PEOPLE_FILTERS,
        ),
        ReportTypeInfo(
            ReportType.WORK_HOURS,
            "Work hours",
            "Per person and day: work, active, idle, extended idle and away time.",
            Permission.ACTIVITY_VIEW,
            PEOPLE_FILTERS,
        ),
        ReportTypeInfo(
            ReportType.ACTIVITY,
            "Activity",
            "Per person: activity score, focus sessions and application switching for the period.",
            Permission.ACTIVITY_VIEW,
            PEOPLE_FILTERS,
        ),
        ReportTypeInfo(
            ReportType.APPLICATIONS,
            "Applications",
            "Time per person and application, with its category and the rule that decided it.",
            Permission.ACTIVITY_VIEW,
            PEOPLE_FILTERS,
        ),
        ReportTypeInfo(
            ReportType.WEBSITES,
            "Websites",
            "Time per person and website domain (when website tracking is on), with its category.",
            Permission.ACTIVITY_VIEW,
            PEOPLE_FILTERS,
        ),
        ReportTypeInfo(
            ReportType.SCREENSHOTS,
            "Screenshots",
            "When screenshots were captured, for whom and on which device. Images are never exported.",
            Permission.SCREENSHOT_VIEW,
            PEOPLE_FILTERS,
        ),
        ReportTypeInfo(
            ReportType.PROJECTS,
            "Projects",
            "Per project: tasks, progress, overdue work and time logged in the period.",
            None,
            ("project", *PEOPLE_FILTERS),
        ),
        ReportTypeInfo(
            ReportType.TASKS,
            "Tasks",
            "Tasks created, due, completed or worked on in the period, with time logged.",
            None,
            ("project", *PEOPLE_FILTERS),
        ),
        ReportTypeInfo(
            ReportType.PRODUCTIVITY,
            "Productivity",
            "Per person: measurements and every score (activity, productive share, focus, utilization, tasks).",
            Permission.ACTIVITY_VIEW,
            PEOPLE_FILTERS,
        ),
        ReportTypeInfo(
            ReportType.LIVE_SESSIONS,
            "Live sessions",
            "Who viewed whose screen live, on which device, when and for how long.",
            Permission.LIVE_STREAM_VIEW,
            PEOPLE_FILTERS,
        ),
    )
}

LIVE_OUTCOME = {
    "viewer_stopped": "Stopped by viewer",
    "viewer_disconnected": "Viewer disconnected",
    "agent_disconnected": "Employee went offline",
    "connection_lost": "Connection lost",
    "connect_timeout": "Never connected (timeout)",
    "max_duration": "Reached time limit",
    "work_session_stopped": "Work session ended",
    "live_view_disabled": "Live viewing turned off",
    "agent_stopped": "Agent closed",
    "agent_error": "Agent error",
    "capture_failed": "Screen capture failed",
    "server_shutdown": "Server restarted",
    "server_restart": "Server restarted",
}


@dataclass
class ReportContext:
    """Everything a builder needs, already restricted to what the requester may see."""

    principal: Principal
    company: Company
    tz: ZoneInfo
    start: date
    end: date
    filters: ReportFilters
    employees: list[Employee]
    departments: dict[ObjectId, Any]
    teams: dict[ObjectId, Any]
    profiles: dict[ObjectId, Any]
    repos: ReportRepos
    productivity: ProductivityService
    work: WorkService
    notes: list[str] = field(default_factory=list)

    @property
    def lo(self) -> datetime:
        return datetime.combine(self.start, datetime.min.time(), tzinfo=self.tz)

    @property
    def hi(self) -> datetime:
        return datetime.combine(self.end + timedelta(days=1), datetime.min.time(), tzinfo=self.tz)

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    @property
    def ids(self) -> list[ObjectId]:
        return [e.id for e in self.employees]

    def person(self, e: Employee) -> dict[str, Any]:
        dept = self.departments.get(e.department_id) if e.department_id else None
        team = self.teams.get(e.team_id) if e.team_id else None
        return {
            "employee": e.full_name,
            "employee_code": e.employee_code or "",
            "department": dept.name if dept else "",
            "team": team.name if team else "",
        }


@dataclass
class ReportRepos:
    employees: EmployeeRepository
    departments: DepartmentRepository
    teams: TeamRepository
    users: UserRepository
    profiles: WorkProfileRepository
    sessions: WorkSessionRepository
    screenshots: ScreenshotRepository
    devices: DeviceRepository
    live: LiveSessionRepository
    projects: ProjectRepository
    tasks: TaskRepository
    milestones: MilestoneRepository
    time_entries: TimeEntryRepository
    scopes: AccessScopeService


PERSON_COLUMNS = [
    Column("employee", "Employee"),
    Column("employee_code", "Employee code"),
    Column("department", "Department"),
    Column("team", "Team"),
]


async def resolve_employees(
    repos: ReportRepos, principal: Principal, filters: ReportFilters
) -> list[Employee]:
    """People in the requester's access scope, narrowed by the report's filters. Sorted by name."""
    scope = await repos.scopes.employee_scope(principal)
    clauses: list[dict[str, Any]] = [{"status": {"$ne": EmployeeStatus.TERMINATED}}]
    if scope.filter:
        clauses.append(scope.filter)
    if filters.employee_ids:
        clauses.append({"_id": {"$in": list(filters.employee_ids)}})
    if filters.department_id:
        clauses.append({"department_id": filters.department_id})
    if filters.team_id:
        clauses.append({"team_id": filters.team_id})
    if filters.work_profile_id:
        clauses.append({"work_profile_id": filters.work_profile_id})
    ids = await repos.employees.ids_matching(principal.company_id, {"$and": clauses})
    people = list((await repos.employees.find_by_ids(principal.company_id, ids)).values())
    if filters.role:
        users = await repos.users.find_by_ids(principal.company_id, [e.user_id for e in people if e.user_id])
        people = [e for e in people if e.user_id in users and users[e.user_id].role.value == filters.role]
    return sorted(people, key=lambda e: e.full_name.lower())


def _day(value: datetime | None) -> date | None:
    """Stored calendar dates (due, start) are midnight UTC."""
    local = _local(value, UTC)
    return local.date() if local else None


def _local(value: datetime | None, tz: tzinfo) -> datetime | None:
    if value is None:
        return None
    return (value if value.tzinfo else value.replace(tzinfo=UTC)).astimezone(tz)


async def _metrics(ctx: ReportContext, *, segments: bool) -> dict[ObjectId, Any]:
    use_segments = segments and ctx.days <= SEGMENT_LIMIT_DAYS
    if segments and not use_segments:
        ctx.notes.append(
            f"Focus sessions and application switching are analysed for ranges of up to {SEGMENT_LIMIT_DAYS} days; "
            "they are left empty in this report."
        )
    return await ctx.productivity.compute(
        ctx.company, ctx.employees, ctx.start, ctx.end, with_segments=use_segments
    )


# --------------------------------------------------------------------------- builders
async def attendance(ctx: ReportContext) -> ReportData:
    data = await _metrics(ctx, segments=False)
    sessions = await ctx.repos.sessions.overlapping(ctx.company.id, ctx.ids, ctx.lo, ctx.hi)
    now = utcnow().astimezone(ctx.tz)
    first: dict[tuple[ObjectId, date], datetime] = {}
    last: dict[tuple[ObjectId, date], datetime] = {}
    ongoing: set[tuple[ObjectId, date]] = set()
    unknown_end: set[tuple[ObjectId, date]] = set()
    count: dict[tuple[ObjectId, date], int] = defaultdict(int)
    for s in sessions:
        start = _local(s.started_at, ctx.tz)
        end = _local(s.ended_at, ctx.tz)
        assert start is not None
        day = start.date()
        while day <= (end or now).date():
            key = (s.employee_id, day)
            day_lo = datetime.combine(day, datetime.min.time(), tzinfo=ctx.tz)
            day_hi = day_lo + timedelta(days=1)
            if ctx.start <= day <= ctx.end:
                count[key] += 1
                first[key] = min(first.get(key, day_hi), max(start, day_lo))
                if end is not None:
                    last[key] = max(last.get(key, day_lo), min(end, day_hi))
                elif day == now.date():
                    ongoing.add(key)  # still open today
                else:
                    unknown_end.add(key)  # never closed (e.g. the agent stopped without saying so)
            day += timedelta(days=1)
    rows = []
    for e in ctx.employees:
        days = data[e.id].days
        for offset in range(ctx.days):
            day = ctx.start + timedelta(days=offset)
            m = days.get(day, Metrics())
            key = (e.id, day)
            worked = key in count
            rows.append(
                {
                    "date": day,
                    "weekday": day.strftime("%A"),
                    **ctx.person(e),
                    "status": "Worked" if worked else "No work session",
                    "first_start": first.get(key),
                    "last_end": None if key in ongoing or key in unknown_end else last.get(key),
                    "ongoing": "Yes" if key in ongoing else "",
                    "work_seconds": m.work,
                    "sessions": count.get((e.id, day), 0),
                }
            )
    ctx.notes.append(
        "Attendance is derived from desktop-agent work sessions (first start and last end per day). Leave, "
        "holidays and shifts are not part of WorkPulse yet, so 'No work session' does not mean absence. A session "
        "that was never closed (for example when the computer was switched off) has no last end; its work time "
        "ends at the device's last contact."
    )
    return ReportData(
        "Attendance",
        [
            Column("date", "Date", "date"),
            Column("weekday", "Weekday"),
            *PERSON_COLUMNS,
            Column("status", "Status"),
            Column("first_start", "First start", "time"),
            Column("last_end", "Last end", "time"),
            Column("ongoing", "Still working"),
            Column("work_seconds", "Work time", "duration"),
            Column("sessions", "Sessions", "int"),
        ],
        rows,
    )


async def work_hours(ctx: ReportContext) -> ReportData:
    data = await _metrics(ctx, segments=False)
    rows = []
    for e in ctx.employees:
        for day, m in sorted(data[e.id].days.items()):
            if m.work <= 0:
                continue
            rows.append(
                {
                    "date": day,
                    **ctx.person(e),
                    "work_seconds": m.work,
                    "active_seconds": m.active,
                    "idle_seconds": m.idle,
                    "extended_idle_seconds": m.extended_idle,
                    "away_seconds": m.away,
                    "activity_score": activity_score(m)["value"],
                }
            )
    ctx.notes.append(
        "Only days with recorded work are listed. Activity score = active ÷ work time; it is input-based."
    )
    return ReportData(
        "Work hours",
        [
            Column("date", "Date", "date"),
            *PERSON_COLUMNS,
            Column("work_seconds", "Work", "duration"),
            Column("active_seconds", "Active", "duration"),
            Column("idle_seconds", "Idle", "duration"),
            Column("extended_idle_seconds", "Extended idle", "duration"),
            Column("away_seconds", "Away", "duration"),
            Column("activity_score", "Activity score", "percent"),
        ],
        rows,
    )


def _total(days: dict[date, Metrics]) -> Metrics:
    total = Metrics()
    for m in days.values():
        total.add(m)
    return total


async def activity(ctx: ReportContext) -> ReportData:
    data = await _metrics(ctx, segments=True)
    segments = ctx.days <= SEGMENT_LIMIT_DAYS
    rows = []
    for e in ctx.employees:
        d = data[e.id]
        t = _total(d.days)
        rows.append(
            {
                **ctx.person(e),
                "days_worked": sum(1 for m in d.days.values() if m.work > 0),
                "work_seconds": t.work,
                "active_seconds": t.active,
                "idle_seconds": t.idle,
                "extended_idle_seconds": t.extended_idle,
                "activity_score": activity_score(t)["value"],
                "focus_sessions": t.focus_count if segments else None,
                "focus_seconds": t.focus_seconds if segments else None,
                "context_switches": t.context_switches if segments else None,
            }
        )
    ctx.notes.append(
        "Activity score = active ÷ work time × 100. It measures input, not productivity or quality."  # noqa: RUF001
    )
    return ReportData(
        "Activity",
        [
            *PERSON_COLUMNS,
            Column("days_worked", "Days worked", "int"),
            Column("work_seconds", "Work", "duration"),
            Column("active_seconds", "Active", "duration"),
            Column("idle_seconds", "Idle", "duration"),
            Column("extended_idle_seconds", "Extended idle", "duration"),
            Column("activity_score", "Activity score", "percent"),
            Column("focus_sessions", "Focus sessions", "int"),
            Column("focus_seconds", "Focus time", "duration"),
            Column("context_switches", "App switches", "int"),
        ],
        rows,
    )


async def _usage(ctx: ReportContext, kind: str) -> list[dict[str, Any]]:
    data = await _metrics(ctx, segments=False)
    rows = []
    for e in ctx.employees:
        items = [i for i in data[e.id].items.values() if i.kind == kind and i.seconds >= 1]
        for i in sorted(items, key=lambda i: -i.seconds):
            rows.append(
                {
                    **ctx.person(e),
                    "name": i.name,
                    "key": i.key,
                    "seconds": i.seconds,
                    "category": i.category.title(),
                    "decided_by": (i.rule_scope or "").replace("_", " ").title() or "No rule",
                }
            )
    return rows


async def applications(ctx: ReportContext) -> ReportData:
    rows = await _usage(ctx, "app")
    ctx.notes.append("Only the application is recorded — never window contents, keystrokes or screen text.")
    return ReportData(
        "Applications",
        [
            *PERSON_COLUMNS,
            Column("name", "Application"),
            Column("key", "Executable"),
            Column("seconds", "Time", "duration"),
            Column("category", "Category"),
            Column("decided_by", "Rule scope"),
        ],
        rows,
    )


async def websites(ctx: ReportContext) -> ReportData:
    rows = await _usage(ctx, "website")
    if not ctx.company.activity_policy.track_websites:
        ctx.notes.append("Website tracking is turned off for this workspace, so this report may be empty.")
    ctx.notes.append("Only domain names are recorded — never full addresses, page titles or content.")
    return ReportData(
        "Websites",
        [
            *PERSON_COLUMNS,
            Column("key", "Domain"),
            Column("name", "Browser"),
            Column("seconds", "Time", "duration"),
            Column("category", "Category"),
            Column("decided_by", "Rule scope"),
        ],
        rows,
    )


async def screenshots(ctx: ReportContext) -> ReportData:
    shots = await ctx.repos.screenshots.in_range(ctx.company.id, ctx.ids, ctx.lo, ctx.hi, MAX_LIST_ROWS)
    devices = await ctx.repos.devices.find_by_ids(ctx.company.id, list({s.device_id for s in shots}))
    people = {e.id: e for e in ctx.employees}
    rows = [
        {
            "captured_at": _local(s.captured_at, ctx.tz),
            **ctx.person(people[s.employee_id]),
            "device": devices[s.device_id].name if s.device_id in devices else "",
            "resolution": f"{s.width} × {s.height}",  # noqa: RUF001
            "size_kb": round(s.size_bytes / 1024),
            "retained_until": _local(s.expires_at, ctx.tz),
        }
        for s in shots
        if s.employee_id in people
    ]
    ctx.notes.append(
        "Screenshot images are never included in exports; view them in WorkPulse (access is audited)."
    )
    return ReportData(
        "Screenshots",
        [
            Column("captured_at", "Captured", "datetime"),
            *PERSON_COLUMNS,
            Column("device", "Device"),
            Column("resolution", "Resolution"),
            Column("size_kb", "Size (KB)", "int"),
            Column("retained_until", "Deleted after", "datetime"),
        ],
        rows,
    )


async def _visible_projects(ctx: ReportContext) -> dict[ObjectId, Any]:
    access = await ctx.work.access(ctx.principal)
    query: dict[str, Any] = dict(access.project_query() or {})
    if ctx.filters.project_id:
        query["_id"] = ctx.filters.project_id
    projects = await ctx.repos.projects.visible(ctx.company.id, query)
    return {p.id: p for p in projects}


async def _time_in_range(ctx: ReportContext) -> list[Any]:
    entries = await ctx.repos.time_entries.overlapping(ctx.company.id, ctx.ids, ctx.lo, ctx.hi)
    return entries


def _clip(entry: Any, ctx: ReportContext) -> float:
    start = max(_local(entry.started_at, ctx.tz) or ctx.lo, ctx.lo)
    end = min(_local(entry.ended_at, ctx.tz) or utcnow().astimezone(ctx.tz), ctx.hi)
    return max(0.0, (end - start).total_seconds())


def _people_filtered(ctx: ReportContext) -> bool:
    f = ctx.filters
    return bool(f.employee_ids or f.department_id or f.team_id or f.role or f.work_profile_id)


async def projects(ctx: ReportContext) -> ReportData:
    visible = await _visible_projects(ctx)
    ids = set(ctx.ids)
    if _people_filtered(ctx):
        visible = {k: p for k, p in visible.items() if ids & set(p.member_ids)}
    counts = await ctx.repos.tasks.counts_by_project(ctx.company.id, list(visible))
    tasks = await ctx.repos.tasks.query(
        ctx.company.id, {"project_id": {"$in": list(visible)}, "parent_id": None}, limit=MAX_LIST_ROWS
    )
    today = utcnow().astimezone(ctx.tz).date()
    overdue: dict[ObjectId, int] = defaultdict(int)
    completed_in: dict[ObjectId, int] = defaultdict(int)
    for t in tasks:
        due_day = _day(t.due_date)
        if t.status != TaskStatus.COMPLETED and due_day and due_day < today:
            overdue[t.project_id] += 1
        finished = _local(t.completed_at, ctx.tz)
        if finished and ctx.start <= finished.date() <= ctx.end:
            completed_in[t.project_id] += 1
    seconds: dict[ObjectId, float] = defaultdict(float)
    for entry in await _time_in_range(ctx):
        seconds[entry.project_id] += _clip(entry, ctx)
    owners = await ctx.repos.employees.find_by_ids(
        ctx.company.id, [p.owner_employee_id for p in visible.values() if p.owner_employee_id]
    )
    rows = []
    for pid, p in sorted(visible.items(), key=lambda kv: kv[1].name.lower()):
        c = counts.get(pid, {})
        total = sum(v for k, v in c.items() if k != "time_spent_seconds")
        done = c.get(TaskStatus.COMPLETED.value, 0)
        rows.append(
            {
                "project": p.name,
                "key": p.key,
                "status": "Archived" if p.status == ProjectStatus.ARCHIVED else "Active",
                "owner": owners[p.owner_employee_id].full_name if p.owner_employee_id in owners else "",
                "members": len(p.member_ids),
                "tasks": total,
                "completed": done,
                "open": total - done,
                "overdue": overdue.get(pid, 0),
                "progress": round(100 * done / total) if total else None,
                "completed_in_period": completed_in.get(pid, 0),
                "time_in_period": seconds.get(pid, 0.0),
                "due_date": _day(p.due_date),
            }
        )
    ctx.notes.append("Time in period counts time logged by the people in this report's scope.")
    return ReportData(
        "Projects",
        [
            Column("project", "Project"),
            Column("key", "Key"),
            Column("status", "Status"),
            Column("owner", "Owner"),
            Column("members", "Members", "int"),
            Column("tasks", "Tasks", "int"),
            Column("completed", "Completed", "int"),
            Column("open", "Open", "int"),
            Column("overdue", "Overdue", "int"),
            Column("progress", "Progress", "percent"),
            Column("completed_in_period", "Completed in period", "int"),
            Column("time_in_period", "Time logged in period", "duration"),
            Column("due_date", "Due date", "date"),
        ],
        rows,
    )


async def tasks(ctx: ReportContext) -> ReportData:
    visible = await _visible_projects(ctx)
    lo_utc, hi_utc = ctx.lo.astimezone(UTC), ctx.hi.astimezone(UTC)
    seconds: dict[ObjectId, float] = defaultdict(float)
    for entry in await _time_in_range(ctx):
        seconds[entry.task_id] += _clip(entry, ctx)
    clauses: list[dict[str, Any]] = [
        {"created_at": {"$gte": lo_utc, "$lt": hi_utc}},
        {"completed_at": {"$gte": lo_utc, "$lt": hi_utc}},
        {
            "due_date": {
                "$gte": datetime.combine(ctx.start, datetime.min.time(), tzinfo=UTC),
                "$lte": datetime.combine(ctx.end, datetime.min.time(), tzinfo=UTC),
            }
        },
        {"_id": {"$in": list(seconds)}},
    ]
    query: dict[str, Any] = {"project_id": {"$in": list(visible)}, "$or": clauses}
    if _people_filtered(ctx):
        query["assignee_ids"] = {"$in": ctx.ids}
    found = await ctx.repos.tasks.query(
        ctx.company.id, query, limit=MAX_LIST_ROWS, sort=[("project_id", 1), ("number", 1)]
    )
    people = await ctx.repos.employees.find_by_ids(
        ctx.company.id, list({a for t in found for a in t.assignee_ids})
    )
    milestones = await ctx.repos.milestones.find_by_ids(
        ctx.company.id, [t.milestone_id for t in found if t.milestone_id]
    )
    today = utcnow().astimezone(ctx.tz).date()
    rows = []
    for t in found:
        p = visible[t.project_id]
        due = _day(t.due_date)
        rows.append(
            {
                "reference": f"{p.key}-{t.number}",
                "title": t.title,
                "project": p.name,
                "type": "Subtask" if t.parent_id else "Task",
                "status": t.status.value.replace("_", " ").title(),
                "priority": t.priority.value.title(),
                "assignees": ", ".join(people[a].full_name for a in t.assignee_ids if a in people),
                "labels": ", ".join(t.labels),
                "milestone": milestones[t.milestone_id].name if t.milestone_id in milestones else "",
                "start_date": _day(t.start_date),
                "due_date": due,
                "completed_at": _local(t.completed_at, ctx.tz),
                "overdue": "Yes" if due and due < today and t.status != TaskStatus.COMPLETED else "",
                "time_in_period": seconds.get(t.id, 0.0),
                "time_total": float(t.time_spent_seconds),
            }
        )
    ctx.notes.append("Tasks created, due, completed or worked on in the period, in projects you can see.")
    return ReportData(
        "Tasks",
        [
            Column("reference", "Reference"),
            Column("title", "Title"),
            Column("project", "Project"),
            Column("type", "Type"),
            Column("status", "Status"),
            Column("priority", "Priority"),
            Column("assignees", "Assignees"),
            Column("labels", "Labels"),
            Column("milestone", "Milestone"),
            Column("start_date", "Start", "date"),
            Column("due_date", "Due", "date"),
            Column("completed_at", "Completed", "datetime"),
            Column("overdue", "Overdue"),
            Column("time_in_period", "Time in period", "duration"),
            Column("time_total", "Time total", "duration"),
        ],
        rows,
    )


async def productivity(ctx: ReportContext) -> ReportData:
    data = await _metrics(ctx, segments=True)
    segments = ctx.days <= SEGMENT_LIMIT_DAYS
    rows = []
    for e in ctx.employees:
        t = _total(data[e.id].days)
        profile = ctx.profiles.get(e.work_profile_id) if e.work_profile_id else None
        rows.append(
            {
                **ctx.person(e),
                "work_profile": profile.name if profile else "",
                "work_seconds": t.work,
                "active_seconds": t.active,
                "productive_seconds": t.productive,
                "neutral_seconds": t.neutral,
                "unproductive_seconds": t.unproductive,
                "unclassified_seconds": t.unclassified,
                "focus_seconds": t.focus_seconds if segments else None,
                "task_seconds": t.task_seconds,
                "activity_score": activity_score(t)["value"],
                "productive_share": productive_share(t)["value"],
                "focus_score": focus_score(t)["value"] if segments else None,
                "work_utilization": work_utilization(t)["value"],
                "task_completion": task_completion(t)["value"],
            }
        )
    ctx.notes.extend(
        [
            "Activity score = active ÷ work time. Productive share = productive ÷ classified app and website time. "
            "Focus score = focus-session time ÷ productive time. Work utilization = time on tasks ÷ work time. "
            "Task completion = completed ÷ (completed + open tasks that were due).",
            "These figures describe recorded computer activity under your workspace's rules. They are context for a "
            "conversation, not a measure of anyone's performance. Rows are sorted by name, not ranked.",
        ]
    )
    return ReportData(
        "Productivity",
        [
            *PERSON_COLUMNS,
            Column("work_profile", "Work profile"),
            Column("work_seconds", "Work", "duration"),
            Column("active_seconds", "Active", "duration"),
            Column("productive_seconds", "Productive", "duration"),
            Column("neutral_seconds", "Neutral", "duration"),
            Column("unproductive_seconds", "Unproductive", "duration"),
            Column("unclassified_seconds", "Unclassified", "duration"),
            Column("focus_seconds", "Focus time", "duration"),
            Column("task_seconds", "Task time", "duration"),
            Column("activity_score", "Activity score", "percent"),
            Column("productive_share", "Productive share", "percent"),
            Column("focus_score", "Focus score", "percent"),
            Column("work_utilization", "Work utilization", "percent"),
            Column("task_completion", "Task completion", "percent"),
        ],
        rows,
    )


async def live_sessions(ctx: ReportContext) -> ReportData:
    sessions = await ctx.repos.live.in_range(ctx.company.id, ctx.ids, ctx.lo, ctx.hi, MAX_LIST_ROWS)
    devices = await ctx.repos.devices.find_by_ids(ctx.company.id, list({s.device_id for s in sessions}))
    people = {e.id: e for e in ctx.employees}
    rows = [
        {
            "session_id": str(s.id),
            **ctx.person(people[s.employee_id]),
            "device": devices[s.device_id].name if s.device_id in devices else "",
            "viewer": s.viewer_name,
            "requested_at": _local(s.created_at, ctx.tz),
            "connected_at": _local(s.connected_at, ctx.tz),
            "ended_at": _local(s.ended_at, ctx.tz),
            "watched": float(s.duration_seconds) if s.duration_seconds is not None else None,
            "outcome": LIVE_OUTCOME.get(
                s.end_reason or "", (s.end_reason or s.status.value).replace("_", " ")
            ),
            "reconnects": s.reconnects,
        }
        for s in sessions
        if s.employee_id in people
    ]
    ctx.notes.append("Live sessions are never recorded; this is the access log only.")
    return ReportData(
        "Live sessions",
        [
            Column("session_id", "Session ID"),
            *PERSON_COLUMNS,
            Column("device", "Device"),
            Column("viewer", "Viewer"),
            Column("requested_at", "Requested", "datetime"),
            Column("connected_at", "Connected", "datetime"),
            Column("ended_at", "Ended", "datetime"),
            Column("watched", "Watched", "duration"),
            Column("outcome", "Outcome"),
            Column("reconnects", "Reconnects", "int"),
        ],
        rows,
    )


BUILDERS: dict[ReportType, Callable[[ReportContext], Awaitable[ReportData]]] = {
    ReportType.ATTENDANCE: attendance,
    ReportType.WORK_HOURS: work_hours,
    ReportType.ACTIVITY: activity,
    ReportType.APPLICATIONS: applications,
    ReportType.WEBSITES: websites,
    ReportType.SCREENSHOTS: screenshots,
    ReportType.PROJECTS: projects,
    ReportType.TASKS: tasks,
    ReportType.PRODUCTIVITY: productivity,
    ReportType.LIVE_SESSIONS: live_sessions,
}
