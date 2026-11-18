"""An employee's own report e-mail ("Your evening report"): tiles, where the time went, focus sessions, long breaks,
the summary and — in the evening — whether today's required hours were met.

Built with tables and inline styles only, so it looks the same in Gmail, Outlook and phone mail apps. What appears
follows the employee's content choices (Settings → Automatic reports → Employee reports). Only the person's own
figures; no window titles, no screenshots.
"""

from __future__ import annotations

from collections.abc import Collection
from datetime import date, datetime
from html import escape

from app.services.auto_reports.figures import PersonReport, Slot, day_label, duration
from app.services.auto_reports.render import FOOTNOTE, Digest, _plain

INK = "#151826"
MUTED = "#646878"
LINE = "#e6e8ef"
BRAND = "#4f46e5"
TEAL = "#14b8a6"
GREY = "#9aa0b4"
ORANGE = "#f97316"
VIOLET = "#8b5cf6"
GREEN = "#16a34a"
AMBER = "#d97706"
RED = "#dc2626"
FONT = "Inter,Segoe UI,Roboto,Helvetica,Arial,sans-serif"


def _clock(at: datetime | None) -> tuple[str, str]:
    """("9:12", "AM")."""
    if at is None:
        return "—", ""
    return at.strftime("%I:%M").lstrip("0"), at.strftime("%p")


def _span(a: datetime, b: datetime) -> str:
    return f"{a:%H:%M} - {b:%H:%M}"


def _pct(part: float, whole: float) -> int:
    return max(0, min(100, round(100 * part / whole))) if whole > 0 else 0


def _bar(segments: list[tuple[float, str]], height: int = 8, track: bool = False) -> str:
    """A horizontal bar made of coloured table cells (works in every mail app)."""
    total = sum(v for v, _ in segments)
    cells = "".join(
        f'<td width="{max(1, _pct(v, total))}%" style="background:{c};height:{height}px;font-size:0;line-height:0">&nbsp;</td>'
        for v, c in segments
        if v > 0
    )
    if not cells:
        cells = f'<td style="background:{LINE};height:{height}px;font-size:0;line-height:0">&nbsp;</td>'
    radius = f"border-radius:{height}px;overflow:hidden;" if not track else ""
    return (
        f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" '
        f'style="border-collapse:collapse;{radius}"><tr>{cells}</tr></table>'
    )


def _progress(value: float, whole: float, color: str) -> str:
    width = _pct(value, whole)
    rest = 100 - width
    filled = (
        f'<td width="{width}%" style="background:{color};height:8px;border-radius:8px;font-size:0">&nbsp;</td>'
        if width
        else ""
    )
    empty = f'<td width="{rest}%" style="height:8px;font-size:0">&nbsp;</td>' if rest else ""
    return (
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" '
        f'style="border-collapse:separate;background:#eef0f5;border-radius:8px"><tr>{filled}{empty}</tr></table>'
    )


def _card(inner: str, pad: str = "18px 20px") -> str:
    return (
        f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:separate;'
        f'background:#ffffff;border:1px solid {LINE};border-radius:14px"><tr><td style="padding:{pad}">{inner}'
        "</td></tr></table>"
    )


def _label(text: str, badge: str = "") -> str:
    return f'<div style="font-size:13px;color:{MUTED};font-weight:500">{escape(text)}{badge}</div>'


def _badge(text: str, fg: str, bg: str) -> str:
    return (
        f' <span style="display:inline-block;margin-left:6px;padding:2px 8px;border-radius:999px;font-size:11px;'
        f'font-weight:700;color:{fg};background:{bg}">{escape(text)}</span>'
    )


def _hint(text: str) -> str:
    return f'<div style="font-size:12px;color:{MUTED};margin-top:8px;line-height:1.45">{escape(text)}</div>'


def _signed(value: float, unit: str) -> str:
    sign = "+" if value >= 0 else "-"
    return f"{sign}{abs(round(value))} {unit}" if unit == "pts" else f"{sign}{duration(abs(value))}"


# ---------------------------------------------------------------------------------------------- tiles
def _tile_productive(p: PersonReport) -> str:
    share = p.period.productive_share
    big = f"{share}%" if share is not None else "—"
    return (
        _label("Productive %")
        + f'<div style="font-size:34px;font-weight:700;color:#0f766e;margin:8px 0 10px">{big}</div>'
        + _bar([(p.period.productive, TEAL), (p.period.neutral, GREY), (p.period.unproductive, ORANGE)])
        + _hint("Productive ÷ (Productive + Neutral + Unproductive)")
    )


def _tile_started(p: PersonReport) -> str:
    time_, ampm = _clock(p.first_in)
    return (
        _label("Started")
        + f'<div style="font-size:34px;font-weight:700;color:#312e81;margin:8px 0 4px">{time_}'
        + (f' <span style="font-size:15px;font-weight:600">{ampm}</span>' if ampm else "")
        + "</div>"
        + _hint("First app or website activity")
    )


_DAY_COLORS = {"met": GREEN, "short": AMBER, "absent": RED}


def _tile_week(p: PersonReport) -> str:
    if p.week_active is None:
        return _label("Required hours · this week") + '<div style="font-size:26px;margin-top:8px">—</div>'
    if p.week_expected:
        state = (
            ("Met", GREEN, "#dcfce7")
            if p.week_active >= p.week_expected
            else ("Short", "#92400e", "#fef3c7")
            if any(s == "short" for s in p.week_statuses)
            else ("On track", BRAND, "#eef2ff")
        )
        value = f'{duration(p.week_active)} <span style="color:{GREY};font-weight:500">/ {duration(p.week_expected)}</span>'
        badge = _badge(*state)
    else:
        value, badge = duration(p.week_active), ""
    pills = "".join(
        f'<td style="padding-right:4px"><div style="height:6px;border-radius:6px;background:'
        f'{_DAY_COLORS.get(s, "#d4d7e2")}">&nbsp;</div></td>'
        for s in p.week_statuses
    )
    return (
        _label("Required hours · this week", badge)
        + f'<div style="font-size:24px;font-weight:700;color:{INK};margin:8px 0 10px;line-height:1.2">{value}</div>'
        + (
            f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr>{pills}</tr></table>'
            if pills
            else ""
        )
        + _hint(f"{p.week_met} of {p.week_days} days met" if p.week_expected else "No required hours set")
    )


def _tile_average(p: PersonReport) -> str:
    share = p.period.productive_share
    rows = []
    if share is not None and p.avg_share is not None:
        better = share >= p.avg_share
        rows.append(
            (
                f"Prod {_signed(share - p.avg_share, 'pts')}",
                "#0f766e" if better else "#b91c1c",
                "#ccfbf1" if better else "#fee2e2",
            )
        )
    if p.avg_idle is not None:
        rows.append((f"Idle {_signed(p.day.idle - p.avg_idle, 'time')}", "#6d28d9", "#ede9fe"))
    pills = (
        "".join(
            f'<div style="margin-top:8px"><span style="display:inline-block;padding:6px 12px;border-radius:10px;'
            f'font-size:18px;font-weight:700;color:{fg};background:{bg}">{escape(t)}</span></div>'
            for t, fg, bg in rows
        )
        or f'<div style="font-size:26px;margin-top:8px;color:{GREY}">—</div>'
    )
    return _label("vs your 7-day average") + pills + _hint("Shows “—” until you have activity history")


def _tiles(p: PersonReport, sections: Collection[str]) -> str:
    tiles = []
    if "productive_share" in sections:
        tiles.append(_tile_productive(p))
    if "start_time" in sections:
        tiles.append(_tile_started(p))
    if "week" in sections or "required_hours" in sections:
        tiles.append(_tile_week(p))
    if "average" in sections or "week_compare" in sections:
        tiles.append(_tile_average(p))
    if not tiles:
        return ""
    rows = []
    for i in range(0, len(tiles), 2):
        pair = tiles[i : i + 2]
        cells = "".join(
            f'<td width="50%" valign="top" style="padding:0 {6 if k == 0 else 0}px 12px {6 if k == 1 else 0}px">{_card(t)}</td>'
            for k, t in enumerate(pair)
        ) + ('<td width="50%" style="padding:0 0 12px 6px"></td>' if len(pair) == 1 else "")
        rows.append(f"<tr>{cells}</tr>")
    return f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0">{"".join(rows)}</table>'


# ---------------------------------------------------------------------------------------------- sections
def _section_title(text: str, right: str = "") -> str:
    return (
        '<table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr>'
        f'<td style="font-size:17px;font-weight:700;color:{INK}">{text}</td>'
        f'<td align="right" style="font-size:12px;color:{MUTED}">{right}</td></tr></table>'
    )


def _required_today(p: PersonReport) -> str:
    if not p.expected:
        return _card(
            _section_title("Today&rsquo;s required hours")
            + f'<div style="font-size:14px;color:{MUTED};margin-top:8px">No required hours today · '
            f"{duration(p.attended_active)} active</div>"
        )
    met = p.attendance == "met"
    gap = p.attended_active - p.expected
    if met:
        head, color, bg = "✓ Met", GREEN, "#f0fdf4"
        detail = f"{duration(p.attended_active)} active of {duration(p.expected)}" + (
            f" · +{duration(gap)} extra" if gap >= 60 else ""
        )
    elif p.attendance == "absent":
        head, color, bg = "✗ Not met — no activity today", RED, "#fef2f2"
        detail = f"0m active of {duration(p.expected)}"
    else:
        head, color, bg = "✗ Not met", RED, "#fef2f2"
        detail = f"{duration(p.attended_active)} active of {duration(p.expected)} · {duration(-gap)} short"
    return (
        f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:separate;'
        f'background:{bg};border:1px solid {color}33;border-radius:14px"><tr><td style="padding:16px 20px">'
        f'<div style="font-size:12px;font-weight:700;color:{MUTED};text-transform:uppercase;letter-spacing:.06em">'
        "Today&rsquo;s required hours</div>"
        f'<div style="font-size:22px;font-weight:800;color:{color};margin-top:6px">{escape(head)}</div>'
        f'<div style="font-size:14px;color:{INK};margin-top:4px">{escape(detail)}</div>'
        f'<div style="margin-top:10px">{_progress(p.attended_active, max(p.expected, p.attended_active), color)}</div>'
        "</td></tr></table>"
    )


def _summary(text: str, by_ai: bool) -> str:
    source = "Written by AI from your figures" if by_ai else "Written from your figures"
    return _card(
        _section_title("Your day in brief", f"✦ {source}")
        + f'<div style="font-size:14px;color:{INK};line-height:1.6;margin-top:10px">{_plain(text)}</div>'
    )


def _where(p: PersonReport) -> str:
    rows = [
        ("Productive", p.period.productive, TEAL),
        ("Neutral", p.period.neutral, GREY),
        ("Unproductive", p.period.unproductive, ORANGE),
        ("Idle", p.period.idle, VIOLET),
    ]
    total = sum(v for _, v, _ in rows)
    top = max((v for _, v, _ in rows), default=0)
    body = "".join(
        f'<tr><td style="padding:7px 0;width:120px;font-size:13px;color:{INK};white-space:nowrap">'
        f'<span style="display:inline-block;width:9px;height:9px;border-radius:3px;background:{c};margin-right:8px">'
        f"</span>{name}</td>"
        f'<td width="62%" style="padding:7px 12px">{_progress(v, top, c)}</td>'
        f'<td align="right" style="padding:7px 0;font-size:13px;font-weight:700;color:{INK};white-space:nowrap">'
        f"{duration(v)}</td></tr>"
        for name, v, c in rows
    )
    return _card(
        _section_title("Where your time went", f"{duration(total)} tracked")
        + f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin-top:8px">{body}'
        "</table>"
    )


def _list_card(
    count: int, title: str, hint: str, items: list[tuple[datetime, datetime, float]], fg: str, bg: str
) -> str:
    rows = (
        "".join(
            f'<tr><td style="padding:4px 0"><table role="presentation" width="100%" cellspacing="0" cellpadding="0" '
            f'style="border-collapse:separate;background:{bg};border-radius:10px"><tr>'
            f'<td style="padding:9px 12px;font-size:13px;color:{fg}">{_span(a, b)}</td>'
            f'<td align="right" style="padding:9px 12px;font-size:13px;font-weight:700;color:{fg}">{duration(s)}</td>'
            "</tr></table></td></tr>"
            for a, b, s in items
        )
        or f'<tr><td style="font-size:13px;color:{MUTED};padding:6px 0">None today.</td></tr>'
    )
    return _card(
        f'<div style="font-size:17px;font-weight:700;color:{INK}"><span style="color:{fg};font-size:22px">{count}'
        f"</span>&nbsp; {title}</div>"
        + f'<div style="font-size:12px;color:{MUTED};margin:6px 0 8px">{hint}</div>'
        + f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0">{rows}</table>'
    )


def _focus_and_breaks(p: PersonReport, sections: Collection[str]) -> str:
    cards = []
    if "focus" in sections:
        cards.append(
            _list_card(
                len(p.focus_list),
                "Focus sessions",
                "25+ min of work with no pause over 2 min and no more than 1 min Unproductive.",
                p.focus_list,
                "#0f766e",
                "#f0fdfa",
            )
        )
    if "long_breaks" in sections:
        cards.append(
            _list_card(
                len(p.breaks),
                "Long breaks",
                "Idle stretches of 15 minutes or more.",
                p.breaks,
                "#6d28d9",
                "#f5f3ff",
            )
        )
    if not cards:
        return ""
    cells = "".join(
        f'<td width="{100 // len(cards)}%" valign="top" '
        f'style="padding:0 {6 if k == 0 and len(cards) > 1 else 0}px 0 {6 if k == 1 else 0}px">{c}</td>'
        for k, c in enumerate(cards)
    )
    return f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0"><tr>{cells}</tr></table>'


_CATEGORY_COLORS = {"productive": GREEN, "neutral": AMBER, "unproductive": RED}


def _apps(p: PersonReport) -> str:
    chips = (
        "".join(
            f'<span style="display:inline-block;margin:3px 6px 3px 0;padding:4px 10px;border-radius:999px;'
            f'border:1px solid {LINE};font-size:12px;color:{INK}"><span style="color:'
            f'{_CATEGORY_COLORS.get(u.category, GREY)}">●</span> {_plain(u.name)} · {duration(u.seconds)}</span>'
            for u in p.top(8)
        )
        or f'<span style="font-size:13px;color:{MUTED}">No app or website activity recorded.</span>'
    )
    return _card(_section_title("Top apps &amp; websites") + f'<div style="margin-top:10px">{chips}</div>')


def _more(p: PersonReport, sections: Collection[str], slot: Slot) -> str:
    rows: list[tuple[str, str]] = []
    if "start_time" in sections and p.sessions:
        rows.append(("Signed in", " · ".join(s.label() for s in p.sessions)))
    if "last_sign_out" in sections:
        rows.append(("Last sign-out", p.last_out))
    if "late_start" in sections and p.late_by:
        rows.append(("Late start", duration(p.late_by)))
    if "active_idle" in sections:
        rows.append(("Active time", duration(p.period.active)))
    if "meetings" in sections:
        rows.append(("Meetings", duration(p.meetings)))
    if "customer_time" in sections:
        rows.append(("Customer time", duration(p.period.customer)))
    if "tasks" in sections:
        rows.append(("Task time", duration(p.period.task)))
    if "screenshots" in sections:
        rows.append(("Screenshots", str(p.screenshots)))
    if slot == "evening" and "overtime" in sections and p.overtime >= 60:
        rows.append(("Extra time", f"+{duration(p.overtime)}"))
    if "week_compare" in sections and p.this_week is not None and p.last_week is not None:
        now_s, then_s = p.this_week.productive_share, p.last_week.productive_share
        if now_s is not None and then_s is not None:
            rows.append(
                (
                    "vs last week",
                    f"Prod {_signed(now_s - then_s, 'pts')} · Idle {_signed(p.this_week.idle - p.last_week.idle, 'time')}",
                )
            )
    if not rows:
        return ""
    body = "".join(
        f'<tr><td style="padding:9px 0;border-top:1px solid {LINE};font-size:13px;color:{MUTED}">{escape(k)}</td>'
        f'<td align="right" style="padding:9px 0;border-top:1px solid {LINE};font-size:13px;font-weight:700;'
        f'color:{INK}">{_plain(v)}</td></tr>'
        for k, v in rows
    )
    return _card(
        _section_title("More about your day")
        + f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin-top:8px">{body}</table>'
    )


def _how() -> str:
    boxes = [
        (
            "Productive %",
            "From the productivity rules. Idle time is not part of the % calculation.",
            "#0f766e",
            "#f0fdfa",
        ),
        (
            "Required hours",
            "From attendance: Met, Short, Absent or No target for each day.",
            "#3730a3",
            "#eef2ff",
        ),
        (
            "Summary lines",
            "Flagged at 20+ min Unproductive, or below 70% of your 7-day average.",
            "#c2410c",
            "#fff7ed",
        ),
        (
            "When you see “—”",
            "No history yet, no requirement set, or less than 1 minute of activity.",
            "#334155",
            "#f8fafc",
        ),
    ]
    cells = [
        f'<td width="50%" valign="top" style="padding:0 {5 if k % 2 == 0 else 0}px 10px {5 if k % 2 else 0}px">'
        f'<table role="presentation" width="100%" cellspacing="0" '
        f'cellpadding="0" style="border-collapse:separate;background:{bg};border-radius:10px"><tr><td style="padding:12px 14px">'
        f'<div style="font-size:13px;font-weight:700;color:{fg}">{escape(t)}</div>'
        f'<div style="font-size:12px;color:#3a3d4d;margin-top:4px;line-height:1.45">{escape(d)}</div></td></tr></table></td>'
        for k, (t, d, fg, bg) in enumerate(boxes)
    ]
    rows = "".join(f"<tr>{cells[i]}{cells[i + 1]}</tr>" for i in range(0, len(cells), 2))
    return _card(
        _section_title("How your numbers work")
        + f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin-top:8px">{rows}</table>'
    )


# ---------------------------------------------------------------------------------------------- the e-mail
def build_personal(
    *,
    company_name: str,
    person: PersonReport,
    summary: str,
    by_ai: bool,
    slot: Slot,
    day: date,
    period: str,
    sections: Collection[str],
) -> Digest:
    p = person
    first = p.name.split(" ")[0] or p.name
    title = "Mid-day report" if slot == "midday" else "Evening report"
    subject = f"[WorkPulse] Your {title.lower()} · {day_label(day)}"
    chosen = set(sections)
    gap = '<tr><td style="height:12px;font-size:0;line-height:0">&nbsp;</td></tr>'
    parts = [_tiles(p, chosen)]
    if slot == "evening" and "required_hours" in chosen:
        parts.append(_required_today(p))
    if "summary" in chosen and summary:
        parts.append(_summary(summary, by_ai))
    if "categories" in chosen or "active_idle" in chosen:
        parts.append(_where(p))
    parts.append(_focus_and_breaks(p, chosen))
    if "top_apps" in chosen:
        parts.append(_apps(p))
    parts.append(_more(p, chosen, slot))
    parts.append(_how())
    body = gap.join(f"<tr><td>{x}</td></tr>" for x in parts if x)
    html = f"""<!doctype html>
<html><body style="margin:0;padding:0;background:#f3f4f8;font-family:{FONT}">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f3f4f8"><tr><td align="center"
  style="padding:24px 10px">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:680px">
  <tr><td style="background:{BRAND};border-radius:16px 16px 0 0;padding:22px 24px">
    <div style="font-size:12px;font-weight:700;color:#c7d2fe;text-transform:uppercase;letter-spacing:.08em">
      {escape(title)} · {escape(company_name)}</div>
    <div style="font-size:24px;font-weight:800;color:#ffffff;margin-top:6px">Hi {escape(first)}, here&rsquo;s your
      {"day so far" if slot == "midday" else "day"}.</div>
    <div style="font-size:13px;color:#e0e7ff;margin-top:4px">{escape(day_label(day))} · covers {escape(period)}</div>
  </td></tr>
  <tr><td style="background:#f8f9fc;border:1px solid {LINE};border-top:0;border-radius:0 0 16px 16px;padding:16px">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0">{body}</table>
    <p style="margin:16px 4px 0;font-size:11px;color:#8a8ea0;line-height:1.5">{FOOTNOTE} You receive this e-mail
      because your WorkPulse administrator turned on employee reports.</p>
  </td></tr>
</table></td></tr></table></body></html>"""
    return Digest(subject=subject, text=_text(p, summary, slot, day, period, chosen, company_name), html=html)


def _text(
    p: PersonReport, summary: str, slot: Slot, day: date, period: str, sections: set[str], company: str
) -> str:
    first = p.name.split(" ")[0] or p.name
    lines = [
        f"Hi {first},",
        "",
        f"Your {'mid-day' if slot == 'midday' else 'evening'} report — {company}, "
        f"{day_label(day)} ({period}).",
        "",
    ]
    if slot == "evening" and "required_hours" in sections:
        if not p.expected:
            lines.append(f"Today: no required hours · {duration(p.attended_active)} active")
        elif p.attendance == "met":
            lines.append(f"Today: Met — {duration(p.attended_active)} active of {duration(p.expected)}")
        else:
            lines.append(
                f"Today: Not met — {duration(p.attended_active)} active of {duration(p.expected)} "
                f"({duration(max(0, p.expected - p.attended_active))} short)"
            )
    if "summary" in sections and summary:
        lines += ["", summary]
    lines += [""]
    if "productive_share" in sections:
        share = p.period.productive_share
        lines.append(f"Productive: {f'{share}%' if share is not None else '—'}")
    if "start_time" in sections:
        lines.append(f"Started: {p.first_in.strftime('%H:%M') if p.first_in else '—'}")
    if ("week" in sections or "required_hours" in sections) and p.week_active is not None:
        lines.append(
            f"This week: {duration(p.week_active)}"
            + (
                f" / {duration(p.week_expected)} · {p.week_met} of {p.week_days} days met"
                if p.week_expected
                else ""
            )
        )
    if "categories" in sections or "active_idle" in sections:
        lines.append(
            f"Productive {duration(p.period.productive)} · Neutral {duration(p.period.neutral)} · "
            f"Unproductive {duration(p.period.unproductive)} · Idle {duration(p.period.idle)}"
        )
    if "focus" in sections:
        lines.append(
            f"Focus sessions: {len(p.focus_list)}"
            + "".join(f"\n  {_span(a, b)} ({duration(s)})" for a, b, s in p.focus_list)
        )
    if "long_breaks" in sections:
        lines.append(
            f"Long breaks: {len(p.breaks)}"
            + "".join(f"\n  {_span(a, b)} ({duration(s)})" for a, b, s in p.breaks)
        )
    if "top_apps" in sections and p.top(5):
        lines.append("Top: " + ", ".join(f"{u.name} {duration(u.seconds)}" for u in p.top(5)))
    lines += ["", FOOTNOTE]
    return "\n".join(lines)
