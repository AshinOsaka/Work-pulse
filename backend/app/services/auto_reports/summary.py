"""The written part of a report: one overview and one line per person.

Two ways, same shape:

* **From the numbers** (always available, free): fixed sentences about what stands out.
* **AI** (Claude Haiku, when the server has ``REPORT_AI_API_KEY``): the same facts in natural language. Only
  numbers and app/website names are sent — people appear as "P1", "P2", never by name or e-mail — and the model is
  told to describe recorded activity, not to judge anyone. Any failure (no key, refusal, timeout, odd output) falls
  back to the summary written from the numbers, so a report always goes out.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

import anthropic

from app.services.auto_reports.figures import PersonReport, Slot, duration

logger = logging.getLogger(__name__)

#: Unproductive time in a period worth mentioning.
NOTABLE_UNPRODUCTIVE = 20 * 60
#: Active time this much below the person's own 7-day average is mentioned (evening, full day only).
BELOW_AVERAGE = 0.7

SYSTEM_PROMPT = """You write the short summary of an automatic WorkPulse activity report that a manager receives \
by e-mail. WorkPulse records computer activity: work time (signed in), active time (keyboard or mouse), idle time, \
and time in apps and websites classified as Productive, Neutral or Unproductive by the company's rules.

Rules:
- Use only the figures you are given. Never invent numbers, causes or intentions.
- Describe recorded activity; do not judge people's character, effort or performance. Meetings, calls and \
offline work are not visible in these figures, so avoid strong conclusions.
- Plain, simple, friendly English that non-native speakers read easily. No markdown.
- "overview": at most 3 short sentences about the group: who has not started, who is short of required hours, \
notable Unproductive time, anything clearly unusual. If nothing stands out, say so in one sentence.
- "people": exactly one entry per person ref given, each "note" at most 20 words, stating the most useful fact \
(e.g. started late, high Unproductive time and on which site/app, well below own 7-day average, good focus). \
In the evening report each note must say whether the person met the required hours (active vs required minutes) \
and how much idle time they had. If nothing stands out, write "On track." """

SCHEMA = {
    "type": "object",
    "properties": {
        "overview": {"type": "string"},
        "people": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"ref": {"type": "string"}, "note": {"type": "string"}},
                "required": ["ref", "note"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["overview", "people"],
    "additionalProperties": False,
}


@dataclass
class Summary:
    overview: str
    #: Notes by position in the people list.
    notes: list[str]
    by_ai: bool


# ---------------------------------------------------------------------------------------------- from the numbers
def person_note(p: PersonReport, slot: Slot) -> str:
    if not p.started:
        return (
            "No computer activity recorded yet today." if slot == "midday" else "No computer activity today."
        )
    parts: list[str] = []
    if slot == "evening":
        active, target = duration(p.attended_active), duration(p.expected)
        if p.expected and p.attendance == "met":
            parts.append(f"Met the required hours: {active} active of {target}.")
        elif p.expected and p.attendance == "short":
            parts.append(
                f"Did not meet the required hours: {active} active of {target} "
                f"({duration(p.expected - p.attended_active)} short)."
            )
        elif p.expected:
            parts.append(f"{active} active of {target} required so far.")
        else:
            parts.append(f"{active} active today.")
        parts.append(f"Idle {duration(p.day.idle)}.")
    if p.period.unproductive >= NOTABLE_UNPRODUCTIVE:
        worst = p.top(1, "unproductive")
        where = f", mostly {worst[0].name}" if worst else ""
        parts.append(f"Unproductive {duration(p.period.unproductive)}{where}.")
    if slot == "evening" and p.avg_active and p.day.active < BELOW_AVERAGE * p.avg_active:
        parts.append(f"Active time below own 7-day average ({duration(p.avg_active)}).")
    return " ".join(parts) or "On track."


def plain_summary(people: list[PersonReport], slot: Slot) -> Summary:
    everyone = people
    # The overview is about the team: a manager's own row (shown first in their e-mail) isn't counted.
    people = [p for p in people if not p.is_self] or people
    total = len(people)
    started = sum(1 for p in people if p.started)
    sentences = [
        f"{started} of {total} {'person has' if total == 1 else 'people have'} recorded activity "
        f"{'so far today' if slot == 'midday' else 'today'}."
    ]
    if slot == "evening":
        with_target = [p for p in people if p.expected and p.started]
        if with_target:
            met = sum(1 for p in with_target if p.attendance == "met")
            # Before the workday ends the attendance status is still "in progress": say "so far", not "met".
            ongoing = any(p.attendance == "in_progress" for p in with_target)
            verb = "have met the required hours so far" if ongoing else "met the required hours"
            sentences.append(f"{met} of {len(with_target)} {verb}.")
    heavy = [p for p in people if p.period.unproductive >= NOTABLE_UNPRODUCTIVE]
    if heavy:
        sentences.append(
            f"{len(heavy)} had more than {NOTABLE_UNPRODUCTIVE // 60} minutes of Unproductive time in this period."
        )
    return Summary(" ".join(sentences), [person_note(p, slot) for p in everyone], by_ai=False)


# ---------------------------------------------------------------------------------------------- AI
def _facts(people: list[PersonReport], slot: Slot) -> str:
    """What the model sees: references and numbers only (minutes), no names or e-mail addresses."""
    rows = []
    for i, p in enumerate(people, start=1):
        row: dict[str, object] = {
            "ref": f"P{i}",
            "started": p.started,
            "first_sign_in": p.first_in.strftime("%H:%M") if p.first_in else None,
            "period_minutes": {
                "work": round(p.period.work / 60),
                "active": round(p.period.active / 60),
                "idle": round(p.period.idle / 60),
                "productive": round(p.period.productive / 60),
                "neutral": round(p.period.neutral / 60),
                "unproductive": round(p.period.unproductive / 60),
                "focus_sessions": p.period.focus_count,
                "customer_systems": round(p.period.customer / 60),
            },
            "top_apps_and_sites": [
                {"name": u.name, "minutes": round(u.seconds / 60), "category": u.category} for u in p.top(4)
            ],
        }
        if slot == "evening":
            row["whole_day_active_minutes"] = round(p.attended_active / 60)
            row["whole_day_idle_minutes"] = round(p.day.idle / 60)
            row["required_minutes"] = round(p.expected / 60) if p.expected else None
            row["required_hours_met"] = None if not p.expected else p.attendance == "met"
            row["own_7_day_average_active_minutes"] = round(p.avg_active / 60) if p.avg_active else None
        rows.append(row)
    period = (
        "the morning (the day so far, mid-day report)"
        if slot == "midday"
        else "the afternoon since the mid-day report; whole-day figures are included (evening report)"
    )
    return f"Report period: {period}.\nPeople:\n{json.dumps(rows, ensure_ascii=False)}"


async def ai_summary(
    client: anthropic.AsyncAnthropic, model: str, people: list[PersonReport], slot: Slot
) -> Summary | None:
    """The model's summary, or None when it can't be used (the caller then uses `plain_summary`)."""
    if not people:
        return None
    try:
        response = await client.messages.create(
            model=model,
            max_tokens=4000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": _facts(people, slot)}],
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
        )
    except anthropic.APIError as exc:
        logger.warning("AI report summary unavailable (%s); using the plain summary", type(exc).__name__)
        return None
    if response.stop_reason != "end_turn":
        logger.warning("AI report summary stopped (%s); using the plain summary", response.stop_reason)
        return None
    try:
        text = next(b.text for b in response.content if b.type == "text")
        data = json.loads(text)
        notes_by_ref = {str(item["ref"]): str(item["note"]).strip() for item in data["people"]}
        overview = str(data["overview"]).strip()
    except (StopIteration, ValueError, KeyError, TypeError):
        logger.warning("AI report summary was not in the expected shape; using the plain summary")
        return None
    fallback = plain_summary(people, slot)
    notes = [notes_by_ref.get(f"P{i}") or fallback.notes[i - 1] for i in range(1, len(people) + 1)]
    return Summary(overview or fallback.overview, notes, by_ai=True)
