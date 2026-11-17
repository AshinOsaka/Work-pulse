"""The digest e-mail: an HTML version (table + one block per person) and a plain-text fallback.

What appears is chosen by the administrator (`SECTIONS`, Settings → Automatic reports); the employee's name is always
there. E-mail clients ignore stylesheets, so styles are inline. Everything that comes from data is escaped. No
window titles and no screenshots — only app/website names and durations.
"""

from __future__ import annotations

from collections.abc import Callable, Collection
from dataclasses import dataclass
from datetime import date
from html import escape

from app.services.auto_reports.figures import SECTIONS, PersonReport, Slot, day_label, duration
from app.services.auto_reports.summary import Summary

COLORS = {"productive": "#16a34a", "neutral": "#d97706", "unproductive": "#dc2626", "unclassified": "#6b7280"}
STATUS = {
    "met": ("Met", "#16a34a"),
    "short": ("Short", "#dc2626"),
    "in_progress": ("In progress", "#6b7280"),
    "absent": ("Absent", "#dc2626"),
    "no_target": ("No target", "#6b7280"),
}
FOOTNOTE = (
    "Figures are recorded computer activity under your workspace's rules. Meetings, calls and offline work are "
    "not visible in them, so use them as context for a conversation, not as a verdict."
)


@dataclass
class Digest:
    subject: str
    text: str
    html: str


def _title(slot: Slot) -> str:
    return "Mid-day report" if slot == "midday" else "Evening report"


def _period(slot: Slot, period_start: str | None, period_end: str) -> str:
    if slot == "midday":
        return f"today until {period_end}"
    return (
        f"{period_start} to {period_end}, plus the whole day"
        if period_start
        else f"the whole day until {period_end}"
    )


def _share(p: PersonReport) -> str:
    share = p.period.productive_share
    return f"{share}%" if share is not None else "—"


def _vs_average(p: PersonReport) -> str:
    if not p.avg_active or not p.started:
        return "—"
    change = round(100 * (p.day.active - p.avg_active) / p.avg_active)
    return f"{'+' if change >= 0 else ''}{change}%"


def _started(p: PersonReport) -> str:
    return p.first_in.strftime("%H:%M") if p.first_in else "—"


def _required(p: PersonReport) -> tuple[str, str]:
    label, color = STATUS.get(p.attendance or "", ("—", "#6b7280"))
    return (f"{label} ({duration(p.expected)})" if p.expected else label), color


def _focus(p: PersonReport) -> str:
    if not p.period.focus_count:
        return "no focus sessions"
    plural = "s" if p.period.focus_count != 1 else ""
    return f"{p.period.focus_count} focus session{plural} ({duration(p.period.focus_seconds)})"


@dataclass(frozen=True)
class Column:
    head: str
    #: (value, colour or None, alignment)
    value: Callable[[PersonReport], tuple[str, str | None, str]]


def _columns(sections: Collection[str], slot: Slot) -> list[Column]:
    cols: list[Column] = []
    if "start_time" in sections:
        cols.append(Column("Started", lambda p: (_started(p), None if p.started else "#dc2626", "left")))
    if "active_idle" in sections:
        cols.append(Column("Active", lambda p: (duration(p.period.active), None, "right")))
        cols.append(Column("Idle", lambda p: (duration(p.period.idle), None, "right")))
    if "categories" in sections:
        cols.append(
            Column("Productive", lambda p: (duration(p.period.productive), COLORS["productive"], "right"))
        )
        cols.append(Column("Neutral", lambda p: (duration(p.period.neutral), COLORS["neutral"], "right")))
        cols.append(
            Column(
                "Unproductive",
                lambda p: (
                    duration(p.period.unproductive),
                    COLORS["unproductive"] if p.period.unproductive >= 60 else None,
                    "right",
                ),
            )
        )
    if "productive_share" in sections:
        cols.append(Column("Productive %", lambda p: (_share(p), None, "right")))
    if "customer_time" in sections:
        cols.append(Column("Customer time", lambda p: (duration(p.period.customer), None, "right")))
    if "focus" in sections:
        cols.append(Column("Focus", lambda p: (str(p.period.focus_count), None, "right")))
    if slot == "evening" and "required_hours" in sections:
        cols.append(Column("Day active", lambda p: (duration(p.attended_active), None, "right")))
        cols.append(Column("Required hours", lambda p: (_required(p)[0], _required(p)[1], "left")))
    if slot == "evening" and "average" in sections:
        cols.append(Column("vs 7-day avg", lambda p: (_vs_average(p), None, "right")))
    return cols


def build_digest(
    *,
    company_name: str,
    recipient_name: str,
    people: list[PersonReport],
    summary: Summary,
    slot: Slot,
    day: date,
    period_start: str | None,
    period_end: str,
    link: str,
    test: bool = False,
    sections: Collection[str] = SECTIONS,
) -> Digest:
    title = _title(slot)
    subject = f"{'[Test] ' if test else ''}[WorkPulse] {title} · {day_label(day)} · {len(people)} " + (
        "person" if len(people) == 1 else "people"
    )
    period = _period(slot, period_start, period_end)
    chosen = set(sections)
    return Digest(
        subject=subject,
        text=_text(company_name, recipient_name, people, summary, slot, day, period, link, chosen),
        html=_html(company_name, recipient_name, people, summary, slot, day, period, link, test, chosen),
    )


# ---------------------------------------------------------------------------------------------- plain text
def _text(
    company: str,
    recipient: str,
    people: list[PersonReport],
    summary: Summary,
    slot: Slot,
    day: date,
    period: str,
    link: str,
    sections: set[str],
) -> str:
    lines = [f"Hello {recipient},", "", f"{_title(slot)} for {company} — {day_label(day)} ({period}).", ""]
    with_summary = "summary" in sections
    if with_summary:
        lines += [summary.overview, ""]
    columns = _columns(sections, slot)
    for i, p in enumerate(people):
        lines.append(f"• {p.name}")
        values = [f"{c.head}: {c.value(p)[0]}" for c in columns]
        if values:
            lines.append("  " + " · ".join(values))
        if "top_apps" in sections:
            top = p.top(5)
            lines.append(
                "  Top: "
                + (", ".join(f"{u.name} {duration(u.seconds)}" for u in top) if top else "none recorded")
            )
        if with_summary:
            lines.append(f"  {summary.notes[i]}")
        lines.append("")
    lines += [f"Open WorkPulse: {link}", "", FOOTNOTE]
    if with_summary and summary.by_ai:
        lines.append("Summary written by AI from the figures above.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------------------------- HTML
TD = "padding:8px 10px;border-bottom:1px solid #eceef3;font-size:13px;color:#1e202c;white-space:nowrap"
TH = (
    "padding:8px 10px;border-bottom:2px solid #e3e5ec;font-size:11px;color:#646878;text-align:left;"
    "text-transform:uppercase;letter-spacing:.04em;white-space:nowrap"
)


def _cell(value: str, color: str | None = None, align: str = "left") -> str:
    style = TD + f";text-align:{align}" + (f";color:{color};font-weight:600" if color else "")
    return f'<td style="{style}">{value}</td>'


def _chip(name: str, seconds: float, category: str) -> str:
    color = COLORS.get(category, COLORS["unclassified"])
    return (
        f'<span style="display:inline-block;margin:2px 6px 2px 0;padding:2px 8px;border-radius:999px;'
        f'border:1px solid {color}33;background:{color}12;font-size:12px;color:#1e202c">'
        f'<span style="color:{color}">●</span> {escape(name)} · {duration(seconds)}</span>'
    )


def _html(
    company: str,
    recipient: str,
    people: list[PersonReport],
    summary: Summary,
    slot: Slot,
    day: date,
    period: str,
    link: str,
    test: bool,
    sections: set[str],
) -> str:
    columns = _columns(sections, slot)
    with_summary = "summary" in sections
    with_apps = "top_apps" in sections
    rows = []
    for p in people:
        cells = [_cell(f"<strong>{escape(p.name)}</strong>")]
        for c in columns:
            value, color, align = c.value(p)
            cells.append(_cell(escape(value), color, align))
        rows.append(f"<tr>{''.join(cells)}</tr>")
    table = (
        '<div style="overflow-x:auto;margin-top:16px"><table cellspacing="0" cellpadding="0" '
        'style="border-collapse:collapse;width:100%"><tr>'
        + "".join(f'<th style="{TH}">{h}</th>' for h in ["Employee", *(c.head for c in columns)])
        + "</tr>"
        + "".join(rows)
        + "</table></div>"
    )

    blocks = []
    if with_summary or with_apps:
        for i, p in enumerate(people):
            parts = [
                f'<div style="font-size:14px;font-weight:600;color:#1e202c">{escape(p.name)}'
                + (
                    f'<span style="font-weight:400;color:#646878;font-size:12px"> · {escape(_focus(p))}</span>'
                    if "focus" in sections and p.period.focus_count
                    else ""
                )
                + "</div>"
            ]
            if with_summary:
                parts.append(
                    f'<div style="font-size:13px;color:#3a3d4d;margin:4px 0 6px">{escape(summary.notes[i])}</div>'
                )
            if with_apps:
                chips = "".join(_chip(u.name, u.seconds, u.category) for u in p.top(6)) or (
                    '<span style="font-size:12px;color:#646878">No app or website activity recorded.</span>'
                )
                parts.append(f'<div style="margin-top:4px">{chips}</div>')
            blocks.append(
                f'<div style="padding:12px 0;border-bottom:1px solid #eceef3">{"".join(parts)}</div>'
            )
    heading = "Per person · most used apps and websites in this period" if with_apps else "Per person"
    per_person = (
        '<div style="margin-top:18px;font-size:12px;color:#646878;text-transform:uppercase;letter-spacing:.04em">'
        f"{heading}</div>{''.join(blocks)}"
        if blocks
        else ""
    )
    overview = (
        '<div style="background:#eeecfd;border-radius:8px;padding:12px 14px;font-size:14px;color:#1e202c;'
        f'line-height:1.5">{escape(summary.overview)}'
        + (
            '<p style="margin:6px 0 0;font-size:11px;color:#8a8ea0">Summary written by AI from the figures in '
            "this e-mail.</p>"
            if summary.by_ai
            else ""
        )
        + "</div>"
        if with_summary
        else ""
    )
    test_banner = (
        '<div style="background:#fff7e6;border:1px solid #f5d18a;color:#8a5a00;padding:8px 12px;border-radius:8px;'
        'font-size:12px;margin-bottom:12px">Test e-mail — sent on request from Settings; managers were not '
        "e-mailed.</div>"
        if test
        else ""
    )
    return f"""<!doctype html>
<html><body style="margin:0;padding:0;background:#f5f6fa;font-family:Segoe UI,Roboto,Helvetica,Arial,sans-serif">
<div style="max-width:980px;margin:0 auto;padding:20px 12px">
{test_banner}
<div style="background:#5b4ce6;color:#fff;border-radius:12px 12px 0 0;padding:18px 20px">
  <div style="font-size:12px;opacity:.85">WorkPulse · {escape(company)}</div>
  <div style="font-size:20px;font-weight:700;margin-top:2px">{_title(slot)} · {escape(day_label(day))}</div>
  <div style="font-size:13px;opacity:.9;margin-top:2px">Covers {escape(period)}</div>
</div>
<div style="background:#fff;border-radius:0 0 12px 12px;padding:18px 20px;border:1px solid #e3e5ec;border-top:0">
  <p style="margin:0 0 6px;font-size:14px;color:#1e202c">Hello {escape(recipient)},</p>
  {overview}
  {table}
  {per_person}
  <div style="margin-top:18px">
    <a href="{escape(link)}" style="display:inline-block;background:#5b4ce6;color:#fff;text-decoration:none;
      padding:9px 16px;border-radius:8px;font-size:13px;font-weight:600">Open in WorkPulse</a>
  </div>
  <p style="margin:16px 0 0;font-size:11px;color:#8a8ea0;line-height:1.5">{FOOTNOTE} You receive this e-mail
    because your WorkPulse administrator set up automatic reports (Settings → Automatic reports).</p>
</div></div></body></html>"""
