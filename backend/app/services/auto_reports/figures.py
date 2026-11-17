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
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Figures:
        known = {k: data[k] for k in cls.__dataclass_fields__ if k in data}
        return cls(**known)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

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
    #: One-line summary (AI or written from the numbers).
    note: str = ""
    #: Department and team names, for grouping the e-mail (empty when not set).
    department: str = ""
    team: str = ""
    department_id: ObjectId | None = None

    @property
    def started(self) -> bool:
        return self.day.work > 0

    def top(self, limit: int = 5, category: str | None = None) -> list[Usage]:
        items = [u for u in self.usage if u.seconds >= 60 and (category is None or u.category == category)]
        return items[:limit]


def usage_from_items(items: list[Any]) -> list[Usage]:
    """Engine usage items (summed per app/site) → most used first."""
    merged: dict[tuple[str, str], Usage] = {}
    for item in items:
        k = (item.kind, item.key)
        if k in merged:
            merged[k].seconds += item.seconds
        else:
            merged[k] = Usage(item.kind, item.key, item.name, float(item.seconds), item.category)
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
