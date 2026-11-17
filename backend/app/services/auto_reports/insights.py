"""The "at a glance" parts of a manager's report: highlights, action items and the team total row.

All of it is worked out from the figures already in the report (no extra data, no AI): who is most and least
productive, who is absent or late, who worked extra, what is waiting for the manager.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from html import escape

from bson import ObjectId

from app.services.auto_reports.figures import Figures, PersonReport, Slot, duration

#: A highlight is only worth mentioning above these.
MIN_CLASSIFIED = 30 * 60
MIN_IDLE = 15 * 60
MIN_UNPRODUCTIVE = 10 * 60
MIN_OVERTIME = 15 * 60


@dataclass
class Highlight:
    good: bool
    text: str


def highlights(people: list[PersonReport], slot: Slot) -> list[Highlight]:
    out: list[Highlight] = []
    working = [p for p in people if p.started]
    rated = [
        p for p in working if p.period.classified >= MIN_CLASSIFIED and p.period.productive_share is not None
    ]
    if rated:
        best = max(rated, key=lambda p: p.period.productive_share or 0)
        out.append(Highlight(True, f"Most productive: {best.name} ({best.period.productive_share}%)"))
        if len(rated) > 1:
            low = min(rated, key=lambda p: p.period.productive_share or 0)
            if low is not best:
                out.append(Highlight(False, f"Least productive: {low.name} ({low.period.productive_share}%)"))
    idle = [p for p in working if p.day.idle >= MIN_IDLE]
    if idle:
        most = max(idle, key=lambda p: p.day.idle)
        out.append(Highlight(False, f"Most idle: {most.name} ({duration(most.day.idle)})"))
    unproductive = [p for p in working if p.period.unproductive >= MIN_UNPRODUCTIVE]
    if unproductive:
        most = max(unproductive, key=lambda p: p.period.unproductive)
        worst = most.top(1, "unproductive")
        where = f", mostly {worst[0].name}" if worst else ""
        out.append(
            Highlight(False, f"Most unproductive: {most.name} ({duration(most.period.unproductive)}{where})")
        )
    absent = [p.name for p in people if not p.started]
    if absent:
        out.append(
            Highlight(False, f"{'Not started' if slot == 'midday' else 'No activity'}: {', '.join(absent)}")
        )
    late = [p for p in people if p.late_by]
    if late:
        out.append(
            Highlight(False, "Late: " + ", ".join(f"{p.name} ({duration(p.late_by or 0)})" for p in late))
        )
    if slot == "evening":
        short = [p.name for p in people if p.attendance == "short"]
        if short:
            out.append(Highlight(False, f"Short of required hours: {', '.join(short)}"))
        extra = [p for p in people if p.overtime >= MIN_OVERTIME]
        if extra:
            out.append(
                Highlight(
                    True, "Extra time: " + ", ".join(f"{p.name} (+{duration(p.overtime)})" for p in extra)
                )
            )
    return out


def action_items(people: list[PersonReport]) -> list[str]:
    claims = [p for p in people if p.pending_claims]
    tasks = [p for p in people if p.overdue_tasks]
    items = []
    if claims:
        n = sum(p.pending_claims for p in claims)
        items.append(
            f"{n} meeting claim{'s' if n != 1 else ''} to approve: "
            + ", ".join(f"{p.name}{f' ({p.pending_claims})' if p.pending_claims > 1 else ''}" for p in claims)
        )
    if tasks:
        n = sum(p.overdue_tasks for p in tasks)
        items.append(
            f"{n} overdue task{'s' if n != 1 else ''}: "
            + ", ".join(f"{p.name}{f' ({p.overdue_tasks})' if p.overdue_tasks > 1 else ''}" for p in tasks)
        )
    return items


def team_total(people: list[PersonReport]) -> PersonReport:
    """One row adding everyone up (Productive % from the totals, so it's the team's real share)."""

    def add(get: str) -> Figures:
        total = Figures()
        for p in people:
            total = total.plus(getattr(p, get))
        return total

    return PersonReport(
        employee_id=ObjectId(),
        name="Team total",
        email="",
        manager_id=None,
        team_id=None,
        period=add("period"),
        day=add("day"),
        attended_active=sum(p.attended_active for p in people),
        expected=sum(p.expected for p in people),
        meetings=sum(p.meetings for p in people),
        screenshots=sum(p.screenshots for p in people),
        week_active=sum(p.week_active or 0 for p in people),
        week_expected=sum(p.week_expected for p in people),
        week_met=sum(p.week_met for p in people),
        week_days=sum(p.week_days for p in people),
        is_total=True,
    )


# ---------------------------------------------------------------------------------------------- HTML pieces
def highlights_html(items: list[Highlight], plain: Callable[[str], str]) -> str:
    if not items:
        return ""
    lis = "".join(
        f'<li style="margin:3px 0;color:#1e202c"><span style="color:{"#16a34a" if h.good else "#d97706"}">'
        f"{'★' if h.good else '▲'}</span> {plain(h.text)}</li>"
        for h in items
    )
    return (
        '<div style="margin-top:14px;border:1px solid #e3e5ec;border-radius:10px;padding:10px 14px">'
        '<div style="font-size:12px;font-weight:700;color:#646878;text-transform:uppercase;letter-spacing:.05em">'
        f'At a glance</div><ul style="margin:6px 0 0;padding:0 0 0 2px;list-style:none;font-size:13px">{lis}</ul></div>'
    )


def actions_html(items: list[str], link: str) -> str:
    if not items:
        return ""
    lis = "".join(f'<li style="margin:3px 0">{escape(i)}</li>' for i in items)
    return (
        '<div style="margin-top:12px;background:#fff7e6;border:1px solid #f5d18a;border-radius:10px;padding:10px 14px">'
        '<div style="font-size:12px;font-weight:700;color:#8a5a00;text-transform:uppercase;letter-spacing:.05em">'
        "Needs your action</div>"
        f'<ul style="margin:6px 0 0;padding-left:18px;font-size:13px;color:#1e202c">{lis}</ul>'
        f'<a href="{escape(link)}" style="font-size:12px;color:#5b4ce6">Open in WorkPulse</a></div>'
    )
