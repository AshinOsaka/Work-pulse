"""The team report e-mail (managers, department heads, team leads and extra recipients).

Layout: header → summary tiles → team summary → at a glance → needs your action → team table → required hours today
(evening) → person cards → summary lines. Tables and inline styles only, so it renders the same in every mail app.
What appears follows the workspace's Content choices. No window titles, no screenshots.
"""

from __future__ import annotations

from collections.abc import Collection
from datetime import date
from html import escape

from app.services.auto_reports.figures import Figures, PersonReport, Slot, day_label, duration
from app.services.auto_reports.insights import action_items
from app.services.auto_reports.personal import (
    BRAND,
    FONT,
    GREY,
    INK,
    LINE,
    MUTED,
    ORANGE,
    TEAL,
    _bar,
    _card,
    _clock,
    _section_title,
    _signed,
    attendance_rows,
    category_table,
)
from app.services.auto_reports.render import FOOTNOTE, _plain
from app.services.auto_reports.summary import BELOW_AVERAGE, NOTABLE_UNPRODUCTIVE, Summary

AVATAR_COLORS = ["#6366f1", "#0d9488", "#ea580c", "#9333ea", "#db2777", "#2563eb", "#475569", "#16a34a"]
STATUS_BADGE = {
    "met": ("Met", "#166534", "#dcfce7"),
    "short": ("Short", "#92400e", "#fef3c7"),
    "absent": ("Absent", "#991b1b", "#fee2e2"),
    "in_progress": ("In progress", "#334155", "#f1f5f9"),
    "no_target": ("No target", "#334155", "#f1f5f9"),
}


def _initials(name: str) -> str:
    parts = [w for w in name.split() if w]
    return ((parts[0][0] + (parts[-1][0] if len(parts) > 1 else "")) if parts else "?").upper()


def _avatar(name: str, size: int = 32) -> str:
    color = AVATAR_COLORS[sum(map(ord, name)) % len(AVATAR_COLORS)]
    return (
        f'<span style="display:inline-block;width:{size}px;height:{size}px;line-height:{size}px;border-radius:8px;'
        f'background:{color};color:#fff;font-size:{max(10, size // 3)}px;font-weight:800;text-align:center">'
        f"{escape(_initials(name))}</span>"
    )


def _pill(text: str, fg: str, bg: str) -> str:
    return (
        f'<span style="display:inline-block;padding:3px 10px;border-radius:999px;font-size:11.5px;font-weight:700;'
        f'color:{fg};background:{bg};white-space:nowrap">{escape(text)}</span>'
    )


def _team(people: list[PersonReport]) -> list[PersonReport]:
    return [p for p in people if not p.is_self]


def _title(people: list[PersonReport]) -> str:
    departments = {p.department for p in _team(people) if p.department}
    return f"Team report · {next(iter(departments))}" if len(departments) == 1 else "Team report"


# ---------------------------------------------------------------------------------------------- tiles
def _tiles(people: list[PersonReport], slot: Slot, sections: set[str]) -> str:
    team = _team(people)
    productive = sum(p.period.productive for p in team)
    classified = sum(p.period.classified for p in team)
    share = f"{round(100 * productive / classified)}%" if classified >= 60 else "—"
    tiles: list[tuple[str, str, str, bool]] = [("Team productive", share, "#ffffff", True)]
    if slot == "evening" and "required_hours" in sections:
        with_target = [p for p in team if p.expected]
        met = sum(1 for p in with_target if p.attendance == "met")
        tiles += [
            (
                "Required hours met",
                f'{met}<span style="font-size:15px;color:{GREY}"> / {len(with_target)}</span>',
                "#15803d",
                False,
            ),
            ("Short", str(sum(1 for p in team if p.attendance == "short")), "#b45309", False),
            ("Absent", str(sum(1 for p in team if p.attendance == "absent")), "#b91c1c", False),
        ]
    else:
        started = sum(1 for p in team if p.started)
        tiles += [
            (
                "Started",
                f'{started}<span style="font-size:15px;color:{GREY}"> / {len(team)}</span>',
                "#15803d",
                False,
            ),
            ("Not started", str(len(team) - started), "#b91c1c", False),
            ("Unproductive", duration(sum(p.period.unproductive for p in team)), "#c2410c", False),
        ]
    tiles.append(("Focus sessions", str(sum(p.period.focus_count for p in team)), "#0f766e", False))
    cells = "".join(
        f'<td width="20%" valign="top" style="padding:0 {6 if i < len(tiles) - 1 else 0}px 0 0">'
        f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:separate;'
        f"background:{'#111827' if dark else '#ffffff'};border:1px solid {'#111827' if dark else LINE};"
        f'border-radius:14px"><tr><td style="padding:14px 14px">'
        f'<div style="font-size:12px;color:{"#cbd5e1" if dark else MUTED}">{escape(label)}</div>'
        f'<div style="font-size:26px;font-weight:800;color:{color};margin-top:6px">{value}</div>'
        "</td></tr></table></td>"
        for i, (label, value, color, dark) in enumerate(tiles)
    )
    return f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr>{cells}</tr></table>'


# ---------------------------------------------------------------------------------------------- at a glance
def _glance(people: list[PersonReport], slot: Slot) -> str:
    team = [p for p in _team(people) if p.started]
    cards: list[tuple[str, str, str, str, str, str]] = []  # title, name, value, hint, fg, bg
    rated = [p for p in team if p.period.classified >= 30 * 60 and p.period.productive_share is not None]
    if rated:
        best = max(rated, key=lambda p: p.period.productive_share or 0)
        cards.append(
            (
                "Most productive",
                best.name,
                f"{best.period.productive_share}%",
                "Needs 30+ min of classified time",
                "#0f766e",
                "#f0fdfa",
            )
        )
    idle = [p for p in team if p.day.idle >= 15 * 60]
    if idle:
        most = max(idle, key=lambda p: p.day.idle)
        cards.append(
            ("Most idle", most.name, duration(most.day.idle), "Shown at 15+ min idle", "#6d28d9", "#f5f3ff")
        )
    unproductive = [p for p in team if p.period.unproductive >= 10 * 60]
    if unproductive:
        most = max(unproductive, key=lambda p: p.period.unproductive)
        cards.append(
            (
                "Most unproductive",
                most.name,
                duration(most.period.unproductive),
                "Shown at 10+ min unproductive",
                "#c2410c",
                "#fff7ed",
            )
        )
    if slot == "evening":
        extra = [p for p in team if p.overtime >= 15 * 60]
        if extra:
            most = max(extra, key=lambda p: p.overtime)
            cards.append(
                (
                    "Extra time",
                    most.name,
                    f"+{duration(most.overtime)}",
                    "Shown at 15+ min over required",
                    "#3730a3",
                    "#eef2ff",
                )
            )
    if not cards:
        return ""
    cells = "".join(
        f'<td width="{100 // len(cards)}%" valign="top" style="padding:0 {6 if i < len(cards) - 1 else 0}px 0 0">'
        f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:separate;'
        f'background:{bg};border:1px solid {fg}40;border-radius:14px"><tr><td style="padding:14px 16px">'
        f'<div style="font-size:11px;font-weight:800;color:{fg};text-transform:uppercase;letter-spacing:.07em">{escape(t)}</div>'
        f'<div style="font-size:16px;font-weight:700;color:{INK};margin-top:6px">{escape(name)}</div>'
        f'<div style="font-size:24px;font-weight:800;color:{fg};margin-top:4px">{escape(value)}</div>'
        f'<div style="font-size:11.5px;color:{MUTED};margin-top:4px">{escape(hint)}</div>'
        "</td></tr></table></td>"
        for i, (t, name, value, hint, fg, bg) in enumerate(cards)
    )
    return (
        f'<div style="font-size:18px;font-weight:700;color:{INK};margin:4px 0 10px">At a glance</div>'
        f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr>{cells}</tr></table>'
    )


# ---------------------------------------------------------------------------------------------- team table
def _vs_avg(p: PersonReport) -> str:
    share = p.period.productive_share
    parts = []
    if share is not None and p.avg_share is not None:
        parts.append(f"Productive {_signed(share - p.avg_share, 'pts')}")
    if p.avg_idle is not None:
        parts.append(f"Idle {_signed(p.day.idle - p.avg_idle, 'time')}")
    return " · ".join(parts) if parts and p.started else "—"


def _role_heading(p: PersonReport, people: list[PersonReport], group: str) -> str | None:
    """'Manager' / 'Members' inside a department, when that department has a manager in the e-mail."""
    if p.is_self:
        return None
    same = [q for q in people if not q.is_self and (q.department or "No department") == group]
    bosses = [q for q in same if q.is_manager]
    if not bosses or len(bosses) == len(same):
        return None
    if p.is_manager:
        return "Managers" if len(bosses) > 1 else "Manager"
    return "Members"


def _table(people: list[PersonReport], slot: Slot, sections: set[str]) -> str:
    cols: list[str] = ["Person"]
    if "start_time" in sections:
        cols.append("Started")
    cols.append("Productive")
    if "focus" in sections:
        cols.append("Focus")
    if "long_breaks" in sections:
        cols.append("Long breaks")
    if slot == "evening" and "required_hours" in sections:
        cols.append("Required hours")
    if slot == "evening" and "average" in sections:
        cols.append("vs 7-day")
    th = (
        f"padding:10px 8px;font-size:11px;color:{MUTED};font-weight:600;text-align:left;"
        f"border-bottom:1px solid {LINE};background:#f8f9fc"
    )
    head = "".join(f'<th style="{th}">{c}</th>' for c in cols)
    rows = []
    groups = len({p.department or "No department" for p in people}) > 1
    current = None
    current_role: str | None = None
    td = f"padding:10px 8px;border-bottom:1px solid {LINE};font-size:12.5px;color:{INK};vertical-align:middle"
    for p in people:
        group = "You" if p.is_self else (p.department or "No department")
        if groups and group != current:
            rows.append(
                f'<tr><td colspan="{len(cols)}" style="padding:12px 8px 6px;font-size:11px;font-weight:800;'
                f'color:{BRAND};text-transform:uppercase;letter-spacing:.07em">'
                f"{'Your own figures' if p.is_self else escape(group)}</td></tr>"
            )
        if group != current:
            current, current_role = group, None
        role = _role_heading(p, people, group)
        if role and role != current_role:
            current_role = role
            rows.append(
                f'<tr><td colspan="{len(cols)}" style="padding:8px 8px 4px 14px;font-size:10.5px;font-weight:700;'
                f'color:{MUTED};text-transform:uppercase;letter-spacing:.06em">{role}</td></tr>'
            )
        name = escape(p.name) + (
            f'<div style="font-size:11px;color:{MUTED}">{escape(p.team)}</div>' if p.team else ""
        )
        cells = [
            f'<td style="{td}"><table role="presentation" cellspacing="0" cellpadding="0"><tr>'
            f'<td style="padding-right:8px">{_avatar(p.name)}</td><td style="font-weight:600;font-size:12.5px">{name}</td>'
            "</tr></table></td>"
        ]
        if "start_time" in sections:
            time_, ampm = _clock(p.first_in)
            cells.append(f'<td style="{td};white-space:nowrap">{time_} {ampm}</td>')
        share = p.period.productive_share
        bar = _bar(
            [(p.period.productive, TEAL), (p.period.neutral, GREY), (p.period.unproductive, ORANGE)], 6
        )
        cells.append(
            f'<td style="{td};min-width:110px"><table role="presentation" width="100%" cellspacing="0" cellpadding="0">'
            f'<tr><td style="font-weight:700;width:38px">{f"{share}%" if share is not None else "—"}</td>'
            f"<td>{bar if p.started else ''}</td></tr></table></td>"
        )
        if "focus" in sections:
            cells.append(
                f'<td style="{td};text-align:center">{p.period.focus_count if p.started else "—"}</td>'
            )
        if "long_breaks" in sections:
            cells.append(f'<td style="{td};text-align:center">{len(p.breaks) if p.started else "—"}</td>')
        if slot == "evening" and "required_hours" in sections:
            label, fg, bg = STATUS_BADGE.get(p.attendance or "", ("—", MUTED, "#f1f5f9"))
            cells.append(f'<td style="{td}">{_pill(label, fg, bg)}</td>')
        if slot == "evening" and "average" in sections:
            cells.append(f'<td style="{td};color:{MUTED};white-space:nowrap">{escape(_vs_avg(p))}</td>')
        rows.append(f'<tr style="background:{"#f0fdfa" if p.is_self else "#ffffff"}">{"".join(cells)}</tr>')
    legend = "".join(
        f'<span style="margin-left:12px;font-size:11.5px;color:{MUTED}"><span style="display:inline-block;width:9px;'
        f'height:9px;border-radius:3px;background:{c}"></span> {n}</span>'
        for n, c in (("Productive", TEAL), ("Neutral", GREY), ("Unproductive", ORANGE))
    )
    return (
        f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:separate;'
        f'background:#ffffff;border:1px solid {LINE};border-radius:14px;overflow:hidden">'
        f'<tr><td style="padding:16px 18px"><table role="presentation" width="100%" cellspacing="0" cellpadding="0">'
        f'<tr><td style="font-size:17px;font-weight:700;color:{INK}">Team</td><td align="right">{legend}</td></tr>'
        "</table></td></tr>"
        f'<tr><td><div style="overflow-x:auto"><table role="presentation" width="100%" cellspacing="0" cellpadding="0" '
        f'style="border-collapse:collapse"><tr>{head}</tr>{"".join(rows)}</table></div></td></tr></table>'
    )


# ---------------------------------------------------------------------------------------------- this week vs last week
def _arrow(delta: float, good_when_up: bool, text: str) -> str:
    if abs(delta) < 1e-9:
        return f'<span style="color:{MUTED};font-weight:700">= {escape(text)}</span>'
    up = delta > 0
    good = up == good_when_up
    color = "#15803d" if good else "#b91c1c"
    return f'<span style="color:{color};font-weight:700">{"▲" if up else "▼"} {escape(text)}</span>'


def _weekly(people: list[PersonReport]) -> str:
    """Week so far (Monday to today) against the same days last week: the team, and who moved most."""
    team = [p for p in _team(people) if p.this_week is not None]
    compared = [p for p in team if p.last_week is not None]
    if not compared:
        return _card(
            _section_title("This week vs last week")
            + f'<div style="font-size:13px;color:{MUTED};margin-top:8px">No activity recorded last week yet — the '
            "comparison starts once there is a week of history.</div>"
        )
    this, last = Figures(), Figures()
    for p in compared:
        this = this.plus(p.this_week or Figures())
        last = last.plus(p.last_week or Figures())
    tiles = []
    now_s, then_s = this.productive_share, last.productive_share
    if now_s is not None and then_s is not None:
        tiles.append(
            (
                "Productive %",
                f"{now_s}%",
                _arrow(now_s - then_s, True, f"{abs(now_s - then_s)} pts vs {then_s}%"),
            )
        )
    tiles.append(
        (
            "Idle time",
            duration(this.idle),
            _arrow(
                this.idle - last.idle,
                False,
                f"{duration(abs(this.idle - last.idle))} vs {duration(last.idle)}",
            ),
        )
    )
    tiles.append(
        (
            "Unproductive time",
            duration(this.unproductive),
            _arrow(
                this.unproductive - last.unproductive,
                False,
                f"{duration(abs(this.unproductive - last.unproductive))} vs {duration(last.unproductive)}",
            ),
        )
    )
    tile_cells = "".join(
        f'<td width="{100 // len(tiles)}%" valign="top" style="padding:0 {6 if i < len(tiles) - 1 else 0}px 0 0">'
        f'<div style="background:#f8f9fc;border:1px solid {LINE};border-radius:12px;padding:12px 14px">'
        f'<div style="font-size:12px;color:{MUTED}">{escape(label)} · this week</div>'
        f'<div style="font-size:22px;font-weight:800;color:{INK};margin-top:4px">{escape(value)}</div>'
        f'<div style="font-size:12px;margin-top:4px">{change}</div></div></td>'
        for i, (label, value, change) in enumerate(tiles)
    )
    moves = []
    for p in compared:
        a, b = (p.this_week or Figures()).productive_share, (p.last_week or Figures()).productive_share
        if a is not None and b is not None and a != b:
            moves.append((a - b, p.name, a, b))
    ups = sorted((m for m in moves if m[0] > 0), reverse=True)[:3]
    downs = sorted(m for m in moves if m[0] < 0)[:3]

    def listing(title: str, rows: list[tuple[int, str, int, int]], color: str, mark: str) -> str:
        items = (
            "".join(
                f'<div style="padding:6px 0;border-top:1px solid {LINE};font-size:13px;color:{INK}">'
                f'<span style="color:{color};font-weight:700">{mark} {"+" if d > 0 else "-"}{abs(d)} pts</span>&nbsp; '
                f'{escape(name)} <span style="color:{MUTED}">({now}% vs {then}%)</span></div>'
                for d, name, now, then in rows
            )
            or f'<div style="padding:6px 0;font-size:13px;color:{MUTED}">None.</div>'
        )
        return f'<div style="font-size:12px;font-weight:800;color:{color};text-transform:uppercase;letter-spacing:.06em">{title}</div>{items}'

    movers = (
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin-top:12px"><tr>'
        f'<td width="50%" valign="top" style="padding-right:8px">{listing("Most improved", ups, "#15803d", "▲")}</td>'
        f'<td width="50%" valign="top" style="padding-left:8px">{listing("Biggest drops", downs, "#b91c1c", "▼")}</td>'
        "</tr></table>"
    )
    return _card(
        _section_title("This week vs last week", "Monday to today, same days last week")
        + f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin-top:10px"><tr>{tile_cells}</tr></table>'
        + movers
    )


# ---------------------------------------------------------------------------------------------- required hours today
def _required(people: list[PersonReport]) -> str:
    team = [p for p in _team(people) if p.expected]
    if not team:
        return ""
    order = {"short": 0, "absent": 1, "met": 2}
    rows = []
    for p in sorted(team, key=lambda p: (order.get(p.attendance or "", 3), p.name.lower())):
        label, fg, bg = STATUS_BADGE.get(p.attendance or "", ("—", MUTED, "#f1f5f9"))
        gap = p.attended_active - p.expected
        if p.attendance == "met":
            detail = f"{duration(p.attended_active)} of {duration(p.expected)}" + (
                f" · +{duration(gap)}" if gap >= 60 else ""
            )
        elif p.attendance == "absent":
            detail = f"No activity · {duration(p.expected)} required"
        else:
            detail = f"{duration(p.attended_active)} of {duration(p.expected)} · {duration(-gap)} short"
        mark = "✓" if p.attendance == "met" else "✗"
        rows.append(
            f'<tr><td style="padding:9px 0;border-top:1px solid {LINE};font-size:13px;font-weight:600;color:{INK}">'
            f'<span style="color:{fg}">{mark}</span>&nbsp; {escape(p.name)}</td>'
            f'<td style="padding:9px 0;border-top:1px solid {LINE};font-size:12.5px;color:{MUTED}">{escape(detail)}</td>'
            f'<td align="right" style="padding:9px 0;border-top:1px solid {LINE}">{_pill(label, fg, bg)}</td></tr>'
        )
    met = sum(1 for p in team if p.attendance == "met")
    return _card(
        _section_title("Required hours today", f"{met} of {len(team)} met their day")
        + f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin-top:10px">{"".join(rows)}</table>'
    )


# ---------------------------------------------------------------------------------------------- person cards
def _rows(lines: list[tuple[str, str]]) -> str:
    return "".join(
        f'<tr><td valign="top" style="padding:6px 8px 6px 0;border-top:1px solid {LINE};font-size:12px;'
        f'color:{MUTED};white-space:nowrap">{escape(k)}</td>'
        f'<td align="right" style="padding:6px 0;border-top:1px solid {LINE};font-size:12px;font-weight:700;'
        f'color:{INK}">{_plain(v)}</td></tr>'
        for k, v in lines
    )


def _block(title: str, inner: str) -> str:
    return (
        f'<div style="margin-top:12px;font-size:10.5px;font-weight:800;color:{BRAND};letter-spacing:.08em;'
        f'text-transform:uppercase">{title}</div>{inner}'
    )


def _required_line(p: PersonReport) -> str:
    """'7h 20m · Met (+33m)' with the status pill."""
    label, fg, bg = STATUS_BADGE.get(p.attendance or "", ("", MUTED, "#f1f5f9"))
    if not p.expected or not label:
        return ""
    gap = p.attended_active - p.expected
    extra = f" (+{duration(gap)})" if p.attendance == "met" and gap >= 60 else (
        f" (-{duration(-gap)})" if p.attendance == "short" and gap < 0 else ""
    )
    return (
        f'<tr><td style="padding:8px 8px 8px 0;border-top:1px solid {LINE};font-size:12px;color:{MUTED};'
        f'white-space:nowrap">Required hours</td>'
        f'<td align="right" style="padding:8px 0;border-top:1px solid {LINE};font-size:12px;font-weight:700;'
        f'color:{INK};white-space:nowrap">{duration(p.expected)}&nbsp; {_pill(label + extra, fg, bg)}</td></tr>'
    )


def _person_card(p: PersonReport, sections: set[str], slot: Slot) -> str:
    blocks = []
    # Productivity: every category with its share of all app/website time, adding up to the total.
    if "categories" in sections or "productive_share" in sections:
        extra: list[tuple[str, str]] = []
        if "focus" in sections:
            extra.append(("Focus sessions", str(p.period.focus_count)))
        if "customer_time" in sections:
            extra.append(("Customer time", duration(p.period.customer)))
        for u in p.low_activity():
            extra.append(("⚠ Low input", f"{u.name}: {duration(u.seconds)} open, keyboard/mouse {u.input_share}%"))
        blocks.append(
            _block(
                "Productivity",
                category_table(p.period, size=12, pad=5)
                + (f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0">{_rows(extra)}</table>'
                   if extra else ""),
            )
        )
    # Attendance: when they worked, active vs idle, and whether the required hours were met.
    attendance = attendance_rows(p, sections, slot)
    required = _required_line(p) if slot == "evening" and "required_hours" in sections else ""
    if attendance or required:
        blocks.append(
            _block(
                "Attendance",
                f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin-top:4px">'
                f"{_rows(attendance)}{required}</table>",
            )
        )
    # This week, and other figures chosen in Content.
    week: list[tuple[str, str]] = []
    if "week" in sections and p.week_active is not None:
        week.append(
            (
                "Week so far",
                duration(p.week_active)
                + (f" of {duration(p.week_expected)} · {p.week_met} of {p.week_days} days met" if p.week_expected else ""),
            )
        )
    if "week_compare" in sections and p.this_week is not None and p.last_week is not None:
        a, b = p.this_week.productive_share, p.last_week.productive_share
        if a is not None and b is not None:
            week.append(("vs last week", f"Productive {_signed(a - b, 'pts')}"))
    if slot == "evening" and "average" in sections:
        week.append(("vs 7-day average", _vs_avg(p)))
    if "meetings" in sections:
        week.append(("Meetings", duration(p.meetings)))
    if "tasks" in sections:
        week.append(("Task time", duration(p.period.task)))
    if "screenshots" in sections:
        week.append(("Screenshots", str(p.screenshots)))
    if week:
        blocks.append(
            _block(
                "This week",
                f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin-top:4px">'
                f"{_rows(week)}</table>",
            )
        )
    apps = ""
    if "top_apps" in sections and p.top(4):
        apps = (
            '<div style="margin-top:10px">'
            + "".join(
                f'<span style="display:inline-block;margin:2px 4px 2px 0;padding:2px 8px;border-radius:999px;'
                f'border:1px solid {LINE};font-size:11px;color:{INK}">{_plain(u.name)} · {duration(u.seconds)}</span>'
                for u in p.top(4)
            )
            + "</div>"
        )
    note = (
        f'<div style="font-size:12px;color:{INK};margin-top:10px;line-height:1.45">{_plain(p.note)}</div>'
        if "summary" in sections and p.note
        else ""
    )
    return (
        f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:separate;'
        f'background:#ffffff;border:1px solid {LINE};border-radius:14px;overflow:hidden">'
        f'<tr><td style="background:#0f766e;padding:12px 14px"><table role="presentation" cellspacing="0" cellpadding="0"><tr>'
        f'<td style="padding-right:10px">{_avatar(p.name, 34)}</td><td>'
        f'<div style="font-size:10.5px;font-weight:800;color:#99f6e4;letter-spacing:.07em;text-transform:uppercase">'
        f"{'Your own figures' if p.is_self else escape(p.department or 'Person')}</div>"
        f'<div style="font-size:15px;font-weight:800;color:#ffffff">{escape(p.name)}</div></td></tr></table></td></tr>'
        f'<tr><td style="padding:2px 14px 14px">{"".join(blocks)}{apps}{note}</td></tr></table>'
    )


def _group_of(p: PersonReport) -> str:
    return "Your own figures" if p.is_self else (p.department or "No department")


def _cards(people: list[PersonReport], sections: set[str], slot: Slot) -> str:
    """Person cards, two per row, under a heading per department (and "Your own figures" first)."""
    groups: list[tuple[str, list[PersonReport]]] = []
    for p in people:
        if not groups or groups[-1][0] != _group_of(p):
            groups.append((_group_of(p), []))
        groups[-1][1].append(p)
    headed = len(groups) > 1
    rows = []
    for name, members in groups:
        if headed:
            rows.append(
                f'<tr><td colspan="2" style="padding:6px 0 8px;font-size:12px;font-weight:800;color:{BRAND};'
                f'text-transform:uppercase;letter-spacing:.07em">{escape(name)}</td></tr>'
            )
        # Managers first, then members (each under its own small heading when the department has a manager).
        parts: list[tuple[str | None, list[PersonReport]]] = []
        for p in members:
            role = _role_heading(p, people, _group_of(p) if not p.is_self else "You")
            if not parts or parts[-1][0] != role:
                parts.append((role, []))
            parts[-1][1].append(p)
        for role, part in parts:
            if role:
                rows.append(
                    f'<tr><td colspan="2" style="padding:2px 0 8px;font-size:10.5px;font-weight:700;color:{MUTED};'
                    f'text-transform:uppercase;letter-spacing:.06em">{role}</td></tr>'
                )
            cards = [_person_card(p, sections, slot) for p in part]
            for i in range(0, len(cards), 2):
                pair = cards[i : i + 2]
                cells = "".join(
                    f'<td width="50%" valign="top" style="padding:0 {6 if k == 0 else 0}px 12px {6 if k == 1 else 0}px">{c}</td>'
                    for k, c in enumerate(pair)
                ) + ('<td width="50%"></td>' if len(pair) == 1 else "")
                rows.append(f"<tr>{cells}</tr>")
    return (
        f'<div style="font-size:18px;font-weight:700;color:{INK};margin:4px 0 10px">Person cards</div>'
        f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0">{"".join(rows)}</table>'
    )


def _by_department(people: list[PersonReport], slot: Slot, sections: set[str]) -> str:
    """One row per department when the e-mail covers more than one (a manager over several departments)."""
    team = _team(people)
    names = sorted(
        {p.department or "No department" for p in team}, key=lambda d: (d == "No department", d.lower())
    )
    if len(names) < 2:
        return ""
    evening = slot == "evening" and "required_hours" in sections
    head = (
        ["Department", "People", "Productive"]
        + (["Met", "Short", "Absent"] if evening else ["Started"])
        + ["Focus"]
    )
    th = f"padding:9px 8px;font-size:11px;color:{MUTED};font-weight:600;text-align:left;border-bottom:1px solid {LINE}"
    td = f"padding:9px 8px;border-bottom:1px solid {LINE};font-size:12.5px;color:{INK}"
    rows = []
    for name in names:
        members = [p for p in team if (p.department or "No department") == name]
        productive = sum(p.period.productive for p in members)
        classified = sum(p.period.classified for p in members)
        share = f"{round(100 * productive / classified)}%" if classified >= 60 else "—"
        cells = [
            f'<td style="{td};font-weight:700">{escape(name)}</td>',
            f'<td style="{td}">{len(members)}</td>',
        ]
        cells.append(f'<td style="{td};font-weight:700;color:#0f766e">{share}</td>')
        if evening:
            with_target = [p for p in members if p.expected]
            met = sum(1 for p in with_target if p.attendance == "met")
            cells += [
                f'<td style="{td};color:#15803d;font-weight:700">{met} / {len(with_target)}</td>',
                f'<td style="{td};color:#b45309;font-weight:700">{sum(1 for p in members if p.attendance == "short")}</td>',
                f'<td style="{td};color:#b91c1c;font-weight:700">{sum(1 for p in members if p.attendance == "absent")}</td>',
            ]
        else:
            cells.append(f'<td style="{td}">{sum(1 for p in members if p.started)} / {len(members)}</td>')
        cells.append(f'<td style="{td}">{sum(p.period.focus_count for p in members)}</td>')
        rows.append(f"<tr>{''.join(cells)}</tr>")
    return _card(
        _section_title("By department", f"{len(names)} departments")
        + '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin-top:8px;'
        f'border-collapse:collapse"><tr>{"".join(f"<th style={chr(34)}{th}{chr(34)}>{h}</th>" for h in head)}</tr>'
        f"{''.join(rows)}</table>"
    )


# ---------------------------------------------------------------------------------------------- summary lines
def _summary_lines(people: list[PersonReport], slot: Slot) -> str:
    items: list[tuple[str, str, str, str]] = []
    for p in _team(people):
        if p.period.unproductive >= NOTABLE_UNPRODUCTIVE:
            worst = p.top(1, "unproductive")
            where = f", mostly {worst[0].name}" if worst else ""
            items.append(
                (p.name, f"{duration(p.period.unproductive)} unproductive today{where}", "#c2410c", "#fff7ed")
            )
        if slot == "evening" and p.avg_active and p.started and p.day.active < BELOW_AVERAGE * p.avg_active:
            items.append(
                (
                    p.name,
                    f"Active {duration(p.day.active)}, below 70% of the 7-day average ({duration(p.avg_active)})",
                    "#6d28d9",
                    "#f5f3ff",
                )
            )
    if not items:
        return ""
    rows = "".join(
        f'<tr><td style="padding:4px 0"><table role="presentation" width="100%" cellspacing="0" cellpadding="0" '
        f'style="border-collapse:separate;background:{bg};border:1px solid {fg}40;border-radius:12px"><tr>'
        f'<td width="34" style="padding:12px 0 12px 14px;color:{fg};font-size:15px">&#9432;</td>'
        f'<td style="padding:12px 14px 12px 6px"><div style="font-size:13px;font-weight:700;color:{INK}">{escape(name)}</div>'
        f'<div style="font-size:12.5px;color:#3a3d4d;margin-top:2px">{_plain(text)}</div></td></tr></table></td></tr>'
        for name, text, fg, bg in items
    )
    return _card(
        _section_title("Summary lines", "20+ min unproductive, or below 70% of 7-day average")
        + f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin-top:8px">{rows}</table>'
    )


def _actions(people: list[PersonReport], link: str) -> str:
    todo = action_items(_team(people))
    if not todo:
        return ""
    lis = "".join(f'<li style="margin:3px 0">{escape(t)}</li>' for t in todo)
    return (
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:separate;'
        'background:#fffbeb;border:1px solid #fcd34d;border-radius:14px"><tr><td style="padding:14px 18px">'
        '<div style="font-size:11px;font-weight:800;color:#92400e;text-transform:uppercase;letter-spacing:.07em">'
        "Needs your action</div>"
        f'<ul style="margin:6px 0 4px;padding-left:18px;font-size:13px;color:{INK}">{lis}</ul>'
        f'<a href="{escape(link)}" style="font-size:12px;color:{BRAND};font-weight:600">Open in WorkPulse</a>'
        "</td></tr></table>"
    )


# ---------------------------------------------------------------------------------------------- the e-mail
def team_html(
    *,
    company_name: str,
    recipient_name: str,
    people: list[PersonReport],
    summary: Summary,
    slot: Slot,
    day: date,
    period: str,
    sections: Collection[str],
    actions_link: str,
    test: bool = False,
) -> str:
    chosen = set(sections)
    first = recipient_name.split(" ")[0] or recipient_name
    report = "Mid-day" if slot == "midday" else "Evening"
    gap = '<tr><td style="height:16px;font-size:0;line-height:0">&nbsp;</td></tr>'
    parts = [_tiles(people, slot, chosen)]
    if "summary" in chosen and summary.overview:
        source = "Written by AI from the figures" if summary.by_ai else "Written from the figures"
        parts.append(
            _card(
                _section_title("Team summary", f"✦ {source}")
                + f'<div style="font-size:14px;color:{INK};line-height:1.6;margin-top:10px">{_plain(summary.overview)}</div>'
            )
        )
    if "highlights" in chosen:
        parts.append(_glance(people, slot))
    if "action_items" in chosen:
        parts.append(_actions(people, actions_link))
    parts.append(_by_department(people, slot, chosen))
    parts.append(_table(people, slot, chosen))
    if slot == "evening" and "required_hours" in chosen:
        parts.append(_required(people))
    if "week_compare" in chosen:
        parts.append(_weekly(people))
    parts.append(_cards(people, chosen, slot))
    if "summary" in chosen:
        parts.append(_summary_lines(people, slot))
    body = gap.join(f"<tr><td>{x}</td></tr>" for x in parts if x)
    banner = (
        '<tr><td style="padding:0 0 12px"><div style="background:#fff7e6;border:1px solid #f5d18a;color:#8a5a00;'
        'padding:8px 12px;border-radius:8px;font-size:12px">Test e-mail — sent on request from Settings; managers '
        "were not e-mailed.</div></td></tr>"
        if test
        else ""
    )
    return f"""<!doctype html>
<html><body style="margin:0;padding:0;background:#f3f4f8;font-family:{FONT}">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f3f4f8"><tr><td align="center"
  style="padding:24px 10px">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:760px">
  {banner}
  <tr><td style="background:#111827;border-radius:16px 16px 0 0;padding:22px 24px">
    <div style="font-size:11px;font-weight:800;color:#5eead4;text-transform:uppercase;letter-spacing:.08em">
      {report} report · {escape(company_name)}</div>
    <div style="font-size:24px;font-weight:800;color:#ffffff;margin-top:6px">{escape(_title(people))}</div>
    <div style="font-size:13px;color:#cbd5e1;margin-top:4px">Hi {escape(first)} · {escape(day_label(day))} · covers
      {escape(period)}</div>
  </td></tr>
  <tr><td style="background:#f8f9fc;border:1px solid {LINE};border-top:0;border-radius:0 0 16px 16px;padding:16px">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0">{body}</table>
    <p style="margin:16px 4px 0;font-size:11px;color:#8a8ea0;line-height:1.5">{FOOTNOTE} You receive this e-mail
      because your WorkPulse administrator set up automatic reports (Settings → Automatic reports).</p>
  </td></tr>
</table></td></tr></table></body></html>"""
