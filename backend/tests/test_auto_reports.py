"""Automatic report e-mails (mid-day and evening digests per manager) and the unproductive-time alert."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

from bson import ObjectId
from fastapi.testclient import TestClient

from app.services.auto_reports.figures import Figures, PersonReport, Usage, duration
from app.services.auto_reports.summary import ai_summary, plain_summary
from tests.org_helpers import Workspace
from tests.test_agent_api import AgentClient, enrol_member, event, iso
from tests.test_notifications import company_id, drain, notes


def _zone_for_afternoon(now: datetime) -> str:
    """A fixed-offset zone where it is about 14:00 now, so "today" has room for activity before now."""
    offset = (14 - now.hour + 12) % 24 - 12  # -12 … +11
    return "UTC" if offset == 0 else f"Etc/GMT{'-' if offset > 0 else '+'}{abs(offset)}"


def _segment(
    start: datetime, minutes: float, app: str, name: str, domain: str | None = None
) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "session_id": str(uuid.uuid4()),
        "app_id": app,
        "app_name": name,
        "started_at": iso(start),
        "ended_at": iso(start + timedelta(minutes=minutes)),
        "active_seconds": int(minutes * 60 * 0.9),
        "activity_level": 80,
    }
    if domain:
        fields["domain"] = domain
    return event("activity.segment", start + timedelta(minutes=minutes), **fields)


def _work_today(agent: AgentClient, now: datetime, netflix_minutes: float = 25) -> None:
    """A session over the last 80 minutes: code, then Netflix (Unproductive under the rule set below)."""
    start = now - timedelta(minutes=80)
    sid = str(uuid.uuid4())
    events = [
        event("session.started", start, session_id=sid),
        _segment(start, 30, "code.exe", "Visual Studio Code"),
        _segment(
            start + timedelta(minutes=30), netflix_minutes, "chrome.exe", "Google Chrome", "netflix.com"
        ),
        event(
            "session.stopped",
            now - timedelta(minutes=5),
            session_id=sid,
            reason="user",
            active_seconds=4000,
            idle_seconds=500,
        ),
    ]
    response = agent.events(*events)
    assert response.status_code == 200 and response.json()["rejected"] == [], response.text


def _work_split(agent: AgentClient, now: datetime) -> None:
    """Netflix 15 min, code 5 min, Netflix 15 min: 30 minutes in total, but never 20 without a break."""
    start = now - timedelta(minutes=60)
    sid = str(uuid.uuid4())
    events = [
        event("session.started", start, session_id=sid),
        _segment(start, 15, "chrome.exe", "Google Chrome", "netflix.com"),
        _segment(start + timedelta(minutes=15), 5, "code.exe", "Visual Studio Code"),
        _segment(start + timedelta(minutes=20), 15, "chrome.exe", "Google Chrome", "netflix.com"),
        event(
            "session.stopped",
            now - timedelta(minutes=20),
            session_id=sid,
            reason="user",
            active_seconds=2000,
            idle_seconds=100,
        ),
    ]
    response = agent.events(*events)
    assert response.status_code == 200 and response.json()["rejected"] == [], response.text


def _setup(ws: Workspace, sync_db: Any, now: datetime, *, split: bool = False) -> tuple[Any, Any, str]:
    boss, _ = enrol_member(ws, "Maya Manager", role="MANAGER")  # has a WorkPulse computer
    worker, agent = enrol_member(ws, "Wes Worker", manager_employee_id=boss.employee_id)
    zone = _zone_for_afternoon(now)
    cid = company_id(sync_db, ws.admin.user_id)
    sync_db["companies"].update_one(
        {"_id": cid},
        {
            "$set": {
                "timezone": zone,
                "work_days": [1, 2, 3, 4, 5, 6, 7],
                "holidays": [],
                "activity_policy.track_websites": True,
            }
        },
    )
    assert (
        ws.post(
            "/productivity/rules", {"kind": "website", "pattern": "netflix.com", "category": "unproductive"}
        ).status_code
        == 201
    )
    assert (
        ws.post(
            "/productivity/rules", {"kind": "app", "pattern": "code.exe", "category": "productive"}
        ).status_code
        == 201
    )
    if split:
        _work_split(agent, now)
    else:
        _work_today(agent, now)
    return boss, worker, zone


def _job(client: TestClient) -> Any:
    return client.app.state.background.auto_reports  # type: ignore[attr-defined]


def test_settings_are_validated_saved_and_off_by_default(ws: Workspace) -> None:
    company = ws.get("/companies/current").json()
    assert company["auto_reports"]["enabled"] is False
    assert company["auto_reports"]["unproductive_alert_minutes"] == 20
    good = {
        "enabled": True,
        "midday_time": "13:00",
        "evening_time": "18:30",
        "send_to_managers": True,
        "extra_recipients": ["HR@Example.com", "hr@example.com", "boss@example.com"],
        "ai_summary": True,
        "unproductive_alert_enabled": True,
        "unproductive_alert_minutes": 25,
    }
    saved = ws.patch("/companies/current", {"auto_reports": good})
    assert saved.status_code == 200, saved.text
    extras = saved.json()["auto_reports"]["extra_recipients"]
    assert [x["email"] for x in extras] == ["hr@example.com", "boss@example.com"]
    assert extras[0] == {
        "email": "hr@example.com",
        "department_ids": [],
        "team_ids": [],
        "midday": True,
        "evening": True,
    }
    assert (
        ws.patch("/companies/current", {"auto_reports": {**good, "midday_time": "19:00"}}).status_code == 422
    )
    assert (
        ws.patch("/companies/current", {"auto_reports": {**good, "extra_recipients": ["nope"]}}).status_code
        == 422
    )
    assert (
        ws.patch(
            "/companies/current", {"auto_reports": {**good, "unproductive_alert_minutes": 1}}
        ).status_code
        == 422
    )
    neither = {**good, "midday_enabled": False, "evening_enabled": False}
    assert ws.patch("/companies/current", {"auto_reports": neither}).status_code == 422
    no_kind = {**good, "unproductive_total_enabled": False, "unproductive_continuous_enabled": False}
    assert ws.patch("/companies/current", {"auto_reports": no_kind}).status_code == 422
    # Once a day: the evening report alone may be set before a (now unused) mid-day time.
    once = {**good, "midday_enabled": False, "midday_time": "20:00", "evening_time": "18:00"}
    assert ws.patch("/companies/current", {"auto_reports": once}).status_code == 200
    # Saving other settings leaves the automatic reports alone.
    assert ws.patch("/companies/current", {"name": "Renamed Co"}).json()["auto_reports"]["enabled"] is True


def test_midday_and_evening_digests_go_to_the_manager_and_extra_recipients_once(
    ws: Workspace, client: TestClient, sync_db: Any
) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    boss, _worker, zone = _setup(ws, sync_db, now)
    local = now.astimezone(ZoneInfo(zone))
    policy = {
        "enabled": True,
        "midday_time": (local - timedelta(minutes=3)).strftime("%H:%M"),
        "evening_time": (local + timedelta(minutes=30)).strftime("%H:%M"),
        "extra_recipients": ["director@example.com"],
        "ai_summary": True,
    }
    assert ws.patch("/companies/current", {"auto_reports": policy}).status_code == 200
    job = _job(client)
    ws.mail.messages.clear()

    assert client.portal.call(job.tick, now) == 1  # type: ignore[attr-defined]
    to = {m.to: m for m in ws.mail.messages}
    assert set(to) == {boss.email, "director@example.com"}
    digest = to[boss.email]
    assert digest.subject.startswith("[WorkPulse] Mid-day report") and "2 people" in digest.subject
    assert "== Your own figures ==" in digest.text  # the manager's own figures come first
    assert "Wes Worker" in digest.text and "1 of 1 person has recorded activity" in digest.text
    assert digest.html and "Wes Worker" in digest.html and "netflix.&#8203;com" in digest.html  # not a link
    assert "Unproductive" in digest.text and "Visual Studio Code" in digest.text
    # Started = the first activity today, with the sign-in sessions as on the Attendance page.
    started = (now - timedelta(minutes=80)).astimezone(ZoneInfo(zone)).strftime("%H:%M")
    assert f"Started: {started}" in digest.text and f"Signed in: {started} to " in digest.text
    first = (now - timedelta(minutes=80)).astimezone(ZoneInfo(zone))
    assert f"{first:%I:%M}".lstrip("0") + f" {first:%p}" in digest.html  # Started, in the team table
    assert "Team report" in digest.html and "Person cards" in digest.html
    # The director gets everyone, including the manager herself.
    assert "Maya Manager" in to["director@example.com"].text
    # Without an AI key, the summary is written from the numbers.
    assert "AI" not in digest.text

    ws.mail.messages.clear()
    assert client.portal.call(job.tick, now + timedelta(minutes=1)) == 0  # type: ignore[attr-defined]
    assert ws.mail.messages == []  # sent once per day

    # Evening: the afternoon is "whole day minus the mid-day snapshot" — nothing new happened since.
    later = now + timedelta(minutes=31)
    assert client.portal.call(job.tick, later) == 1  # type: ignore[attr-defined]
    evening = next(m for m in ws.mail.messages if m.to == boss.email)
    assert evening.subject.startswith("[WorkPulse] Evening report")
    assert (
        "the whole day until" in evening.text  # the evening report covers the day from its start
        and "Unproductive: 25m" in evening.text
        and "Day active: " in evening.text
        and "Required hours: " in evening.text
    )
    runs = ws.get("/auto-reports/status").json()["runs"]
    assert [(r["slot"], r["status"], r["sent"]) for r in runs] == [
        ("evening", "done", 2),
        ("midday", "done", 2),
    ]


def test_reports_skip_days_off_and_respect_the_send_window(
    ws: Workspace, client: TestClient, sync_db: Any
) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    _setup(ws, sync_db, now)
    local = now.astimezone(ZoneInfo(_zone_for_afternoon(now)))
    cid = company_id(sync_db, ws.admin.user_id)
    policy = {
        "enabled": True,
        "midday_time": (local - timedelta(hours=3)).strftime("%H:%M"),
        "evening_time": "23:59",
    }
    if policy["midday_time"] >= "23:59":  # pragma: no cover - only near midnight
        return
    assert ws.patch("/companies/current", {"auto_reports": policy}).status_code == 200
    ws.mail.messages.clear()
    assert client.portal.call(_job(client).tick, now) == 0  # type: ignore[attr-defined]  # 3 h late: stale
    sync_db["companies"].update_one(
        {"_id": cid},
        {
            "$set": {
                "auto_reports.midday_time": (local - timedelta(minutes=1)).strftime("%H:%M"),
                "holidays": [local.date().isoformat()],
            }
        },
    )
    assert client.portal.call(_job(client).tick, now) == 0  # type: ignore[attr-defined]  # a holiday
    assert ws.mail.messages == []


def test_unproductive_alert_tells_the_employee_and_manager_once_a_day(
    ws: Workspace, client: TestClient, sync_db: Any
) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    boss, worker, _ = _setup(ws, sync_db, now)
    policy = {"enabled": False, "unproductive_alert_enabled": True, "unproductive_alert_minutes": 30}
    assert ws.patch("/companies/current", {"auto_reports": policy}).status_code == 200
    job = _job(client)
    ws.mail.messages.clear()
    client.portal.call(job.tick, now)  # type: ignore[attr-defined]
    assert ws.mail.messages == []  # 25 minutes is under the 30-minute limit

    sync_db["companies"].update_one(
        {"_id": company_id(sync_db, ws.admin.user_id)},
        {"$set": {"auto_reports.unproductive_alert_minutes": 20}},
    )
    client.portal.call(job.tick, now + timedelta(minutes=6))  # type: ignore[attr-defined]
    to = {m.to: m for m in ws.mail.messages}
    assert set(to) == {worker.email, boss.email}
    assert (
        "netflix.com" in to[worker.email].text and "Your manager has received a copy" in to[worker.email].text
    )
    assert to[boss.email].subject == f"[WorkPulse] Wes Worker: Unproductive time today: {duration(25 * 60)}"
    drain(client)
    alert = notes(ws, type="unproductive_time")
    assert alert and alert[0]["title"] == "Unproductive time limit reached — Wes Worker"
    assert notes(ws, token=worker.token, type="unproductive_time")  # the employee sees it too

    ws.mail.messages.clear()
    client.portal.call(job.tick, now + timedelta(minutes=12))  # type: ignore[attr-defined]
    assert ws.mail.messages == []  # once per person per day


def test_test_email_goes_only_to_the_requester(ws: Workspace, client: TestClient, sync_db: Any) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    _setup(ws, sync_db, now)
    ws.mail.messages.clear()
    response = ws.post("/auto-reports/test", {"slot": "midday"})
    assert response.status_code == 200, response.text
    assert response.json()["sent_to"] == ws.admin.email and response.json()["ai"] is False
    (message,) = ws.mail.messages
    assert message.to == ws.admin.email and message.subject.startswith("[Test] [WorkPulse] Mid-day report")
    assert message.html and "managers were not" in message.html
    status = ws.get("/auto-reports/status").json()
    assert status["ai_available"] is False and status["ai_model"] == "claude-haiku-5-5"
    member = ws.member("Nia Nosy")
    assert ws.post("/auto-reports/test", {"slot": "midday"}, token=member.token).status_code == 403


# ---------------------------------------------------------------------------------------------- summaries
def _person(name: str, **figures: float) -> PersonReport:
    f = Figures(**figures)  # type: ignore[arg-type]
    return PersonReport(
        employee_id=ObjectId(),
        name=name,
        email=f"{name.lower()}@example.com",
        manager_id=None,
        team_id=None,
        period=f,
        day=f,
        usage=[Usage("website", "youtube.com", "youtube.com", f.unproductive, "unproductive")],
        expected=8 * 3600,
        attended_active=round(f.active),
        attendance="short",
    )


class _FakeMessages:
    def __init__(self, reply: str | Exception, stop: str = "end_turn") -> None:
        self.reply, self.stop, self.prompts = reply, stop, []

    async def create(self, **kwargs: Any) -> Any:
        self.prompts.append(kwargs)
        if isinstance(self.reply, Exception):
            raise self.reply
        return SimpleNamespace(stop_reason=self.stop, content=[SimpleNamespace(type="text", text=self.reply)])


def test_plain_summary_states_what_stands_out() -> None:
    people = [_person("Ann", work=3600, active=3000, unproductive=1800), _person("Bob")]
    summary = plain_summary(people, "evening")
    assert summary.overview.startswith("1 of 2 people have recorded activity today.")
    assert "Unproductive 30m, mostly youtube.com." in summary.notes[0]
    assert (
        "Did not meet the required hours: 50m active of 8h 00m (7h 10m short). Idle 0m." in summary.notes[0]
    )
    assert summary.notes[1] == "No computer activity today." and not summary.by_ai


def test_ai_summary_sends_numbers_only_and_falls_back_on_any_problem(client: TestClient) -> None:
    import anthropic

    people = [_person("Ann", work=3600, active=3000, unproductive=1800), _person("Bob")]
    reply = json.dumps(
        {"overview": "Ann watched videos.", "people": [{"ref": "P1", "note": "High Unproductive time."}]}
    )
    fake = _FakeMessages(reply)
    result = client.portal.call(
        ai_summary, SimpleNamespace(messages=fake), "claude-haiku-5-5", people, "midday"
    )  # type: ignore[attr-defined]
    assert result is not None and result.by_ai and result.overview == "Ann watched videos."
    assert result.notes[0] == "High Unproductive time."
    assert (
        result.notes[1] == "No computer activity recorded yet today."
    )  # missing ref: written from the numbers
    sent = fake.prompts[0]
    assert sent["model"] == "claude-haiku-5-5" and sent["output_config"]["effort"] == "low"
    prompt = sent["messages"][0]["content"]
    assert "Ann" not in prompt and "@example.com" not in prompt and '"ref": "P1"' in prompt

    for broken in (
        _FakeMessages("not json"),
        _FakeMessages(reply, stop="refusal"),
        _FakeMessages(anthropic.APIConnectionError(request=SimpleNamespace())),  # type: ignore[arg-type]
    ):
        assert client.portal.call(ai_summary, SimpleNamespace(messages=broken), "m", people, "midday") is None  # type: ignore[attr-defined]


def test_once_a_day_sends_only_the_evening_report_covering_the_whole_day(
    ws: Workspace, client: TestClient, sync_db: Any
) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    boss, _, zone = _setup(ws, sync_db, now)
    local = now.astimezone(ZoneInfo(zone))
    policy = {
        "enabled": True,
        "midday_enabled": False,
        "midday_time": (local - timedelta(minutes=20)).strftime("%H:%M"),
        "evening_time": (local - timedelta(minutes=2)).strftime("%H:%M"),
    }
    assert ws.patch("/companies/current", {"auto_reports": policy}).status_code == 200
    ws.mail.messages.clear()
    assert client.portal.call(_job(client).tick, now) == 1  # type: ignore[attr-defined]
    (message,) = ws.mail.messages
    assert message.to == boss.email and message.subject.startswith("[WorkPulse] Evening report")
    assert "the whole day until" in message.text and "Unproductive 25m" in message.text


def test_continuous_alert_needs_one_unbroken_stretch(ws: Workspace, client: TestClient, sync_db: Any) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    boss, worker, _ = _setup(ws, sync_db, now, split=True)
    policy = {
        "unproductive_alert_enabled": True,
        "unproductive_total_enabled": False,
        "unproductive_continuous_enabled": True,
        "unproductive_continuous_minutes": 20,
    }
    assert ws.patch("/companies/current", {"auto_reports": policy}).status_code == 200
    job = _job(client)
    ws.mail.messages.clear()
    client.portal.call(job.tick, now)  # type: ignore[attr-defined]
    assert ws.mail.messages == []  # 30 minutes in total, but split by 5 minutes of work

    sync_db["companies"].update_one(
        {"_id": company_id(sync_db, ws.admin.user_id)},
        {"$set": {"auto_reports.unproductive_continuous_minutes": 15}},
    )
    client.portal.call(job.tick, now + timedelta(minutes=1))  # type: ignore[attr-defined]
    to = [m.to for m in ws.mail.messages]
    assert sorted(to) == sorted([worker.email, worker.email, boss.email, boss.email])  # one per stretch
    first = next(m for m in ws.mail.messages if m.to == worker.email)
    assert first.subject == "[WorkPulse] Unproductive for 15m without a break"
    assert "netflix.com" in first.text and " from " in first.text and "once per stretch" in first.text
    ws.mail.messages.clear()
    client.portal.call(job.tick, now + timedelta(minutes=2))  # type: ignore[attr-defined]
    assert ws.mail.messages == []


def test_stretches_join_short_gaps_and_end_at_real_breaks() -> None:
    from app.services.auto_reports.stretches import unproductive_stretches
    from app.services.productivity.engine import Segment

    t0 = datetime(2026, 11, 17, 10, 0, tzinfo=UTC)

    def seg(start: float, minutes: float, category: str, name: str = "youtube.com") -> Segment:
        a = t0 + timedelta(minutes=start)
        return Segment(a, a + timedelta(minutes=minutes), "chrome.exe", "Chrome", name, category)

    stretches = unproductive_stretches(
        [
            seg(0, 10, "unproductive"),
            seg(11, 0.5, "neutral", "google.com"),  # a quick look elsewhere
            seg(11.5, 10, "unproductive", "instagram.com"),
            seg(22, 5, "productive", "crm.example.com"),  # real work: ends the stretch
            seg(27, 4, "unproductive"),
        ]
    )
    assert [round(s.seconds / 60) for s in stretches] == [20, 4]
    assert stretches[0].where() == "youtube.com (10m), instagram.com (10m)"


def test_admin_chooses_what_the_report_shows(ws: Workspace, client: TestClient, sync_db: Any) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    boss, _, zone = _setup(ws, sync_db, now)
    assert ws.get("/companies/current").json()["auto_reports"]["sections"][0] == "summary"  # all by default
    local = now.astimezone(ZoneInfo(zone))
    policy = {
        "enabled": True,
        "midday_enabled": False,
        "evening_time": (local - timedelta(minutes=2)).strftime("%H:%M"),
        "sections": ["categories", "customer_time", "start_time", "categories"],
    }
    saved = ws.patch("/companies/current", {"auto_reports": policy})
    assert saved.status_code == 200 and saved.json()["auto_reports"]["sections"] == [
        "start_time",
        "categories",
        "customer_time",
    ]
    assert ws.patch("/companies/current", {"auto_reports": {**policy, "sections": []}}).status_code == 422
    assert (
        ws.patch("/companies/current", {"auto_reports": {**policy, "sections": ["salary"]}}).status_code
        == 422
    )
    ws.mail.messages.clear()
    assert client.portal.call(_job(client).tick, now) == 1  # type: ignore[attr-defined]
    (message,) = ws.mail.messages
    assert message.to == boss.email and message.html
    assert "Started: " in message.text and "Unproductive: 25m" in message.text
    assert "Customer time: 0m" in message.text
    for left_out in (
        "Active:",
        "Idle:",
        "Top:",
        "Required hours",
        "7-day",
        "recorded activity",
        "netflix.com",
    ):
        assert left_out not in message.text, left_out
    assert ">Productive<" in message.html and ">Idle<" not in message.html and "netflix" not in message.html


def test_reports_can_go_to_department_heads_and_are_grouped_by_department(
    ws: Workspace, client: TestClient, sync_db: Any
) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    boss, worker, zone = _setup(ws, sync_db, now)
    head = ws.member("Hana Head", role="MANAGER")
    visa = ws.department("Visa", head_employee_id=head.employee_id)
    sales = ws.department("Sales")
    assert ws.patch(f"/employees/{worker.employee_id}", {"department_id": visa["id"]}).status_code == 200
    assert ws.patch(f"/employees/{boss.employee_id}", {"department_id": sales["id"]}).status_code == 200
    local = now.astimezone(ZoneInfo(zone))
    policy = {
        "enabled": True,
        "midday_enabled": False,
        "evening_time": (local - timedelta(minutes=2)).strftime("%H:%M"),
        "route_by": "department_head",
        "extra_recipients": ["director@example.com"],
    }
    assert ws.patch("/companies/current", {"auto_reports": policy}).status_code == 200
    ws.mail.messages.clear()
    assert client.portal.call(_job(client).tick, now) == 1  # type: ignore[attr-defined]
    to = {m.to: m for m in ws.mail.messages}
    # Wes is in Visa: the Visa head gets him (not his manager Maya, who has no one left to report on).
    assert head.email in to and "Wes Worker" in to[head.email].text and boss.email not in to
    # The director's e-mail covers everyone, grouped under department headings (no department last).
    text = to["director@example.com"].text
    assert text.index("== Sales ==") < text.index("== Visa ==")
    assert "== No department ==" not in text  # only the admin and the head, who have no WorkPulse computer
    assert ">Visa</td>" in (to["director@example.com"].html or "")
    assert "By department" in (
        to["director@example.com"].html or ""
    )  # several departments: a summary row each


def test_extra_recipients_choose_departments_teams_and_reports(
    ws: Workspace, client: TestClient, sync_db: Any
) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    boss, worker, zone = _setup(ws, sync_db, now)
    visa = ws.department("Visa")
    sales = ws.department("Sales")
    desk = ws.team("Desk A", department_id=visa["id"])
    assert (
        ws.patch(
            f"/employees/{worker.employee_id}", {"department_id": visa["id"], "team_id": desk["id"]}
        ).status_code
        == 200
    )
    assert ws.patch(f"/employees/{boss.employee_id}", {"department_id": sales["id"]}).status_code == 200
    local = now.astimezone(ZoneInfo(zone))
    policy = {
        "enabled": True,
        "midday_time": (local - timedelta(minutes=3)).strftime("%H:%M"),
        "evening_time": (local + timedelta(minutes=30)).strftime("%H:%M"),
        "send_to_managers": False,
        "extra_recipients": [
            {"email": "visa-hr@example.com", "department_ids": [visa["id"]]},
            {"email": "desk@example.com", "team_ids": [desk["id"]], "midday": False},  # evening only
            {"email": "sales@example.com", "department_ids": [sales["id"]]},
            "all@example.com",  # a plain address still means everyone, both reports
        ],
    }
    assert ws.patch("/companies/current", {"auto_reports": policy}).status_code == 200
    bad = {**policy, "extra_recipients": [{"email": "x@example.com", "midday": False, "evening": False}]}
    assert ws.patch("/companies/current", {"auto_reports": bad}).status_code == 422
    ws.mail.messages.clear()
    assert client.portal.call(_job(client).tick, now) == 1  # type: ignore[attr-defined]
    to = {m.to: m.text for m in ws.mail.messages}
    assert set(to) == {"visa-hr@example.com", "sales@example.com", "all@example.com"}  # desk@ is evening only
    assert "Wes Worker" in to["visa-hr@example.com"] and "Maya Manager" not in to["visa-hr@example.com"]
    assert "Maya Manager" in to["sales@example.com"] and "Wes Worker" not in to["sales@example.com"]
    assert "Wes Worker" in to["all@example.com"] and "Maya Manager" in to["all@example.com"]

    ws.mail.messages.clear()
    assert client.portal.call(_job(client).tick, now + timedelta(minutes=31)) == 1  # type: ignore[attr-defined]
    to = {m.to: m.text for m in ws.mail.messages}
    assert "desk@example.com" in to and "Wes Worker" in to["desk@example.com"]

    overview = ws.get("/auto-reports/overview").json()
    assert overview["emails_today"] == 7 and overview["email_daily_cap"] == 350
    visa_row = next(d for d in overview["departments"] if d["name"] == "Visa")
    assert visa_row["employees"] == 1 and visa_row["teams"][0]["name"] == "Desk A"
    wes = next(e for e in overview["employees"] if e["name"] == "Wes Worker")
    assert wes["department"] == "Visa" and wes["team"] == "Desk A" and wes["report_to"] is None
    assert sorted(wes["extra_recipients"]) == ["all@example.com", "desk@example.com", "visa-hr@example.com"]
    assert wes["reports_7d"] == 5  # mid-day: visa-hr, all; evening: visa-hr, desk, all
    all_row = next(r for r in overview["recipients"] if r["email"] == "all@example.com")
    assert all_row["sent"] == 2 and all_row["reports"] == 2


def test_daily_email_limit_stops_sending_and_is_recorded(
    ws: Workspace, client: TestClient, sync_db: Any
) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    _setup(ws, sync_db, now)
    job = _job(client)
    original = job._settings
    job._settings = original.model_copy(update={"report_email_daily_cap": 1})
    try:
        policy = {
            "enabled": True,
            "extra_recipients": ["a@example.com", "b@example.com"],
            "send_to_managers": False,
        }
        assert ws.patch("/companies/current", {"auto_reports": policy}).status_code == 200
        ws.mail.messages.clear()
        response = ws.post("/auto-reports/test", {"slot": "midday"})
        assert response.status_code == 200  # the first e-mail of the day fits
        assert len(ws.mail.messages) == 1
        assert (
            ws.post("/auto-reports/test", {"slot": "midday"}).status_code == 503
        )  # over the limit: not sent
        assert len(ws.mail.messages) == 1
        assert sync_db["auto_report_deliveries"].count_documents({"status": "over_limit"}) >= 1
    finally:
        job._settings = original
        assert ws.patch("/companies/current", {"auto_reports": {"enabled": False}}).status_code == 200


def test_unproductive_alerts_stay_with_the_manager_whatever_the_report_routing(
    ws: Workspace, client: TestClient, sync_db: Any
) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    boss, worker, _ = _setup(ws, sync_db, now)
    head = ws.member("Hana Head", role="MANAGER")
    visa = ws.department("Visa", head_employee_id=head.employee_id)
    assert ws.patch(f"/employees/{worker.employee_id}", {"department_id": visa["id"]}).status_code == 200
    policy = {
        "route_by": "department_head",
        "unproductive_alert_enabled": True,
        "unproductive_alert_minutes": 20,
    }
    assert ws.patch("/companies/current", {"auto_reports": policy}).status_code == 200
    ws.mail.messages.clear()
    client.portal.call(_job(client).tick, now)  # type: ignore[attr-defined]
    ours = {worker.email, boss.email, head.email}
    # The employee and their manager, not the department head.
    assert {m.to for m in ws.mail.messages if m.to in ours} == {worker.email, boss.email}


def test_extra_content_items_and_alert_history(ws: Workspace, client: TestClient, sync_db: Any) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    boss, worker, zone = _setup(ws, sync_db, now)
    local = now.astimezone(ZoneInfo(zone))
    visa = ws.department("Visa")
    assert ws.patch(f"/employees/{worker.employee_id}", {"department_id": visa["id"]}).status_code == 200
    # The workday starts 2 hours before "now": Wes started 80 minutes ago, so he was 40 minutes late.
    start = (local - timedelta(hours=2)).strftime("%H:%M")
    sync_db["companies"].update_one(
        {"_id": company_id(sync_db, ws.admin.user_id)}, {"$set": {"start_check_time": start}}
    )
    policy = {
        "enabled": True,
        "midday_enabled": False,
        "evening_time": (local - timedelta(minutes=2)).strftime("%H:%M"),
        "sections": ["start_time", "last_sign_out", "late_start", "meetings", "tasks", "screenshots"],
        "unproductive_alert_enabled": True,
        "unproductive_alert_minutes": 20,
    }
    assert ws.patch("/companies/current", {"auto_reports": policy}).status_code == 200
    ws.mail.messages.clear()
    client.portal.call(_job(client).tick, now)  # type: ignore[attr-defined]
    report = next(m for m in ws.mail.messages if m.to == boss.email and "Evening report" in m.subject)
    assert f"Last out: {(now - timedelta(minutes=5)).astimezone(ZoneInfo(zone)):%H:%M}" in report.text
    # 40 minutes plus the seconds the workday start was rounded down by.
    assert ("Late: 40m" in report.text or "Late: 41m" in report.text) and "Meetings: 0m" in report.text
    assert "Task time: 0m" in report.text and "Screenshots: 0" in report.text

    day = local.date().isoformat()
    history = ws.get("/auto-reports/alerts", start=day, end=day).json()
    (alert,) = history
    assert alert["employee"] == "Wes Worker" and alert["department"] == "Visa"
    assert alert["manager"] == "Maya Manager" and alert["kind"] == "total" and alert["minutes"] == 25
    assert "netflix.com" in alert["where"]
    assert ws.get("/auto-reports/alerts", start=day, end="2020-01-01").status_code == 400


def test_employees_get_their_own_report_with_per_person_switch_and_content(
    ws: Workspace, client: TestClient, sync_db: Any
) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    boss, worker, zone = _setup(ws, sync_db, now)
    quiet = ws.member("Quinn Quiet")
    local = now.astimezone(ZoneInfo(zone))
    policy = {
        "enabled": True,
        "midday_enabled": False,
        "evening_time": (local - timedelta(minutes=2)).strftime("%H:%M"),
        "send_to_managers": False,
        "employee_reports_enabled": True,
        "employee_midday": False,
        "employee_sections": ["start_time", "categories"],
        "employee_settings": [
            {"employee_id": quiet.employee_id, "enabled": False},
            {"employee_id": worker.employee_id, "sections": ["top_apps", "late_start"]},
            {"employee_id": boss.employee_id, "enabled": True},  # nothing special: dropped
        ],
    }
    saved = ws.patch("/companies/current", {"auto_reports": policy})
    assert saved.status_code == 200, saved.text
    assert [s["employee_id"] for s in saved.json()["auto_reports"]["employee_settings"]] == [
        quiet.employee_id,
        worker.employee_id,
    ]
    bad = {**policy, "employee_settings": [{"employee_id": worker.employee_id, "sections": []}]}
    assert ws.patch("/companies/current", {"auto_reports": bad}).status_code == 422
    ws.mail.messages.clear()
    assert client.portal.call(_job(client).tick, now) == 1  # type: ignore[attr-defined]
    own = {m.to: m for m in ws.mail.messages if m.subject.startswith("[WorkPulse] Your evening report")}
    assert quiet.email not in own  # switched off for Quinn
    wes = own[worker.email]
    assert "Hi Wes," in wes.text and "Maya" not in wes.text  # only their own figures
    assert wes.html and "Hi Wes, here&rsquo;s your" in wes.html and "How your numbers work" in wes.html
    assert "Top: " in wes.text and "Started:" not in wes.text  # Wes's own content
    maya = own[boss.email]
    assert (
        "Started: " in maya.text and "Unproductive " in maya.text and "Top:" not in maya.text
    )  # the default
    assert maya.html and "Where your time went" in maya.html


def test_manager_report_glance_actions_week_and_team_total(
    ws: Workspace, client: TestClient, sync_db: Any
) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    boss, worker, zone = _setup(ws, sync_db, now)
    second, agent2 = enrol_member(ws, "Sara Second", manager_employee_id=boss.employee_id)
    _work_today(agent2, now, netflix_minutes=5)
    cid = company_id(sync_db, ws.admin.user_id)
    # Something waiting for the manager: a meeting claim to approve and a task past its due date.
    sync_db["time_claims"].insert_one(
        {
            "company_id": cid,
            "employee_id": ObjectId(worker.employee_id),
            "status": "pending",
            "day": "2026-01-01",
        }
    )
    sync_db["tasks"].insert_one(
        {
            "company_id": cid,
            "project_id": ObjectId(),
            "number": 1,
            "title": "Send visa documents",
            "created_at": now.replace(tzinfo=None),
            "updated_at": now.replace(tzinfo=None),
            "assignee_ids": [ObjectId(second.employee_id)],
            "status": "TODO",
            "due_date": now.replace(tzinfo=None) - timedelta(days=3),
        }
    )
    local = now.astimezone(ZoneInfo(zone))
    policy = {
        "enabled": True,
        "midday_enabled": False,
        "evening_time": (local - timedelta(minutes=2)).strftime("%H:%M"),
        "sections": [
            "highlights",
            "action_items",
            "categories",
            "week",
            "week_compare",
            "long_breaks",
            "overtime",
            "team_totals",
        ],
    }
    assert ws.patch("/companies/current", {"auto_reports": policy}).status_code == 200
    ws.mail.messages.clear()
    assert client.portal.call(_job(client).tick, now) == 1  # type: ignore[attr-defined]
    mail = next(m for m in ws.mail.messages if m.to == boss.email)
    text = mail.text
    assert "At a glance:" in text and "Most unproductive: Wes Worker (25m, mostly netflix.com)" in text
    assert "Needs your action:" in text
    assert "1 meeting claim to approve: Wes Worker" in text and "1 overdue task: Sara Second" in text
    assert "Week: " in text and "Long breaks: " in text and "vs last week: " in text
    assert "• Team total" in text and "Unproductive: 30m" in text  # 25m + 5m
    assert (
        mail.html
        and "At a glance" in mail.html
        and "Needs your action" in mail.html
        and "Team productive" in mail.html
    )


def test_a_manager_with_an_own_report_gets_one_email_with_their_figures_first(
    ws: Workspace, client: TestClient, sync_db: Any
) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    boss, worker, zone = _setup(ws, sync_db, now)
    local = now.astimezone(ZoneInfo(zone))
    policy = {
        "enabled": True,
        "midday_enabled": False,
        "evening_time": (local - timedelta(minutes=2)).strftime("%H:%M"),
        "sections": ["categories", "team_totals"],
        "employee_reports_enabled": True,
        "employee_midday": False,
    }
    assert ws.patch("/companies/current", {"auto_reports": policy}).status_code == 200
    ws.mail.messages.clear()
    assert client.portal.call(_job(client).tick, now) == 1  # type: ignore[attr-defined]
    to_boss = [m for m in ws.mail.messages if m.to == boss.email]
    assert len(to_boss) == 1  # not a separate "Your evening report" for Maya
    text = to_boss[0].text
    assert text.index("== Your own figures ==") < text.index("• Maya Manager") < text.index("• Wes Worker")
    # The team total counts the team only (Wes's 25 minutes), not Maya herself.
    assert text.split("• Team total")[1].count("Unproductive: 25m") == 1
    # Wes, who manages no one, still gets his own report.
    assert any(
        m.to == worker.email and m.subject.startswith("[WorkPulse] Your evening report")
        for m in ws.mail.messages
    )


def test_evening_report_says_met_or_short_not_in_progress(
    ws: Workspace, client: TestClient, sync_db: Any
) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    boss, _worker, zone = _setup(ws, sync_db, now)
    idle_one, _ = enrol_member(
        ws, "Ida Idle", manager_employee_id=boss.employee_id
    )  # computer, no work today
    cid = company_id(sync_db, ws.admin.user_id)
    sync_db["companies"].update_one({"_id": cid}, {"$set": {"required_minutes": [480] * 7}})  # 8 h every day
    local = now.astimezone(ZoneInfo(zone))
    policy = {
        "enabled": True,
        "midday_enabled": False,
        "evening_time": (local - timedelta(minutes=2)).strftime("%H:%M"),
        "sections": ["required_hours", "summary"],
    }
    assert ws.patch("/companies/current", {"auto_reports": policy}).status_code == 200
    ws.mail.messages.clear()
    assert client.portal.call(_job(client).tick, now) == 1  # type: ignore[attr-defined]
    mail = next(m for m in ws.mail.messages if m.to == boss.email)
    text = mail.text
    html = mail.html or ""
    assert "Required hours today" in html and "0 of 2 met their day" in html
    assert "Required hours met" in html  # the tile
    assert "In progress" not in text
    assert (
        "Required hours: Short (8h 00m)" in text and "Did not meet the required hours" in text
    )  # Wes worked ~1 h
    assert "Required hours: Absent (8h 00m)" in text  # Ida did nothing today
    assert "0 of 1 met the required hours." in text
    assert idle_one.email


def test_employee_report_layout_shows_today_met_or_not_and_lists(
    ws: Workspace, client: TestClient, sync_db: Any
) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    _boss, worker, zone = _setup(ws, sync_db, now)
    cid = company_id(sync_db, ws.admin.user_id)
    sync_db["companies"].update_one({"_id": cid}, {"$set": {"required_minutes": [60] * 7}})  # 1 h every day
    local = now.astimezone(ZoneInfo(zone))
    policy = {
        "enabled": True,
        "midday_enabled": False,
        "evening_time": (local - timedelta(minutes=2)).strftime("%H:%M"),
        "send_to_managers": False,
        "employee_reports_enabled": True,
        "employee_midday": False,
        "employee_sections": [
            "summary",
            "productive_share",
            "start_time",
            "week",
            "average",
            "categories",
            "focus",
            "long_breaks",
            "required_hours",
        ],
    }
    assert ws.patch("/companies/current", {"auto_reports": policy}).status_code == 200
    ws.mail.messages.clear()
    client.portal.call(_job(client).tick, now)  # type: ignore[attr-defined]
    mail = next(m for m in ws.mail.messages if m.to == worker.email)
    html = mail.html or ""
    for part in (
        "Productive %",
        "Started",
        "Required hours · this week",
        "vs your 7-day average",
        "Today&rsquo;s required hours",
        "Your day in brief",
        "Where your time went",
        "Focus sessions",
        "Long breaks",
        "How your numbers work",
    ):
        assert part in html, part
    assert "✓ Met" in html  # Wes worked over an hour against a 1-hour requirement
    assert "Today: Met" in mail.text and "Focus sessions: 1" in mail.text


def test_people_without_a_workpulse_computer_are_left_out(
    ws: Workspace, client: TestClient, sync_db: Any
) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    boss, _worker, zone = _setup(ws, sync_db, now)
    office = ws.member("Olive Office", manager_employee_id=boss.employee_id)  # website only, no agent
    local = now.astimezone(ZoneInfo(zone))
    policy = {
        "enabled": True,
        "midday_enabled": False,
        "evening_time": (local - timedelta(minutes=2)).strftime("%H:%M"),
        "extra_recipients": ["hr@example.com"],
    }
    assert ws.patch("/companies/current", {"auto_reports": policy}).status_code == 200
    ws.mail.messages.clear()
    client.portal.call(_job(client).tick, now)  # type: ignore[attr-defined]
    hr = next(m for m in ws.mail.messages if m.to == "hr@example.com").text
    assert (
        "Wes Worker" in hr and "Olive Office" not in hr and "Ada Admin" not in hr
    )  # the admin has no computer
    names = [e["name"] for e in ws.get("/auto-reports/overview").json()["employees"]]
    assert office.email and "Olive Office" not in names and "Ada Admin" not in names


def test_manager_email_compares_this_week_with_last_week() -> None:
    from app.services.auto_reports.team import _weekly

    def person(name: str, now_prod: float, last_prod: float | None) -> PersonReport:
        this = Figures(
            work=7 * 3600, active=6 * 3600, idle=3600, productive=now_prod, neutral=3600, unproductive=1800
        )
        last = (
            Figures(
                work=7 * 3600,
                active=6 * 3600,
                idle=2 * 3600,
                productive=last_prod,
                neutral=3600,
                unproductive=3600,
            )
            if last_prod is not None
            else None
        )
        p = _person(name, work=3600, active=3000)
        p.this_week, p.last_week = this, last
        return p

    html = _weekly(
        [
            person("Rahul", 6 * 3600, 3 * 3600),
            person("Vivek", 2 * 3600, 4 * 3600),
            person("New", 4 * 3600, None),
        ]
    )
    assert "This week vs last week" in html and "Most improved" in html and "Biggest drops" in html
    assert "Rahul" in html.split("Most improved")[1].split("Biggest drops")[0]  # went up
    assert "Vivek" in html.split("Biggest drops")[1]  # went down
    assert "New" not in html  # no week to compare with
    assert "▲" in html and "▼" in html
    empty = _weekly([person("New", 4 * 3600, None)])
    assert "comparison starts once there is a week of history" in empty
