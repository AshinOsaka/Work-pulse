"""The "View more" breakdown: time per window title inside one application or website."""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from bson import ObjectId

from tests.org_helpers import Workspace
from tests.test_agent_api import enrol_member, event, iso
from tests.test_productivity_api import DAY, at


def titled(
    hour: float, minutes: float, app: str, name: str, title: str, domain: str | None = None
) -> dict[str, Any]:
    start = at(hour)
    fields: dict[str, Any] = {
        "session_id": str(uuid.uuid4()),
        "app_id": app,
        "app_name": name,
        "window_title": title,
        "started_at": iso(start),
        "ended_at": iso(start + timedelta(minutes=minutes)),
        "active_seconds": int(minutes * 60 * 0.8),
        "activity_level": 80,
    }
    if domain:
        fields["domain"] = domain
    return event("activity.segment", start + timedelta(minutes=minutes), **fields)


def titles(ws: Workspace, employee_id: str, kind: str, key: str, token: str | None = None) -> Any:
    day = DAY.date().isoformat()
    return ws.get(
        f"/productivity/employees/{employee_id}/titles", start=day, end=day, kind=kind, key=key, token=token
    )


def test_titles_are_totalled_per_website_and_per_application(ws: Workspace) -> None:
    ws.patch("/companies/current/activity-policy", {"capture_window_titles": True, "track_websites": True})
    member, agent = enrol_member(ws, "Tina Titles")
    agent.events(
        titled(9, 30, "chrome.exe", "Google Chrome", "Fare search - Claude - Google Chrome", "claude.ai"),
        titled(10, 10, "chrome.exe", "Google Chrome", "Visa checklist - Claude - Google Chrome", "claude.ai"),
        titled(11, 15, "chrome.exe", "Google Chrome", "Fare search - Claude - Google Chrome", "claude.ai"),
        titled(
            12, 20, "chrome.exe", "Google Chrome", "New Tab - Google Chrome"
        ),  # no website: the browser's own
        titled(13, 25, "code.exe", "Visual Studio Code", "main.py - WorkPulse"),
    )

    site = titles(ws, member.employee_id, "website", "claude.ai").json()
    assert site["capture_enabled"] is True
    assert [(t["title"], t["seconds"]) for t in site["titles"]] == [
        ("Fare search - Claude - Google Chrome", 45 * 60),  # same title on two segments: added up, most first
        ("Visa checklist - Claude - Google Chrome", 10 * 60),
    ]
    assert site["titled_seconds"] == 55 * 60

    browser = titles(ws, member.employee_id, "app", "chrome.exe").json()
    assert [t["title"] for t in browser["titles"]] == [
        "New Tab - Google Chrome"
    ]  # website time is not repeated

    app = titles(ws, member.employee_id, "app", "code.exe").json()
    assert app["titles"] == [{"title": "main.py - WorkPulse", "seconds": 25 * 60}]


def test_no_titles_are_kept_while_capture_is_off_or_for_sensitive_apps(ws: Workspace, sync_db: Any) -> None:
    member, agent = enrol_member(ws, "Oscar Off")
    agent.events(titled(9, 10, "code.exe", "Visual Studio Code", "secret.py - Project"))
    off = titles(ws, member.employee_id, "app", "code.exe").json()
    assert off["capture_enabled"] is False and off["titles"] == [] and off["titled_seconds"] == 0

    ws.patch("/companies/current/activity-policy", {"capture_window_titles": True})
    agent.events(
        titled(10, 10, "whatsapp.exe", "WhatsApp", "Chat with Priya"),
        titled(11, 10, "code.exe", "Visual Studio Code", "Mail anna@example.com about 9876543210"),
    )
    assert titles(ws, member.employee_id, "app", "whatsapp.exe").json()["titles"] == []  # never recorded
    redacted = titles(ws, member.employee_id, "app", "code.exe").json()["titles"]
    assert redacted == [{"title": "Mail [email] about [number]", "seconds": 600}]
    stored = sync_db["window_title_daily"].count_documents({"employee_id": ObjectId(member.employee_id)})
    assert stored == 1


def test_titles_follow_the_employee_report_access(ws: Workspace) -> None:
    ws.patch("/companies/current/activity-policy", {"capture_window_titles": True})
    member, agent = enrol_member(ws, "Ada Access")
    other, _ = enrol_member(ws, "Ben Other")
    agent.events(titled(9, 10, "code.exe", "Visual Studio Code", "notes.md"))

    assert (
        titles(ws, member.employee_id, "app", "code.exe", token=member.token).status_code == 200
    )  # own data
    assert (
        titles(ws, member.employee_id, "app", "code.exe", token=other.token).status_code == 404
    )  # not theirs
    assert titles(ws, member.employee_id, "bogus", "code.exe").status_code == 422


def test_deleting_an_employee_removes_their_titles(ws: Workspace, sync_db: Any) -> None:
    ws.patch("/companies/current/activity-policy", {"capture_window_titles": True})
    member, agent = enrol_member(ws, "Del Gone")
    agent.events(titled(9, 10, "code.exe", "Visual Studio Code", "draft.txt"))
    emp = ObjectId(member.employee_id)
    assert sync_db["window_title_daily"].count_documents({"employee_id": emp}) == 1

    assert ws.delete(f"/employees/{member.employee_id}").status_code == 204
    assert sync_db["window_title_daily"].count_documents({"employee_id": emp}) == 0
