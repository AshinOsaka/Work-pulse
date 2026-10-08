"""Pure calculations behind the productivity views (no I/O, fully unit-tested).

Definitions (all per employee, in the workspace timezone):

* **Work time** — time inside work sessions (the employee clocked in on the desktop agent).
* **Active time** — work time with recent keyboard or mouse input.
* **Idle time** — work time without input beyond the idle threshold.
* **Away time** — gaps between work sessions within a day (from the first session start to the last
  session end), e.g. breaks. Time outside that span is not counted.
* **Productive / neutral / unproductive / unclassified time** — foreground time by category, according
  to the rules that apply to the employee. Browser time with a known website follows the website rule.
* **Focus session** — at least `FOCUS_MIN_SECONDS` of productive work with no interruption longer than
  `FOCUS_MAX_INTERRUPTION_SECONDS` and no unproductive activity longer than `FOCUS_MAX_UNPRODUCTIVE_SECONDS`.

Two separate kinds of output:

* **Activity score** = active time ÷ work time. It only says how much of the work time had input. Reading,
  meetings and thinking have little input, so it says nothing about the value of the work.
* **Productivity insights** — the category breakdown, focus sessions and observations. The one percentage
  shown (productive share of classified time) depends entirely on how rules are configured.

Neither is a measurement of an employee's performance.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from itertools import pairwise
from typing import Any
from zoneinfo import ZoneInfo

from app.models.agent import WorkSession
from app.services.productivity.rules import BROWSERS, UNCLASSIFIED, RuleBook

FOCUS_MIN_SECONDS = 25 * 60
FOCUS_MAX_INTERRUPTION_SECONDS = 2 * 60
FOCUS_MAX_UNPRODUCTIVE_SECONDS = 60
MIN_TRACKED_FOR_INSIGHTS = 30 * 60
#: An idle stretch at least this long counts as "extended idle" (a break, a meeting away from the keyboard…).
EXTENDED_IDLE_SECONDS = 15 * 60
#: Minimum productive time before a focus score is given.
MIN_PRODUCTIVE_FOR_FOCUS = 30 * 60
#: Minimum work time before work utilization is given.
MIN_WORK_FOR_UTILIZATION = 30 * 60
MIN_CLASSIFIED_SHARE = 0.5

CATEGORIES = ("productive", "neutral", "unproductive", UNCLASSIFIED)


# --------------------------------------------------------------------------- metrics container
@dataclass
class Metrics:
    work: float = 0.0
    active: float = 0.0
    idle: float = 0.0
    #: Idle time in uninterrupted stretches of EXTENDED_IDLE_SECONDS or more (exact presence data only).
    extended_idle: float = 0.0
    away: float = 0.0
    productive: float = 0.0
    neutral: float = 0.0
    unproductive: float = 0.0
    unclassified: float = 0.0
    focus_count: int = 0
    focus_seconds: float = 0.0
    longest_focus_seconds: float = 0.0
    context_switches: int = 0
    #: Time logged on tasks (timer and manual entries).
    task_seconds: float = 0.0
    tasks_completed: int = 0
    #: Tasks due in the period that are still open.
    tasks_due_open: int = 0

    @property
    def tracked(self) -> float:
        return self.productive + self.neutral + self.unproductive + self.unclassified

    @property
    def classified(self) -> float:
        return self.productive + self.neutral + self.unproductive

    def add(self, other: Metrics) -> None:
        for name in (
            "work",
            "active",
            "idle",
            "extended_idle",
            "away",
            "productive",
            "neutral",
            "unproductive",
            "unclassified",
            "focus_seconds",
            "task_seconds",
        ):
            setattr(self, name, getattr(self, name) + getattr(other, name))
        self.focus_count += other.focus_count
        self.context_switches += other.context_switches
        self.tasks_completed += other.tasks_completed
        self.tasks_due_open += other.tasks_due_open
        self.longest_focus_seconds = max(self.longest_focus_seconds, other.longest_focus_seconds)

    def as_dict(self) -> dict[str, Any]:
        return {
            "work_seconds": round(self.work),
            "active_seconds": round(self.active),
            "idle_seconds": round(self.idle),
            "extended_idle_seconds": round(self.extended_idle),
            "away_seconds": round(self.away),
            "tracked_seconds": round(self.tracked),
            "productive_seconds": round(self.productive),
            "neutral_seconds": round(self.neutral),
            "unproductive_seconds": round(self.unproductive),
            "unclassified_seconds": round(self.unclassified),
            "focus_sessions": self.focus_count,
            "focus_seconds": round(self.focus_seconds),
            "longest_focus_seconds": round(self.longest_focus_seconds),
            "context_switches": self.context_switches,
            "task_seconds": round(self.task_seconds),
            "tasks_completed": self.tasks_completed,
            "tasks_due_open": self.tasks_due_open,
        }


def local_days(start: date, end: date) -> list[date]:
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def day_bounds(day: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    begin = datetime.combine(day, time.min, tzinfo=tz)
    return begin, datetime.combine(day + timedelta(days=1), time.min, tzinfo=tz)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


# --------------------------------------------------------------------------- work, active, idle, away
def session_pieces(
    session: WorkSession, now: datetime, open_end: datetime | None = None
) -> list[tuple[datetime, datetime, float]]:
    """The session as (start, end, active_fraction) pieces.

    Uses the recorded active/idle changes when present (exact). Older sessions only have totals, so
    their idle share is spread evenly over the session. An open session without changes counts as active.
    """
    start = _aware(session.started_at)
    end = _aware(session.ended_at) if session.ended_at else _aware(open_end) if open_end else now
    if end <= start:
        return []
    if session.presence_changes:
        pieces: list[tuple[datetime, datetime, float]] = []
        cursor, active = start, True
        for change in sorted(session.presence_changes, key=lambda c: c.at):
            at = min(max(_aware(change.at), start), end)
            if at > cursor:
                pieces.append((cursor, at, 1.0 if active else 0.0))
                cursor = at
            active = change.status == "active"
        if end > cursor:
            pieces.append((cursor, end, 1.0 if active else 0.0))
        return pieces
    total = (session.active_seconds or 0) + (session.idle_seconds or 0)
    fraction = (session.active_seconds or 0) / total if session.ended_at and total > 0 else 1.0
    return [(start, end, fraction)]


def time_accounting(
    sessions: Iterable[WorkSession],
    days: Sequence[date],
    tz: ZoneInfo,
    now: datetime,
    open_ends: dict[Any, datetime] | None = None,
) -> dict[date, Metrics]:
    """Work, active, idle and away seconds per local day."""
    result = {day: Metrics() for day in days}
    spans: dict[date, list[datetime]] = defaultdict(list)  # first start / last end per day
    for session in sessions:
        exact = bool(session.presence_changes)
        for piece_start, piece_end, fraction in session_pieces(
            session, now, (open_ends or {}).get(session.id)
        ):
            # Extended idle needs exact idle stretches; prorated older sessions can't show them.
            extended = (
                exact
                and fraction == 0.0
                and (piece_end - piece_start).total_seconds() >= EXTENDED_IDLE_SECONDS
            )
            # Only the local days this piece touches (keeps long ranges cheap).
            first, last = piece_start.astimezone(tz).date(), piece_end.astimezone(tz).date()
            for offset in range((last - first).days + 1):
                day = first + timedelta(days=offset)
                if day not in result:
                    continue
                lo, hi = day_bounds(day, tz)
                s, e = max(piece_start, lo), min(piece_end, hi)
                if e <= s:
                    continue
                seconds = (e - s).total_seconds()
                m = result[day]
                m.work += seconds
                m.active += seconds * fraction
                m.idle += seconds * (1 - fraction)
                if extended:
                    m.extended_idle += seconds
                spans[day].extend((s, e))
    for day, edges in spans.items():
        span = (max(edges) - min(edges)).total_seconds()
        result[day].away = max(0.0, span - result[day].work)
    return result


# --------------------------------------------------------------------------- categories (from rollups)
@dataclass
class UsageItem:
    kind: str  # "app" or "website"
    key: str  # app_id or domain
    name: str
    seconds: float = 0.0
    category: str = UNCLASSIFIED
    rule_scope: str | None = None
    rule_pattern: str | None = None


def category_time(
    app_rows: Iterable[dict[str, Any]], site_rows: Iterable[dict[str, Any]], book: RuleBook
) -> tuple[dict[str, float], dict[tuple[str, str], UsageItem]]:
    """Seconds per category for one employee from the daily rollups.

    Browser time with a recorded domain is classified by the website; the rest of the browser's time
    (no domain known, e.g. website tracking off) falls back to the browser's own application rule.
    """
    per_category = dict.fromkeys(CATEGORIES, 0.0)
    items: dict[tuple[str, str], UsageItem] = {}
    site_seconds_by_app: dict[str, float] = defaultdict(float)
    for row in site_rows:
        match = book.website(row["domain"])
        item = items.setdefault(
            ("website", row["domain"]),
            UsageItem(
                "website", row["domain"], row["domain"], 0.0, match.category, match.scope, match.pattern
            ),
        )
        item.seconds += row["seconds"]
        per_category[match.category] += row["seconds"]
        site_seconds_by_app[row["app_id"]] += row["seconds"]
    for row in app_rows:
        seconds = row["seconds"] - site_seconds_by_app.get(row["app_id"], 0.0)
        if seconds <= 0.5:
            continue
        match = book.app(row["app_id"], row["app_name"])
        item = items.setdefault(
            ("app", row["app_id"]),
            UsageItem("app", row["app_id"], row["app_name"], 0.0, match.category, match.scope, match.pattern),
        )
        item.seconds += seconds
        per_category[match.category] += seconds
    return per_category, items


# --------------------------------------------------------------------------- focus and switching (from segments)
@dataclass
class Segment:
    start: datetime
    end: datetime
    app_id: str
    app_name: str
    domain: str | None
    category: str = UNCLASSIFIED

    @property
    def seconds(self) -> float:
        return max(0.0, (self.end - self.start).total_seconds())


@dataclass
class FocusSession:
    start: datetime
    end: datetime
    productive_seconds: float
    apps: dict[str, float] = field(default_factory=dict)

    @property
    def seconds(self) -> float:
        return (self.end - self.start).total_seconds()


def classify_segments(segments: Iterable[Segment], book: RuleBook) -> list[Segment]:
    out = []
    for seg in segments:
        seg.category = book.classify(
            seg.app_id, seg.app_name, seg.domain if seg.app_id in BROWSERS else None
        ).category
        out.append(seg)
    return sorted(out, key=lambda s: s.start)


def focus_sessions(segments: Sequence[Segment]) -> list[FocusSession]:
    """Runs of productive work; brief neutral switches and short gaps are tolerated, unproductive time is not."""
    found: list[FocusSession] = []
    current: FocusSession | None = None
    interruption = 0.0  # non-productive seconds since the last productive segment

    def close() -> None:
        nonlocal current
        if current and current.seconds >= FOCUS_MIN_SECONDS:
            found.append(current)
        current = None

    last_end: datetime | None = None
    for seg in segments:
        gap = (seg.start - last_end).total_seconds() if last_end else 0.0
        last_end = max(last_end, seg.end) if last_end else seg.end
        if current and gap > FOCUS_MAX_INTERRUPTION_SECONDS:
            close()
        if seg.category == "productive":
            if current is None:
                current = FocusSession(seg.start, seg.end, 0.0)
            current.end = seg.end
            current.productive_seconds += seg.seconds
            name = seg.domain or seg.app_name
            current.apps[name] = current.apps.get(name, 0.0) + seg.seconds
            interruption = 0.0
        elif current is not None:
            interruption += gap + seg.seconds
            limit = (
                FOCUS_MAX_UNPRODUCTIVE_SECONDS
                if seg.category == "unproductive"
                else FOCUS_MAX_INTERRUPTION_SECONDS
            )
            if seg.seconds > limit or interruption > FOCUS_MAX_INTERRUPTION_SECONDS:
                close()
    close()
    return found


def context_switches(segments: Sequence[Segment]) -> int:
    """Changes of application or website between consecutive segments less than two minutes apart."""
    switches = 0
    for prev, seg in pairwise(segments):
        close_in_time = (seg.start - prev.end).total_seconds() <= FOCUS_MAX_INTERRUPTION_SECONDS
        if close_in_time and (prev.app_id, prev.domain) != (seg.app_id, seg.domain):
            switches += 1
    return switches


# --------------------------------------------------------------------------- scores
def _pct(part: float, whole: float) -> int | None:
    return round(100 * part / whole) if whole > 0 else None


def activity_score(m: Metrics) -> dict[str, Any]:
    value = _pct(m.active, m.work) if m.work >= 60 else None
    return {
        "key": "activity_score",
        "label": "Activity score",
        "value": value,
        "status": "ok" if value is not None else "insufficient_data",
        "formula": "Active time ÷ Work time × 100",  # noqa: RUF001 - shown to people
        "components": [
            {"key": "active_seconds", "label": "Active time", "seconds": round(m.active)},
            {"key": "work_seconds", "label": "Work time", "seconds": round(m.work)},
        ],
        "interpretation": (
            "How much of the work time had keyboard or mouse input. Reading, calls, meetings and thinking "
            "involve little input, so this is not a measure of productivity or of the quality of work."
        ),
    }


def productive_share(m: Metrics) -> dict[str, Any]:
    enough = (
        m.tracked >= MIN_TRACKED_FOR_INSIGHTS
        and m.tracked > 0
        and m.classified / m.tracked >= MIN_CLASSIFIED_SHARE
    )
    value = _pct(m.productive, m.classified) if enough else None
    if m.tracked < MIN_TRACKED_FOR_INSIGHTS:
        reason = "Less than 30 minutes of application activity in this period."
    elif m.tracked > 0 and m.classified / m.tracked < MIN_CLASSIFIED_SHARE:
        reason = (
            "Less than half of the activity is covered by productivity rules. Classify more applications."
        )
    else:
        reason = None
    return {
        "key": "productive_share",
        "label": "Productive share",
        "value": value,
        "status": "ok" if value is not None else "insufficient_data",
        "reason": reason,
        "formula": "Productive time ÷ (Productive + Neutral + Unproductive time) × 100",  # noqa: RUF001
        "components": [
            {"key": "productive_seconds", "label": "Productive", "seconds": round(m.productive)},
            {"key": "neutral_seconds", "label": "Neutral", "seconds": round(m.neutral)},
            {"key": "unproductive_seconds", "label": "Unproductive", "seconds": round(m.unproductive)},
            {
                "key": "unclassified_seconds",
                "label": "Unclassified (excluded)",
                "seconds": round(m.unclassified),
            },
        ],
        "coverage": _pct(m.classified, m.tracked),
        "interpretation": (
            "Share of classified application and website time that your rules call productive. It reflects "
            "how the rules are configured as much as how time was spent, and is not a performance rating."
        ),
    }


def focus_score(m: Metrics) -> dict[str, Any]:
    """How much of the productive time came in uninterrupted focus sessions."""
    value = (
        min(100, _pct(m.focus_seconds, m.productive) or 0)
        if m.productive >= MIN_PRODUCTIVE_FOR_FOCUS
        else None
    )
    return {
        "key": "focus_score",
        "label": "Focus score",
        "value": value,
        "status": "ok" if value is not None else "insufficient_data",
        "reason": None if value is not None else "Less than 30 minutes of productive time in this period.",
        "formula": "Time in focus sessions ÷ Productive time × 100",  # noqa: RUF001 - shown to people
        "components": [
            {"key": "focus_seconds", "label": "Time in focus sessions", "seconds": round(m.focus_seconds)},
            {"key": "productive_seconds", "label": "Productive time", "seconds": round(m.productive)},
        ],
        "interpretation": (
            f"A focus session is {FOCUS_MIN_SECONDS // 60}+ minutes of productive work without longer "
            "interruptions. Some jobs (support, sales) are interrupt-driven by nature, so a low value can be "
            "exactly what the role requires."
        ),
    }


def work_utilization(m: Metrics) -> dict[str, Any]:
    """How much of the recorded work time was logged against tasks."""
    value: int | None = None
    reason: str | None = None
    if m.work < MIN_WORK_FOR_UTILIZATION:
        reason = "Less than 30 minutes of work time in this period."
    else:
        raw = _pct(m.task_seconds, m.work) or 0
        value = min(100, raw)
        if raw > 100:
            reason = (
                "More time was logged on tasks than recorded as work time (manual entries, or work without the "
                "desktop agent), so the value is capped at 100%."
            )
    return {
        "key": "work_utilization",
        "label": "Work utilization",
        "value": value,
        "status": "ok" if value is not None else "insufficient_data",
        "reason": reason,
        "formula": "Time logged on tasks ÷ Work time × 100",  # noqa: RUF001 - shown to people
        "components": [
            {"key": "task_seconds", "label": "Time logged on tasks", "seconds": round(m.task_seconds)},
            {"key": "work_seconds", "label": "Work time", "seconds": round(m.work)},
        ],
        "interpretation": (
            "Share of work time attributed to tracked tasks. Meetings, email and untracked work also count as "
            "work, so 100% is neither expected nor a goal; use it to see whether task logging reflects the work."
        ),
    }


def summary(m: Metrics) -> list[dict[str, Any]]:
    """The headline measurements behind the insights, each with the metrics it comes from."""
    completion = task_completion(m)
    return [
        {"key": "active", "label": "Active work", "value": _fmt(m.active), "metrics": ["active_seconds"]},
        {
            "key": "task_completion",
            "label": "Task completion",
            "value": f"{completion['value']}%" if completion["value"] is not None else "—",
            "metrics": ["tasks_completed", "tasks_due_open"],
        },
        {
            "key": "productive",
            "label": "Productive applications",
            "value": _fmt(m.productive),
            "metrics": ["productive_seconds"],
        },
        {"key": "focus", "label": "Focus time", "value": _fmt(m.focus_seconds), "metrics": ["focus_seconds"]},
        {
            "key": "tasks",
            "label": "Logged on tasks",
            "value": _fmt(m.task_seconds),
            "metrics": ["task_seconds"],
        },
        {
            "key": "extended_idle",
            "label": "Extended idle",
            "value": _fmt(m.extended_idle),
            "metrics": ["extended_idle_seconds"],
        },
    ]


def task_completion(m: Metrics) -> dict[str, Any]:
    """Completed ÷ (completed + still-open tasks that were due in the period)."""
    denominator = m.tasks_completed + m.tasks_due_open
    value = _pct(m.tasks_completed, denominator) if denominator else None
    return {
        "available": True,
        "value": value,
        "reason": "No tasks were completed or due in this period." if value is None else "",
        "formula": "Tasks completed ÷ (Tasks completed + Open tasks that were due) × 100",  # noqa: RUF001
        "completed": m.tasks_completed,
        "due_open": m.tasks_due_open,
        "task_seconds": round(m.task_seconds),
        "interpretation": (
            "Counts tasks, not their size or difficulty, and only tasks tracked in WorkPulse. Use it to spot "
            "slipping work, not to compare people."
        ),
    }


# --------------------------------------------------------------------------- insights
def _fmt(seconds: float) -> str:
    minutes = round(seconds / 60)
    hours, rest = divmod(minutes, 60)
    return f"{hours}h {rest:02d}m" if hours else f"{minutes}m"


def insights(
    current: Metrics, previous: Metrics | None, items: Iterable[UsageItem], days_with_work: int
) -> list[dict[str, Any]]:
    """Plain observations, each tied to the metrics it is based on. No judgement of the person."""
    out: list[dict[str, Any]] = []
    items = list(items)
    if current.work == 0 and current.task_seconds == 0 and not current.tasks_completed:
        return [
            {
                "tone": "info",
                "title": "No work sessions in this period",
                "detail": "Insights appear once the desktop agent has recorded work sessions.",
                "metrics": ["work_seconds"],
            }
        ]
    if current.tracked and current.unclassified / current.tracked >= 0.25:
        top = sorted((i for i in items if i.category == UNCLASSIFIED), key=lambda i: -i.seconds)[:3]
        out.append(
            {
                "tone": "attention",
                "title": f"{_pct(current.unclassified, current.tracked)}% of activity is unclassified",
                "detail": "Add productivity rules for "
                + ", ".join(i.name for i in top)
                + " to make the category breakdown meaningful.",
                "metrics": ["unclassified_seconds", "tracked_seconds"],
            }
        )
    if current.focus_count:
        out.append(
            {
                "tone": "positive",
                "title": f"{current.focus_count} focus session{'s' if current.focus_count != 1 else ''}, {_fmt(current.focus_seconds)} in total",
                "detail": f"The longest lasted {_fmt(current.longest_focus_seconds)}. A focus session is at least "
                f"{FOCUS_MIN_SECONDS // 60} minutes of productive work without longer interruptions.",
                "metrics": ["focus_sessions", "focus_seconds", "longest_focus_seconds"],
            }
        )
    elif current.productive >= FOCUS_MIN_SECONDS:
        out.append(
            {
                "tone": "info",
                "title": "Productive time was fragmented",
                "detail": f"{_fmt(current.productive)} of productive time, but no stretch of "
                f"{FOCUS_MIN_SECONDS // 60}+ minutes without interruption.",
                "metrics": ["productive_seconds", "focus_sessions", "context_switches"],
            }
        )
    if current.tracked >= 3600:
        per_hour = current.context_switches / (current.tracked / 3600)
        if per_hour >= 30:
            out.append(
                {
                    "tone": "attention",
                    "title": f"Frequent switching: about {round(per_hour)} application changes per hour",
                    "detail": "Frequent switching can indicate interruptions; it can also be normal for the role.",
                    "metrics": ["context_switches", "tracked_seconds"],
                }
            )
    top_unproductive = sorted((i for i in items if i.category == "unproductive"), key=lambda i: -i.seconds)[
        :1
    ]
    if top_unproductive and top_unproductive[0].seconds >= 15 * 60:
        item = top_unproductive[0]
        out.append(
            {
                "tone": "info",
                "title": f"Most time in an unproductive category: {item.name} ({_fmt(item.seconds)})",
                "detail": "Based on your workspace rules; check the rule if this use is part of the job.",
                "metrics": ["unproductive_seconds"],
            }
        )
    if current.extended_idle >= 30 * 60:
        out.append(
            {
                "tone": "info",
                "title": f"{_fmt(current.extended_idle)} in idle stretches of {EXTENDED_IDLE_SECONDS // 60}+ minutes",
                "detail": "Long periods without input inside a work session — often breaks, calls or meetings away "
                "from the keyboard. Stopping the work session during breaks keeps work time accurate.",
                "metrics": ["extended_idle_seconds", "idle_seconds"],
            }
        )
    if current.work and current.idle / current.work >= 0.3:
        out.append(
            {
                "tone": "info",
                "title": f"{_pct(current.idle, current.work)}% of work time was idle",
                "detail": "Idle means no keyboard or mouse input — for example calls, reading or time away from "
                "the computer without stopping the work session.",
                "metrics": ["idle_seconds", "work_seconds"],
            }
        )
    if (
        previous
        and previous.classified >= MIN_TRACKED_FOR_INSIGHTS
        and current.classified >= MIN_TRACKED_FOR_INSIGHTS
    ):
        before = previous.productive / previous.classified
        now = current.productive / current.classified
        delta = round(100 * (now - before))
        if abs(delta) >= 10:
            out.append(
                {
                    "tone": "info",
                    "title": f"Productive share {'up' if delta > 0 else 'down'} {abs(delta)} points vs the previous period",
                    "detail": "Compared with the period of the same length immediately before. Rule changes affect both periods.",
                    "metrics": ["productive_seconds", "neutral_seconds", "unproductive_seconds"],
                }
            )
    if current.task_seconds and not current.work:
        out.append(
            {
                "tone": "info",
                "title": f"{_fmt(current.task_seconds)} logged on tasks",
                "detail": "No desktop-agent work sessions in this period, so it can't be compared with work time.",
                "metrics": ["task_seconds"],
            }
        )
    if current.task_seconds and current.work:
        out.append(
            {
                "tone": "info",
                "title": f"{_fmt(current.task_seconds)} logged on tasks ({_pct(current.task_seconds, current.work)}% of work time)",
                "detail": "Time from task timers and manual entries. Time not logged on a task can still be productive.",
                "metrics": ["task_seconds", "work_seconds"],
            }
        )
    if current.tasks_due_open:
        out.append(
            {
                "tone": "attention",
                "title": f"{current.tasks_due_open} task{'s' if current.tasks_due_open != 1 else ''} due in this period still open",
                "detail": "Overdue or due today and not completed yet.",
                "metrics": ["tasks_due_open", "tasks_completed"],
            }
        )
    if days_with_work:
        out.append(
            {
                "tone": "info",
                "title": f"{_fmt(current.work / days_with_work)} of work time per working day on average",
                "detail": f"Averaged over {days_with_work} day{'s' if days_with_work != 1 else ''} with work sessions "
                "(per person, for a team).",
                "metrics": ["work_seconds"],
            }
        )
    return out
