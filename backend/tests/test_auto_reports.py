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
    boss = ws.member("Maya Manager", role="MANAGER")
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
    boss, worker, zone = _setup(ws, sync_db, now)
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
    assert digest.subject.startswith("[WorkPulse] Mid-day report") and "1 person" in digest.subject
    assert (
        "Wes Worker" in digest.text and "Maya Manager" not in digest.text.split("Hello")[1].split("\n", 1)[1]
    )
    assert digest.html and "Wes Worker" in digest.html and "netflix.&#8203;com" in digest.html  # not a link
    assert "Unproductive" in digest.text and "Visual Studio Code" in digest.text
    # Started = the first activity today, with the sign-in sessions as on the Attendance page.
    started = (now - timedelta(minutes=80)).astimezone(ZoneInfo(zone)).strftime("%H:%M")
    assert f"Started: {started}" in digest.text and f"Signed in: {started} to " in digest.text
    assert f"Started {started}" in digest.html
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
        "plus the whole day" in evening.text
        and "Day active: " in evening.text
        and "Required hours: " in evening.text
    )
    runs = ws.get("/auto-reports/status").json()["runs"]
    assert [(r["slot"], r["status"], r["sent"]) for r in runs] == [
        ("evening", "done", 2),
        ("midday", "done", 2),
    ]
    snapshot = sync_db["auto_report_snapshots"].find_one({"employee_id": ObjectId(worker.employee_id)})
    assert snapshot and snapshot["figures"]["unproductive"] >= 20 * 60


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
    assert alert and alert[0]["title"] == "Wes Worker passed 20 minutes of Unproductive time today"
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
    assert text.index("== Sales ==") < text.index("== Visa ==") < text.index("== No department ==")
    assert ">Visa</td>" in (to["director@example.com"].html or "")


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
