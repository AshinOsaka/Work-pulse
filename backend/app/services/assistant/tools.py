"""The assistant's tools: read-only questions to WorkPulse's own services, answered for one requester.

Every tool runs *as the person asking*: the same services, permissions and access scope as the web app, so the
assistant can never see more than they can. Each returns two things:

* `facts` - a compact JSON payload for the model: the period, the numbers, where they came from and a link. The model
  may only state what is in these payloads (see the system prompt).
* `cards` - structured data the UI renders directly (metrics, tables, charts, links). Numbers in cards come straight
  from the services, never from model text.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

from bson import ObjectId
from pydantic import BaseModel, Field, ValidationError

from app.auth.permissions import Permission
from app.auth.principal import Principal
from app.core.exceptions import AppError
from app.models.organization import Employee, EmployeeStatus
from app.models.report import ReportFilters, ReportType
from app.repositories.company import CompanyRepository
from app.repositories.notification import NotificationRepository
from app.repositories.organization import DepartmentRepository, EmployeeRepository, TeamRepository
from app.services.access_scope import AccessScopeService
from app.services.activity_feed_service import ActivityFeedService
from app.services.presence_service import PresenceService
from app.services.productivity.service import ProductivityService
from app.services.reports.service import ReportEngine
from app.services.work.service import WorkService
from app.utils.time import utcnow

PeriodKey = Literal[
    "today",
    "yesterday",
    "this_week",
    "last_week",
    "last_7_days",
    "this_month",
    "last_month",
    "last_30_days",
    "custom",
]
MAX_DAYS = 31


class ToolError(Exception):
    """A failure the model should see and explain (permission, unknown name, bad period)."""


# --------------------------------------------------------------------------- inputs
class PeriodInput(BaseModel, extra="forbid"):
    period: PeriodKey = "today"
    start: date | None = None
    end: date | None = None


class GroupInput(PeriodInput):
    team_name: str | None = Field(default=None, max_length=80)
    department_name: str | None = Field(default=None, max_length=80)


class ProjectTimeInput(PeriodInput):
    project: str = Field(min_length=1, max_length=80)


class OverdueInput(BaseModel, extra="forbid"):
    project: str | None = Field(default=None, max_length=80)
    assignee_name: str | None = Field(default=None, max_length=80)


class PeopleInput(BaseModel, extra="forbid"):
    query: str = Field(min_length=1, max_length=80)


class EmployeeInput(PeriodInput):
    employee_name: str = Field(min_length=1, max_length=80)


class EmptyInput(BaseModel, extra="forbid"):
    pass


_PERIOD_SCHEMA = {
    "period": {
        "type": "string",
        "enum": list(PeriodKey.__args__),  # type: ignore[attr-defined]
        "description": "Calendar period in the workspace time zone. Weeks start on Monday. Use custom with start/end.",
    },
    "start": {"type": "string", "format": "date", "description": "YYYY-MM-DD, only with period=custom"},
    "end": {"type": "string", "format": "date", "description": "YYYY-MM-DD, only with period=custom"},
}
_GROUP_SCHEMA = {
    **_PERIOD_SCHEMA,
    "team_name": {"type": "string", "description": "Optional team name to narrow to"},
    "department_name": {"type": "string", "description": "Optional department name to narrow to"},
}


def _tool(
    name: str, description: str, properties: dict[str, Any], required: list[str] | None = None
) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "input_schema": {
            "type": "object",
            "properties": properties,
            "required": required or [],
            "additionalProperties": False,
        },
        # Inputs stream as generated; they are validated before any tool runs.
        "eager_input_streaming": True,
    }


#: Fixed order and content: the tool list is part of the cached, conversation-bound prefix.
TOOL_DEFINITIONS: list[dict[str, Any]] = [
    _tool(
        "get_live_presence",
        "Who is working right now: counts of online, active, idle and offline people, with names. Source: desktop "
        "agent heartbeats. Use for 'how many are active now', 'who is online'.",
        {},
    ),
    _tool(
        "get_team_activity",
        "Recorded work signals for a period: work, active, idle time, time by application category, focus, tasks, "
        "and the derived scores with their formulas, plus hours per day. Optionally for one team or department.",
        _GROUP_SCHEMA,
    ),
    _tool(
        "get_project_time",
        "Time logged on a project's tasks in a period (timers and manual entries), per person, with task counts and "
        "progress. Matches the project by name or key.",
        {**_PERIOD_SCHEMA, "project": {"type": "string", "description": "Project name or key"}},
        ["project"],
    ),
    _tool(
        "list_overdue_tasks",
        "Open tasks past their due date in projects the person can see, optionally for one project or assignee.",
        {
            "project": {"type": "string", "description": "Optional project name or key"},
            "assignee_name": {"type": "string", "description": "Optional person's name"},
        },
    ),
    _tool(
        "get_attendance_summary",
        "Per person for a period: days with work sessions, total hours, typical first start and last end. Derived "
        "from desktop-agent work sessions (WorkPulse has no leave or shift records).",
        _GROUP_SCHEMA,
    ),
    _tool(
        "get_recent_events",
        "What happened in a period: organisation changes and work events from the audit trail, plus the person's "
        "own alerts (offline devices, overdue work, live views, policy changes).",
        _PERIOD_SCHEMA,
    ),
    _tool(
        "find_people",
        "Find employees the person can see by (part of) a name; returns job title, team and department.",
        {"query": {"type": "string"}},
        ["query"],
    ),
    _tool(
        "get_employee_summary",
        "One person's recorded work signals for a period: measurements, scores with formulas, and project time.",
        {**_PERIOD_SCHEMA, "employee_name": {"type": "string"}},
        ["employee_name"],
    ),
    _tool(
        "list_projects",
        "Active projects the person can see, with progress, open and overdue task counts and due dates.",
        {},
    ),
]

INPUT_MODELS: dict[str, type[BaseModel]] = {
    "get_live_presence": EmptyInput,
    "get_team_activity": GroupInput,
    "get_project_time": ProjectTimeInput,
    "list_overdue_tasks": OverdueInput,
    "get_attendance_summary": GroupInput,
    "get_recent_events": PeriodInput,
    "find_people": PeopleInput,
    "get_employee_summary": EmployeeInput,
    "list_projects": EmptyInput,
}

TOOL_LABELS = {
    "get_live_presence": "Checking who is online",
    "get_team_activity": "Reading activity",
    "get_project_time": "Reading project time",
    "list_overdue_tasks": "Finding overdue tasks",
    "get_attendance_summary": "Reading attendance",
    "get_recent_events": "Reading recent events",
    "find_people": "Looking up people",
    "get_employee_summary": "Reading a person's summary",
    "list_projects": "Listing projects",
}


# --------------------------------------------------------------------------- helpers
@dataclass
class ToolResult:
    facts: dict[str, Any]
    cards: list[dict[str, Any]] = field(default_factory=list)


def hours(seconds: float) -> float:
    return round(seconds / 3600, 1)


def fmt(seconds: float) -> str:
    minutes = round(seconds / 60)
    h, m = divmod(minutes, 60)
    return f"{h}h {m:02d}m" if h else f"{minutes}m"


@dataclass(frozen=True)
class Period:
    key: str
    start: date
    end: date

    @property
    def label(self) -> str:
        if self.start == self.end:
            return self.start.strftime("%a %d %b %Y")
        return f"{self.start.strftime('%d %b')} - {self.end.strftime('%d %b %Y')}"

    def as_dict(self) -> dict[str, str]:
        return {
            "key": self.key,
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "label": self.label,
        }


def resolve_period(p: PeriodInput, today: date, max_days: int = MAX_DAYS) -> Period:
    monday = today - timedelta(days=today.weekday())
    first = today.replace(day=1)
    if p.period == "today":
        start = end = today
    elif p.period == "yesterday":
        start = end = today - timedelta(days=1)
    elif p.period == "this_week":
        start, end = monday, today
    elif p.period == "last_week":
        start, end = monday - timedelta(days=7), monday - timedelta(days=1)
    elif p.period == "last_7_days":
        start, end = today - timedelta(days=6), today
    elif p.period == "this_month":
        start, end = first, today
    elif p.period == "last_month":
        end = first - timedelta(days=1)
        start = end.replace(day=1)
    elif p.period == "last_30_days":
        start, end = today - timedelta(days=29), today
    else:
        if not p.start or not p.end:
            raise ToolError("A custom period needs both start and end dates.")
        start, end = p.start, p.end
    if end < start:
        raise ToolError("The end date is before the start date.")
    if (end - start).days >= max_days:
        raise ToolError(f"Choose a period of at most {max_days} days.")
    return Period(p.period, start, end)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


@dataclass
class AssistantServices:
    companies: CompanyRepository
    employees: EmployeeRepository
    departments: DepartmentRepository
    teams: TeamRepository
    scopes: AccessScopeService
    presence: PresenceService
    feed: ActivityFeedService
    productivity: ProductivityService
    work: WorkService
    reports: ReportEngine
    notifications: NotificationRepository


class AssistantTools:
    def __init__(self, services: AssistantServices, principal: Principal) -> None:
        self.s = services
        self.p = principal
        self._tz: ZoneInfo | None = None

    async def tz(self) -> ZoneInfo:
        if self._tz is None:
            company = await self.s.companies.get_by_id(self.p.company_id)
            self._tz = ZoneInfo(company.timezone if company else "UTC")
        return self._tz

    async def today(self) -> date:
        return utcnow().astimezone(await self.tz()).date()

    def _need(self, permission: Permission, what: str) -> None:
        if not self.p.has(permission):
            raise ToolError(f"You don't have permission to see {what}.")

    async def _visible_people(self) -> list[Employee]:
        scope = await self.s.scopes.employee_scope(self.p)
        clauses: list[dict[str, Any]] = [{"status": {"$ne": EmployeeStatus.TERMINATED}}]
        if scope.filter:
            clauses.append(scope.filter)
        ids = await self.s.employees.ids_matching(self.p.company_id, {"$and": clauses})
        return list((await self.s.employees.find_by_ids(self.p.company_id, ids)).values())

    async def _person(self, name: str) -> Employee:
        wanted = _norm(name)
        people = await self._visible_people()
        exact = [e for e in people if _norm(e.full_name) == wanted]
        partial = exact or [e for e in people if wanted in _norm(e.full_name)]
        if not partial:
            raise ToolError(f"No one called “{name}” among the people you can see.")
        if len(partial) > 1:
            raise ToolError(
                "Several people match: "
                + ", ".join(sorted(e.full_name for e in partial)[:8])
                + ". Ask which one."
            )
        return partial[0]

    async def _group(self, data: GroupInput) -> tuple[dict[str, str], str]:
        """Resolve team / department names to ids (and a label)."""
        out: dict[str, str] = {}
        labels = []
        for kind, raw, repo in (
            ("team_id", data.team_name, self.s.teams),
            ("department_id", data.department_name, self.s.departments),
        ):
            if not raw:
                continue
            items = await repo.find_many(self.p.company_id, {}, sort=None, limit=1000)
            match = [i for i in items if _norm(i.name) == _norm(raw)] or [
                i for i in items if _norm(raw) in _norm(i.name)
            ]
            if not match:
                raise ToolError(f"No {kind.split('_')[0]} called “{raw}”.")
            out[kind] = str(match[0].id)
            labels.append(match[0].name)
        return out, " / ".join(labels) or "everyone you can see"

    async def _project(self, query: str) -> Any:
        projects = await self.s.work.list_projects(self.p, include_archived=True)
        q = _norm(query)
        exact = [p for p in projects if _norm(p.name) == q or p.key.lower() == q]
        found = exact or [p for p in projects if q in _norm(p.name)]
        if not found:
            names = ", ".join(p.name for p in projects[:10])
            raise ToolError(f"No project matching “{query}” that you can see. Projects: {names or 'none'}.")
        if len(found) > 1:
            raise ToolError(
                "Several projects match: " + ", ".join(p.name for p in found[:8]) + ". Ask which one."
            )
        return found[0]

    # ------------------------------------------------------------------ tools
    async def run(self, name: str, raw: Any) -> ToolResult:
        handler = getattr(self, f"_t_{name}", None)
        if handler is None:
            raise ToolError(f"Unknown tool {name}.")
        model = INPUT_MODELS[name]
        try:
            data = model.model_validate(raw if isinstance(raw, dict) else {})
        except ValidationError as exc:
            raise ToolError(f"Invalid input: {exc.errors()[0]['msg']}") from exc
        try:
            result: ToolResult = await handler(data)
        except AppError as exc:  # permission / not found from the services, said plainly
            raise ToolError(exc.message) from exc
        return result

    async def _t_get_live_presence(self, _: EmptyInput) -> ToolResult:
        self._need(Permission.ACTIVITY_VIEW, "live presence")
        o = await self.s.presence.overview(self.p, None)
        working = [e for e in o.employees if e.status in ("active", "idle")]
        rows = [
            {
                "employee": e.employee.full_name,
                "status": e.status.title(),
                "since": (e.since.astimezone(await self.tz()).strftime("%H:%M") if e.since else ""),
                "application": e.current_app or "",
            }
            for e in sorted(working, key=lambda e: e.employee.full_name)[:40]
        ]
        facts = {
            "as_of": o.as_of.astimezone(await self.tz()).isoformat(timespec="minutes"),
            "counts": o.counts.model_dump(),
            "working_now": rows,
            "source": "Desktop-agent heartbeats and work sessions (Live Tracking)",
            "link": "/live",
        }
        card = {
            "kind": "metrics",
            "title": "Right now",
            "period": f"As of {o.as_of.astimezone(await self.tz()).strftime('%H:%M')}",
            "source": facts["source"],
            "link": {"label": "Open Live Tracking", "href": "/live"},
            "metrics": [
                {"label": "Online", "value": str(o.counts.online)},
                {"label": "Active", "value": str(o.counts.active)},
                {"label": "Idle", "value": str(o.counts.idle)},
                {"label": "Offline", "value": str(o.counts.offline)},
            ],
            "columns": [
                {"key": "employee", "label": "Person"},
                {"key": "status", "label": "Status"},
                {"key": "since", "label": "Since"},
                {"key": "application", "label": "Application"},
            ]
            if rows
            else [],
            "rows": rows,
        }
        return ToolResult(facts, [card])

    async def _t_get_team_activity(self, data: GroupInput) -> ToolResult:
        self._need(Permission.ACTIVITY_VIEW, "activity")
        period = resolve_period(data, await self.today())
        group, label = await self._group(data)
        r = await self.s.productivity.team_report(
            self.p, period.start, period.end, group.get("team_id"), group.get("department_id")
        )
        t = r.totals
        scores = {k: {"value": v["value"], "formula": v["formula"]} for k, v in r.scores.model_dump().items()}
        query = "&".join(f"{'team' if k == 'team_id' else 'department'}={v}" for k, v in group.items())
        link = "/productivity" + (f"?{query}" if query else "")
        facts = {
            "period": period.as_dict(),
            "scope": label,
            "people_with_data": len(r.rows),
            "totals": {
                "work": fmt(t.work_seconds),
                "active": fmt(t.active_seconds),
                "idle": fmt(t.idle_seconds),
                "extended_idle": fmt(t.extended_idle_seconds),
                "productive_apps": fmt(t.productive_seconds),
                "unclassified": fmt(t.unclassified_seconds),
                "focus": fmt(t.focus_seconds),
                "logged_on_tasks": fmt(t.task_seconds),
                "tasks_completed": t.tasks_completed,
                "tasks_due_open": t.tasks_due_open,
            },
            "scores": scores,
            "per_person": [
                {
                    "employee": row.employee.full_name,
                    "work": fmt(row.metrics.work_seconds),
                    "active": fmt(row.metrics.active_seconds),
                }
                for row in r.rows[:30]
            ],
            "observations": [i.title for i in r.insights],
            "source": "Desktop-agent work sessions and application activity, under the workspace's productivity rules",
            "caveat": r.disclaimer,
            "link": link,
        }
        cards: list[dict[str, Any]] = [
            {
                "kind": "metrics",
                "title": f"Activity · {label}",
                "period": period.label,
                "source": facts["source"],
                "link": {"label": "Open Productivity", "href": link},
                "metrics": [{"label": s.label, "value": s.value} for s in r.summary],
            },
            {
                "kind": "chart",
                "title": "Work hours per day",
                "period": period.label,
                "source": "Work sessions",
                "link": {"label": "Open Productivity", "href": link},
                "unit": "h",
                "series": [
                    {"label": d.day.strftime("%a %d"), "value": hours(d.metrics.work_seconds)} for d in r.days
                ],
            },
        ]
        if period.start == period.end:
            cards.pop()  # a single-day chart says nothing the metrics don't
        return ToolResult(facts, cards)

    async def _t_get_project_time(self, data: ProjectTimeInput) -> ToolResult:
        period = resolve_period(data, await self.today(), max_days=92)
        project = await self._project(data.project)
        s = await self.s.work.summary(self.p, period.start, period.end, None, project.id)
        members = [m for m in s.members if m.time_spent_seconds or m.completed_in_period]
        facts = {
            "period": period.as_dict(),
            "project": {
                "name": project.name,
                "key": project.key,
                "progress_percent": project.stats.progress,
                "status": project.status,
            },
            "time_logged": fmt(s.time_spent_seconds),
            "time_logged_hours": hours(s.time_spent_seconds),
            "tasks_completed_in_period": s.completed,
            "open_tasks": s.open,
            "overdue_tasks": s.overdue,
            "per_person": [
                {
                    "employee": m.employee.full_name,
                    "time": fmt(m.time_spent_seconds),
                    "completed": m.completed_in_period,
                }
                for m in members
            ],
            "source": "Task timers and manual time entries (Projects & Tasks), by people you can see",
            "link": f"/projects/{project.id}",
        }
        card = {
            "kind": "metrics",
            "title": f"{project.name} ({project.key})",
            "period": period.label,
            "source": facts["source"],
            "link": {"label": "Open project", "href": facts["link"]},
            "metrics": [
                {"label": "Time logged", "value": facts["time_logged"]},
                {"label": "Completed", "value": str(s.completed)},
                {"label": "Open", "value": str(s.open)},
                {"label": "Overdue", "value": str(s.overdue)},
                {"label": "Progress", "value": f"{project.stats.progress}%"},
            ],
            "columns": [
                {"key": "employee", "label": "Person"},
                {"key": "time", "label": "Time"},
                {"key": "completed", "label": "Completed"},
            ]
            if members
            else [],
            "rows": facts["per_person"],
        }
        return ToolResult(facts, [card])

    async def _t_list_overdue_tasks(self, data: OverdueInput) -> ToolResult:
        project = await self._project(data.project) if data.project else None
        assignee = await self._person(data.assignee_name) if data.assignee_name else None
        tasks = await self.s.work.list_tasks(
            self.p,
            project_id=project.id if project else None,
            assignee=str(assignee.id) if assignee else None,
            team_id=None,
            statuses=None,
            priority=None,
            search=None,
            due="overdue",
            include_subtasks=True,
            limit=200,
        )
        today = await self.today()
        tasks = sorted(tasks, key=lambda t: t.due_date or today)
        names = {p.id: p.name for p in await self.s.work.list_projects(self.p, include_archived=True)}
        rows = [
            {
                "reference": t.reference,
                "title": t.title,
                "project": names.get(t.project_id, t.project_key),
                "assignees": ", ".join(a.full_name for a in t.assignees) or "Unassigned",
                "due": t.due_date.isoformat() if t.due_date else "",
                "days_overdue": (today - t.due_date).days if t.due_date else None,
                "status": t.status.value.replace("_", " ").title(),
                "href": f"/projects/{t.project_id}?task={t.id}",
            }
            for t in tasks
        ]
        facts = {
            "as_of": today.isoformat(),
            "filters": {
                "project": project.name if project else None,
                "assignee": assignee.full_name if assignee else None,
            },
            "count": len(rows),
            "tasks": [{k: v for k, v in r.items() if k != "href"} for r in rows[:50]],
            "source": "Projects & Tasks (open tasks with a due date before today, in projects you can see)",
            "link": f"/projects/{project.id}" if project else "/projects/team",
        }
        card = {
            "kind": "table",
            "title": f"Overdue tasks ({len(rows)})",
            "period": f"As of {today.strftime('%d %b %Y')}",
            "source": facts["source"],
            "link": {"label": "Open task board", "href": facts["link"]},
            "columns": [
                {"key": "reference", "label": "Task"},
                {"key": "title", "label": "Title"},
                {"key": "assignees", "label": "Assignees"},
                {"key": "due", "label": "Due"},
                {"key": "days_overdue", "label": "Days over"},
            ],
            "rows": rows[:50],
        }
        return ToolResult(facts, [card])

    async def _t_get_attendance_summary(self, data: GroupInput) -> ToolResult:
        self._need(Permission.ACTIVITY_VIEW, "attendance")
        period = resolve_period(data, await self.today())
        group, label = await self._group(data)
        filters = ReportFilters(
            team_id=ObjectId(group["team_id"]) if "team_id" in group else None,
            department_id=ObjectId(group["department_id"]) if "department_id" in group else None,
        )
        report, ctx = await self.s.reports.build(
            self.p, ReportType.ATTENDANCE, period.start, period.end, filters
        )
        per: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"days": 0, "seconds": 0.0, "starts": [], "ends": []}
        )
        for row in report.rows:
            entry = per[row["employee"]]
            if row["status"] == "Worked":
                entry["days"] += 1
                entry["seconds"] += row["work_seconds"] or 0
                if row["first_start"]:
                    entry["starts"].append(row["first_start"].hour * 60 + row["first_start"].minute)
                if row["last_end"]:
                    entry["ends"].append(row["last_end"].hour * 60 + row["last_end"].minute)

        def avg(values: list[int]) -> str:
            if not values:
                return ""
            m = round(sum(values) / len(values))
            return f"{m // 60:02d}:{m % 60:02d}"

        rows = [
            {
                "employee": name,
                "days_worked": v["days"],
                "hours": fmt(v["seconds"]),
                "typical_start": avg(v["starts"]),
                "typical_end": avg(v["ends"]),
            }
            for name, v in sorted(per.items())
        ]
        facts = {
            "period": period.as_dict(),
            "scope": label,
            "days_in_period": ctx.days,
            "people": rows,
            "people_with_no_sessions": [r["employee"] for r in rows if r["days_worked"] == 0],
            "source": "Desktop-agent work sessions (first start and last end per day)",
            "caveat": "WorkPulse has no leave, holiday or shift records yet, so a day without sessions is not an absence.",
            "link": "/reports",
        }
        card = {
            "kind": "table",
            "title": f"Attendance · {label}",
            "period": period.label,
            "source": facts["source"],
            "note": facts["caveat"],
            "link": {"label": "Create an attendance report", "href": "/reports"},
            "columns": [
                {"key": "employee", "label": "Person"},
                {"key": "days_worked", "label": "Days worked"},
                {"key": "hours", "label": "Hours"},
                {"key": "typical_start", "label": "Typical start"},
                {"key": "typical_end", "label": "Typical end"},
            ],
            "rows": rows,
        }
        return ToolResult(facts, [card])

    async def _t_get_recent_events(self, data: PeriodInput) -> ToolResult:
        period = resolve_period(data, await self.today())
        tz = await self.tz()
        lo = datetime.combine(period.start, datetime.min.time(), tzinfo=tz)
        hi = datetime.combine(period.end + timedelta(days=1), datetime.min.time(), tzinfo=tz)
        items = []
        if self.p.has(Permission.ACTIVITY_VIEW) or self.p.has(Permission.AUDIT_LOG_VIEW):
            feed = await self.s.feed.recent(self.p, limit=200, team_id=None)
            items = [i for i in feed if lo <= i.occurred_at.astimezone(tz) < hi]
        by_action: dict[str, int] = defaultdict(int)
        for i in items:
            by_action[i.action] += 1
        notes, _ = await self.s.notifications.page(
            self.p.company_id, self.p.user_id, {"last_occurred_at": {"$gte": lo, "$lt": hi}}, 0, 50
        )
        events = [
            {
                "time": i.occurred_at.astimezone(tz).strftime("%d %b %H:%M"),
                "event": i.action.replace(".", " ").replace("_", " "),
                "who": (i.actor.name if i.actor else ""),
                "about": (i.subject.name if i.subject else ""),
            }
            for i in items[:40]
        ]
        alerts: list[dict[str, Any]] = [
            {
                "time": n.last_occurred_at.astimezone(tz).strftime("%d %b %H:%M"),
                "alert": n.title,
                "severity": n.severity.value,
                "count": n.count,
                "href": n.link or "/alerts",
            }
            for n in notes
        ]
        facts = {
            "period": period.as_dict(),
            "events_by_type": dict(sorted(by_action.items(), key=lambda kv: -kv[1])),
            "events": events,
            "your_alerts": [{k: v for k, v in a.items() if k != "href"} for a in alerts],
            "source": "Audit trail (organisation and work events) and your notifications",
            "link": "/alerts",
        }
        cards: list[dict[str, Any]] = []
        if alerts:
            cards.append(
                {
                    "kind": "list",
                    "title": f"Your alerts ({len(alerts)})",
                    "period": period.label,
                    "source": "Notifications",
                    "link": {"label": "Open Alerts", "href": "/alerts"},
                    "items": [
                        {
                            "title": a["alert"],
                            "meta": f"{a['severity'].title()} · {a['time']}"
                            + (f" · ×{a['count']}" if a["count"] > 1 else ""),  # noqa: RUF001 - shown to people
                            "href": a["href"],
                        }
                        for a in alerts[:12]
                    ],
                }
            )
        if events:
            cards.append(
                {
                    "kind": "list",
                    "title": f"Events ({len(items)})",
                    "period": period.label,
                    "source": "Audit trail",
                    "link": {"label": "Open dashboard", "href": "/dashboard"},
                    "items": [
                        {
                            "title": f"{e['event'].capitalize()}"
                            + (f" — {e['about']}" if e["about"] else ""),
                            "meta": f"{e['time']}" + (f" · {e['who']}" if e["who"] else ""),
                        }
                        for e in events[:12]
                    ],
                }
            )
        return ToolResult(facts, cards)

    async def _t_find_people(self, data: PeopleInput) -> ToolResult:
        q = _norm(data.query)
        people = [e for e in await self._visible_people() if q in _norm(e.full_name)][:20]
        teams = await self.s.teams.find_by_ids(self.p.company_id, [e.team_id for e in people if e.team_id])
        depts = await self.s.departments.find_by_ids(
            self.p.company_id, [e.department_id for e in people if e.department_id]
        )
        rows = [
            {
                "name": e.full_name,
                "job_title": e.job_title or "",
                "team": teams[e.team_id].name if e.team_id in teams else "",
                "department": depts[e.department_id].name if e.department_id in depts else "",
            }
            for e in sorted(people, key=lambda e: e.full_name)
        ]
        return ToolResult(
            {
                "query": data.query,
                "people": rows,
                "source": "People directory (your access scope)",
                "link": "/people",
            }
        )

    async def _t_get_employee_summary(self, data: EmployeeInput) -> ToolResult:
        period = resolve_period(data, await self.today())
        person = await self._person(data.employee_name)
        r = await self.s.productivity.employee_report(self.p, str(person.id), period.start, period.end)
        link = f"/productivity/employees/{person.id}"
        facts = {
            "period": period.as_dict(),
            "employee": person.full_name,
            "work_profile": r.work_profile.name if r.work_profile else None,
            "summary": {s.label: s.value for s in r.summary},
            "scores": {
                k: {"value": v["value"], "formula": v["formula"]} for k, v in r.scores.model_dump().items()
            },
            "projects": [
                {"project": p.name, "time": fmt(p.task_seconds), "completed": p.tasks_completed}
                for p in r.projects
            ],
            "observations": [i.title for i in r.insights],
            "source": "Desktop-agent work sessions, application activity and task time, under the workspace's productivity rules",
            "caveat": r.disclaimer,
            "link": link,
        }
        card = {
            "kind": "metrics",
            "title": person.full_name,
            "period": period.label,
            "source": facts["source"],
            "link": {"label": "Open their report", "href": link},
            "metrics": [{"label": s.label, "value": s.value} for s in r.summary],
        }
        return ToolResult(facts, [card])

    async def _t_list_projects(self, _: EmptyInput) -> ToolResult:
        projects = await self.s.work.list_projects(self.p, include_archived=False)
        rows = [
            {
                "project": p.name,
                "key": p.key,
                "progress": f"{p.stats.progress}%",
                "open": p.stats.total - p.stats.completed,
                "overdue": p.stats.overdue,
                "due": p.due_date.isoformat() if p.due_date else "",
                "href": f"/projects/{p.id}",
            }
            for p in projects
        ]
        facts = {
            "projects": [{k: v for k, v in r.items() if k != "href"} for r in rows],
            "source": "Projects & Tasks",
            "link": "/projects",
        }
        card = {
            "kind": "table",
            "title": f"Projects ({len(rows)})",
            "period": "Current",
            "source": "Projects & Tasks",
            "link": {"label": "Open projects", "href": "/projects"},
            "columns": [
                {"key": "project", "label": "Project"},
                {"key": "progress", "label": "Progress"},
                {"key": "open", "label": "Open"},
                {"key": "overdue", "label": "Overdue"},
                {"key": "due", "label": "Due"},
            ],
            "rows": rows,
        }
        return ToolResult(facts, [card])
