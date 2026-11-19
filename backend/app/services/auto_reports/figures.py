"""What one automatic report says about one person, and how the figures are put together.

The numbers come from the same productivity engine and attendance report as the web app (nothing is calculated
differently here). The engine works in whole days, so the mid-day report is "today so far"; it stores a snapshot,
and the evening report shows the afternoon as "the whole day minus that snapshot", plus the whole day.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any, Literal

from bson import ObjectId

from app.services.productivity.engine import Metrics

Slot = Literal["midday", "evening"]
SLOTS: tuple[Slot, ...] = ("midday", "evening")

#: The parts of a report an administrator can include or leave out (the employee's name is always shown).
#: "required_hours" and "average" appear in the evening report only.
Section = Literal[
    "summary",
    "start_time",
    "active_idle",
    "categories",
    "productive_share",
    "customer_time",
    "top_apps",
    "focus",
    "required_hours",
    "average",
    "last_sign_out",
    "late_start",
    "meetings",
    "tasks",
    "screenshots",
    "highlights",
    "action_items",
    "overtime",
    "week",
    "week_compare",
    "long_breaks",
    "team_totals",
]
SECTIONS: tuple[Section, ...] = (
    "summary",
    "start_time",
    "active_idle",
    "categories",
    "productive_share",
    "customer_time",
    "top_apps",
    "focus",
    "required_hours",
    "average",
    "last_sign_out",
    "late_start",
    "meetings",
    "tasks",
    "screenshots",
    "highlights",
    "action_items",
    "overtime",
    "week",
    "week_compare",
    "long_breaks",
    "team_totals",
)
#: Switched on for a new workspace (the extra items can be added in Settings).
DEFAULT_SECTIONS: tuple[Section, ...] = SECTIONS[:10]
#: What an employee's own report shows by default.
EMPLOYEE_DEFAULT_SECTIONS: tuple[Section, ...] = (
    "start_time",
    "active_idle",
    "categories",
    "productive_share",
    "top_apps",
    "required_hours",
)


@dataclass
class Figures:
    """Seconds (and focus-session counts) for one person over one period."""

    work: float = 0.0
    active: float = 0.0
    idle: float = 0.0
    productive: float = 0.0
    neutral: float = 0.0
    unproductive: float = 0.0
    unclassified: float = 0.0
    focus_count: int = 0
    focus_seconds: float = 0.0
    #: Foreground time in the company's customer systems (CRM, ticketing, telephony).
    customer: float = 0.0
    #: Time logged on tasks.
    task: float = 0.0
    #: Idle time in single stretches of 15+ minutes (long breaks).
    extended_idle: float = 0.0

    @classmethod
    def from_metrics(cls, m: Metrics) -> Figures:
        return cls(
            work=m.work,
            active=m.active,
            idle=m.idle,
            productive=m.productive,
            neutral=m.neutral,
            unproductive=m.unproductive,
            unclassified=m.unclassified,
            focus_count=m.focus_count,
            focus_seconds=m.focus_seconds,
            customer=m.customer_seconds,
            task=m.task_seconds,
            extended_idle=m.extended_idle,
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Figures:
        known = {k: data[k] for k in cls.__dataclass_fields__ if k in data}
        return cls(**known)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def plus(self, other: Figures) -> Figures:
        out = Figures()
        for name in self.__dataclass_fields__:
            setattr(out, name, getattr(self, name) + getattr(other, name))
        return out

    def minus(self, earlier: Figures) -> Figures:
        """This period minus an earlier part of it (never below zero)."""
        out = Figures()
        for name in self.__dataclass_fields__:
            value = getattr(self, name) - getattr(earlier, name)
            setattr(out, name, max(0, value))
        return out

    @property
    def classified(self) -> float:
        return self.productive + self.neutral + self.unproductive

    @property
    def productive_share(self) -> int | None:
        """Productive ÷ (Productive + Neutral + Unproductive), as on the Productivity page."""
        return round(100 * self.productive / self.classified) if self.classified >= 60 else None


@dataclass
class Usage:
    kind: str  # "app" or "website"
    key: str
    name: str
    seconds: float
    category: str
    #: Seconds with keyboard/mouse input (None when not known).
    active: float | None = None

    @property
    def input_share(self) -> int | None:
        return round(100 * self.active / self.seconds) if self.active is not None and self.seconds > 0 else None


#: A Productive app or website open at least this long...
LOW_ACTIVITY_MIN_SECONDS = 60 * 60
#: ...with keyboard/mouse input in less than this share of the time is flagged (e.g. a CRM left open while on the
#: phone, the mouse nudged now and then). Real use of such a system is usually 40-80%.
LOW_ACTIVITY_SHARE = 15


@dataclass
class SignIn:
    """One work session today (company time zone), as on the Attendance page."""

    start: datetime
    end: datetime
    #: Still running when the report was made.
    open: bool = False
    #: Began before midnight (the session carried over from yesterday).
    from_yesterday: bool = False

    def label(self) -> str:
        start = "before 00:00" if self.from_yesterday else self.start.strftime("%H:%M")
        return f"{start} to {'now' if self.open else self.end.strftime('%H:%M')}"


@dataclass
class PersonReport:
    employee_id: ObjectId
    name: str
    email: str
    manager_id: ObjectId | None
    team_id: ObjectId | None
    #: The report's period: the day so far (mid-day) or the afternoon (evening).
    period: Figures
    #: The whole day so far.
    day: Figures
    #: Apps and websites in the period, most used first.
    usage: list[Usage] = field(default_factory=list)
    #: First activity today (company time zone): the first app or website used, not a session carried over
    #: from yesterday.
    first_in: datetime | None = None
    #: Today's sign-in sessions (sign in → sign out), oldest first.
    sessions: list[SignIn] = field(default_factory=list)
    #: Attendance status: met, short, in_progress, absent, no_target.
    attendance: str | None = None
    #: Active time as the attendance report counts it (meetings and customer time included).
    attended_active: int = 0
    #: Required seconds today (0 when there is no requirement).
    expected: int = 0
    #: Average active seconds and productive share over the past 7 days with work.
    avg_active: float | None = None
    avg_share: int | None = None
    #: Average idle seconds over the same past days (for "vs your 7-day average").
    avg_idle: float | None = None
    #: Today's focus sessions and long breaks (idle 15+ min): (start, end, seconds), company time zone.
    focus_list: list[tuple[datetime, datetime, float]] = field(default_factory=list)
    breaks: list[tuple[datetime, datetime, float]] = field(default_factory=list)
    #: Attendance status of each working day this week, Monday first (today last).
    week_statuses: list[str] = field(default_factory=list)
    #: One-line summary (AI or written from the numbers).
    note: str = ""
    #: Department and team names, for grouping the e-mail (empty when not set).
    department: str = ""
    team: str = ""
    department_id: ObjectId | None = None
    #: Approved time away from the computer (meetings, visits) today, as on the Attendance page.
    meetings: int = 0
    #: Screenshots taken today.
    screenshots: int = 0
    #: How long after the workday start (Settings → Workspace) the first activity came; None if on time.
    late_by: float | None = None
    #: Week so far (Monday to today): active time as attendance counts it, required time, days met / working days.
    week_active: int | None = None
    week_expected: int = 0
    week_met: int = 0
    week_days: int = 0
    #: Productive share and idle time this week vs the same days last week.
    this_week: Figures | None = None
    last_week: Figures | None = None
    #: Waiting for the manager: meeting claims to approve, tasks past their due date.
    pending_claims: int = 0
    overdue_tasks: int = 0
    #: The "Team total" row (not a person).
    is_total: bool = False
    #: The recipient's own row at the top of their team e-mail (left out of team highlights and totals).
    is_self: bool = False
    #: Manages people: a manager or team-lead role, someone's manager, a department head or a team lead.
    is_manager: bool = False

    @property
    def overtime(self) -> float:
        """Active time beyond today's required hours (0 without a requirement)."""
        return max(0.0, float(self.attended_active - self.expected)) if self.expected else 0.0

    @property
    def last_out(self) -> str:
        """Last sign-out today, \"Working\" while a session is open, or \"—\"."""
        if not self.sessions:
            return "—"
        last = self.sessions[-1]
        return "Working" if last.open else last.end.strftime("%H:%M")

    @property
    def started(self) -> bool:
        return self.day.work > 0

    def top(self, limit: int = 5, category: str | None = None) -> list[Usage]:
        items = [u for u in self.usage if u.seconds >= 60 and (category is None or u.category == category)]
        return items[:limit]

    def low_activity(self) -> list[Usage]:
        """Productive apps/sites open an hour or more with very little keyboard/mouse use."""
        return [
            u
            for u in self.usage
            if u.category == "productive"
            and u.seconds >= LOW_ACTIVITY_MIN_SECONDS
            and u.input_share is not None
            and u.input_share < LOW_ACTIVITY_SHARE
        ]


def usage_from_items(items: list[Any]) -> list[Usage]:
    """Engine usage items (summed per app/site) → most used first."""
    merged: dict[tuple[str, str], Usage] = {}
    for item in items:
        k = (item.kind, item.key)
        active = getattr(item, "active", None)
        if k in merged:
            merged[k].seconds += item.seconds
            if active is not None:
                merged[k].active = (merged[k].active or 0.0) + active
        else:
            merged[k] = Usage(item.kind, item.key, item.name, float(item.seconds), item.category, active)
    return sorted(merged.values(), key=lambda u: -u.seconds)


def usage_minus(day: list[Usage], earlier: dict[str, float]) -> list[Usage]:
    """Usage in the day minus a snapshot taken earlier (keyed "kind|key")."""
    out = [
        Usage(u.kind, u.key, u.name, max(0.0, u.seconds - earlier.get(f"{u.kind}|{u.key}", 0.0)), u.category)
        for u in day
    ]
    return sorted((u for u in out if u.seconds > 0), key=lambda u: -u.seconds)


def usage_snapshot(usage: list[Usage]) -> dict[str, float]:
    return {f"{u.kind}|{u.key}": u.seconds for u in usage}


def duration(seconds: float) -> str:
    """ "2h 05m", "45m", "0m"."""
    minutes = round(seconds / 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m" if hours else f"{minutes}m"


def day_label(day: date) -> str:
    return day.strftime("%a %d %b %Y").replace(" 0", " ")
