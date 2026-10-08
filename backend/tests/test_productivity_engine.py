"""Phase 8: the pure productivity engine — rules, time accounting, categories, focus, scores, insights."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from bson import ObjectId

from app.models.agent import PresenceChange, WorkSession
from app.models.productivity import Category, ProductivityRule, RuleKind, RuleScope
from app.services.productivity.engine import (
    EXTENDED_IDLE_SECONDS,
    FOCUS_MIN_SECONDS,
    Metrics,
    Segment,
    activity_score,
    category_time,
    context_switches,
    focus_score,
    focus_sessions,
    insights,
    productive_share,
    session_pieces,
    summary,
    time_accounting,
    work_utilization,
)
from app.services.productivity.rules import EmployeeContext, RuleBook

CO = ObjectId()
DEPT, TEAM, OTHER_TEAM = ObjectId(), ObjectId(), ObjectId()
T0 = datetime(2026, 9, 28, 9, 0, tzinfo=UTC)  # a Monday
UTCZ = ZoneInfo("UTC")


def rule(
    kind: RuleKind, pattern: str, category: Category, scope: RuleScope = RuleScope.COMPANY, **kw: object
) -> ProductivityRule:
    return ProductivityRule(company_id=CO, kind=kind, pattern=pattern, category=category, scope=scope, **kw)  # type: ignore[arg-type]


RULES = [
    rule(RuleKind.APP, "slack.exe", Category.NEUTRAL),
    rule(RuleKind.APP, "slack.exe", Category.UNPRODUCTIVE, RuleScope.ROLE, role="EMPLOYEE"),
    rule(RuleKind.APP, "slack.exe", Category.PRODUCTIVE, RuleScope.DEPARTMENT, scope_id=DEPT),
    rule(RuleKind.APP, "slack.exe", Category.UNPRODUCTIVE, RuleScope.TEAM, scope_id=TEAM),
    rule(RuleKind.APP, "code.exe", Category.PRODUCTIVE),
    rule(RuleKind.APP, "spotify", Category.UNPRODUCTIVE),  # by display name
    rule(RuleKind.WEBSITE, "google.com", Category.UNPRODUCTIVE),
    rule(RuleKind.WEBSITE, "docs.google.com", Category.PRODUCTIVE),
    rule(RuleKind.WEBSITE, "github.com", Category.PRODUCTIVE),
]


def book(
    department: ObjectId | None = None, team: ObjectId | None = None, role: str | None = None
) -> RuleBook:
    return RuleBook(RULES, EmployeeContext(department, team, role))


# --------------------------------------------------------------------------- rules


def test_most_specific_scope_wins() -> None:
    assert book().app("slack.exe", "Slack").category == "neutral"  # company
    assert book(role="EMPLOYEE").app("slack.exe", "Slack").category == "unproductive"  # role beats company
    assert (
        book(DEPT, role="EMPLOYEE").app("slack.exe", "Slack").category == "productive"
    )  # department beats role
    assert (
        book(DEPT, TEAM, "EMPLOYEE").app("slack.exe", "Slack").category == "unproductive"
    )  # team beats department
    assert (
        book(DEPT, OTHER_TEAM).app("slack.exe", "Slack").category == "productive"
    )  # other team's rule ignored
    match = book(DEPT, TEAM).app("slack.exe", "Slack")
    assert (match.scope, match.pattern) == ("team", "slack.exe")


def test_apps_by_executable_or_name_and_unclassified() -> None:
    assert book().app("code.exe", "Visual Studio Code").category == "productive"
    assert book().app("spotify.exe", "Spotify").category == "unproductive"
    assert book().app("notepad.exe", "Notepad").category == "unclassified"


def test_websites_match_subdomains_most_specific_first() -> None:
    b = book()
    assert b.website("docs.google.com").category == "productive"
    assert b.website("mail.google.com").category == "unproductive"
    assert b.website("api.github.com").category == "productive"
    assert b.website("notgoogle.com").category == "unclassified"
    assert b.website("google.com.evil.io").category == "unclassified"
    # Browser time follows the website; other apps ignore any domain.
    assert b.classify("chrome.exe", "Chrome", "github.com").category == "productive"
    assert b.classify("chrome.exe", "Chrome", None).category == "unclassified"


# --------------------------------------------------------------------------- work, active, idle, away


def session(
    start: datetime, minutes: int, changes: list[tuple[int, str]] | None = None, **kw: object
) -> WorkSession:
    return WorkSession(
        company_id=CO,
        employee_id=ObjectId(),
        device_id=ObjectId(),
        client_session_id="s",
        started_at=start,
        ended_at=start + timedelta(minutes=minutes),
        presence_changes=[
            PresenceChange(at=start + timedelta(minutes=m), status=s) for m, s in (changes or [])
        ],  # type: ignore[arg-type]
        **kw,  # type: ignore[arg-type]
    )


def test_active_and_idle_from_recorded_presence_changes() -> None:
    s = session(T0, 120, [(30, "idle"), (45, "active"), (100, "idle")])
    day = time_accounting([s], [T0.date()], UTCZ, T0 + timedelta(days=1))[T0.date()]
    assert day.work == 120 * 60
    assert day.active == (30 + 55) * 60 and day.idle == (15 + 20) * 60
    assert day.away == 0


def test_away_is_the_gap_between_sessions_and_midnight_is_split() -> None:
    morning = session(T0, 180)  # 09:00-12:00
    afternoon = session(T0 + timedelta(hours=4), 240)  # 13:00-17:00
    late = session(datetime(2026, 9, 28, 23, 0, tzinfo=UTC), 120)  # 23:00-01:00
    days = [date(2026, 9, 28), date(2026, 9, 29)]
    result = time_accounting([morning, afternoon, late], days, UTCZ, T0 + timedelta(days=3))
    monday, tuesday = result[days[0]], result[days[1]]
    assert monday.work == (3 + 4 + 1) * 3600 and tuesday.work == 3600
    assert monday.away == (1 + 6) * 3600  # lunch 12-13 and 17-23 (between last session and the late one)


def test_older_sessions_are_prorated_and_open_sessions_count_as_active() -> None:
    old = session(T0, 100, active_seconds=4500, idle_seconds=1500)
    (piece,) = session_pieces(old, T0 + timedelta(days=1))
    assert piece[2] == 0.75
    running = WorkSession(
        company_id=CO, employee_id=ObjectId(), device_id=ObjectId(), client_session_id="r", started_at=T0
    )
    (piece,) = session_pieces(running, T0 + timedelta(minutes=10))
    assert piece[2] == 1.0 and (piece[1] - piece[0]).total_seconds() == 600


# --------------------------------------------------------------------------- categories


def test_browser_time_is_split_between_websites_and_the_browser_rule() -> None:
    apps = [
        {"app_id": "chrome.exe", "app_name": "Google Chrome", "seconds": 3600},
        {"app_id": "code.exe", "app_name": "Visual Studio Code", "seconds": 1800},
    ]
    sites = [
        {"app_id": "chrome.exe", "domain": "github.com", "seconds": 1200},
        {"app_id": "chrome.exe", "domain": "mail.google.com", "seconds": 600},
    ]
    per_category, items = category_time(apps, sites, book())
    assert per_category == {
        "productive": 1800 + 1200,
        "neutral": 0,
        "unproductive": 600,
        "unclassified": 1800,
    }
    assert items[("app", "chrome.exe")].seconds == 1800  # browser time without a known website
    assert items[("website", "mail.google.com")].rule_pattern == "google.com"


# --------------------------------------------------------------------------- focus and switching


def seg(start_min: float, minutes: float, category: str, app: str = "code.exe") -> Segment:
    s = Segment(
        T0 + timedelta(minutes=start_min), T0 + timedelta(minutes=start_min + minutes), app, app, None
    )
    s.category = category
    return s


def test_focus_sessions_tolerate_brief_neutral_switches_only() -> None:
    steady = [seg(0, 15, "productive"), seg(15, 1, "neutral", "slack.exe"), seg(16, 15, "productive")]
    (focus,) = focus_sessions(steady)
    assert focus.seconds == 31 * 60 and focus.productive_seconds == 30 * 60

    broken = [seg(0, 15, "productive"), seg(15, 3, "unproductive", "steam.exe"), seg(18, 15, "productive")]
    assert focus_sessions(broken) == []  # neither half reaches 25 minutes

    gap = [seg(0, 20, "productive"), seg(25, 20, "productive")]  # 5 minutes away in between
    assert focus_sessions(gap) == []

    long_one = [seg(0, 10, "productive"), seg(10, 0.5, "unproductive", "x"), seg(10.5, 20, "productive")]
    (focus,) = focus_sessions(long_one)  # a 30-second unproductive blip is tolerated
    assert focus.seconds >= FOCUS_MIN_SECONDS


def test_context_switches_count_changes_close_in_time() -> None:
    segments = [
        seg(0, 5, "productive"),
        seg(5, 1, "neutral", "slack.exe"),
        seg(6, 5, "productive"),
        seg(30, 5, "productive"),
    ]
    assert context_switches(segments) == 2


# --------------------------------------------------------------------------- scores and insights


def test_scores_expose_formula_components_and_refuse_thin_data() -> None:
    m = Metrics(
        work=8 * 3600,
        active=6 * 3600,
        idle=2 * 3600,
        productive=4 * 3600,
        neutral=3600,
        unproductive=3600,
        unclassified=1800,
    )
    activity = activity_score(m)
    assert activity["value"] == 75 and "not a measure of productivity" in activity["interpretation"]
    assert [c["seconds"] for c in activity["components"]] == [6 * 3600, 8 * 3600]
    share = productive_share(m)
    assert share["value"] == 67 and share["coverage"] == 92
    assert {c["key"] for c in share["components"]} >= {"productive_seconds", "unclassified_seconds"}

    thin = productive_share(Metrics(work=3600, productive=600))
    assert thin["value"] is None and thin["status"] == "insufficient_data" and "30 minutes" in thin["reason"]
    uncovered = productive_share(Metrics(work=8 * 3600, productive=1200, unclassified=6 * 3600))
    assert uncovered["value"] is None and "rules" in uncovered["reason"]
    assert activity_score(Metrics())["value"] is None


def test_insights_reference_their_metrics() -> None:
    from app.services.productivity.engine import UsageItem

    m = Metrics(
        work=8 * 3600,
        active=5 * 3600,
        idle=3 * 3600,
        productive=3 * 3600,
        unclassified=2 * 3600,
        focus_count=2,
        focus_seconds=3600,
        longest_focus_seconds=2400,
    )
    items = [UsageItem("app", "notion.exe", "Notion", 2 * 3600)]
    found = insights(m, None, items, 1)
    titles = " | ".join(i["title"] for i in found)
    assert "unclassified" in titles and "focus session" in titles and "idle" in titles
    assert all(i["metrics"] for i in found)
    assert insights(Metrics(), None, [], 0)[0]["title"] == "No work sessions in this period"


def test_abandoned_open_sessions_end_where_the_device_was_last_seen() -> None:
    from app.models.organization import Device
    from app.services.work_sessions import effective_end

    grace = timedelta(minutes=3)
    now = T0 + timedelta(days=3)
    open_session = WorkSession(
        company_id=CO, employee_id=ObjectId(), device_id=ObjectId(), client_session_id="s1", started_at=T0
    )
    device = Device(
        company_id=CO,
        employee_id=open_session.employee_id,
        name="Laptop",
        last_seen_at=T0 + timedelta(hours=2),
        current_session_id="s1",
    )
    assert effective_end(open_session, device, now, grace) == T0 + timedelta(
        hours=2, minutes=3
    )  # agent vanished
    device.current_session_id = "s2"
    assert effective_end(
        open_session, device, now, grace, last_activity=T0 + timedelta(hours=1)
    ) == T0 + timedelta(hours=1)
    device.last_seen_at, device.current_session_id = now - timedelta(seconds=30), "s1"
    assert effective_end(open_session, device, now, grace) == now  # still reporting: running session
    day = time_accounting([open_session], [T0.date()], UTCZ, now, {open_session.id: T0 + timedelta(hours=2)})[
        T0.date()
    ]
    assert day.work == 2 * 3600


def test_a_session_the_device_left_ends_when_its_next_session_starts() -> None:
    from app.models.organization import Device
    from app.services.work_sessions import effective_ends

    grace = timedelta(minutes=3)
    now = T0 + timedelta(days=2)
    device_id = ObjectId()
    stale = WorkSession(
        company_id=CO, employee_id=ObjectId(), device_id=device_id, client_session_id="old", started_at=T0
    )
    later = WorkSession(
        company_id=CO,
        employee_id=stale.employee_id,
        device_id=device_id,
        client_session_id="new",
        started_at=T0 + timedelta(hours=3),
    )
    device = Device(
        id=device_id,
        company_id=CO,
        employee_id=stale.employee_id,
        name="L",
        last_seen_at=now - timedelta(seconds=10),
        current_session_id="new",
    )
    ends = effective_ends([later, stale], {device_id: device}, now, grace)
    assert ends[stale.id] == T0  # no evidence of activity: no time is invented
    ends = effective_ends(
        [later, stale], {device_id: device}, now, grace, {"old": T0 + timedelta(minutes=50)}
    )
    assert ends[stale.id] == T0 + timedelta(minutes=50)  # last recorded activity, not two days later
    assert ends[later.id] == now  # still running


# --------------------------------------------------------------------------- Phase 12: profiles, extended idle, focus & utilization
PROFILE = ObjectId()


def test_work_profile_rules_are_the_most_specific() -> None:
    rules = [
        *RULES,
        rule(RuleKind.APP, "slack.exe", Category.PRODUCTIVE, RuleScope.PROFILE, scope_id=PROFILE),
    ]
    support = RuleBook(rules, EmployeeContext(DEPT, TEAM, "EMPLOYEE", PROFILE))
    assert support.app("slack.exe", "Slack").category == "productive"  # beats the team rule
    assert support.app("slack.exe", "Slack").scope == "profile"
    colleague = RuleBook(rules, EmployeeContext(DEPT, TEAM, "EMPLOYEE", None))
    assert colleague.app("slack.exe", "Slack").category == "unproductive"  # the team rule still applies


def test_extended_idle_needs_long_exact_idle_stretches() -> None:
    assert EXTENDED_IDLE_SECONDS == 15 * 60
    s = session(T0, 180, [(30, "idle"), (40, "active"), (60, "idle"), (90, "active")])
    day = time_accounting([s], [T0.date()], UTCZ, T0 + timedelta(days=1))[T0.date()]
    assert day.idle == 40 * 60 and day.extended_idle == 30 * 60  # the 10-minute stretch doesn't count
    old = session(T0, 60, active_seconds=0, idle_seconds=3600)  # totals only: stretches unknown
    assert time_accounting([old], [T0.date()], UTCZ, T0 + timedelta(days=1))[T0.date()].extended_idle == 0


def test_focus_score_and_work_utilization_are_explained_and_guarded() -> None:
    f = focus_score(Metrics(productive=3600, focus_seconds=1800))
    assert f["value"] == 50 and f["formula"].startswith("Time in focus sessions")
    assert {c["key"] for c in f["components"]} == {"focus_seconds", "productive_seconds"}
    assert focus_score(Metrics(productive=1000, focus_seconds=1000))["value"] is None

    u = work_utilization(Metrics(work=7200, task_seconds=3600))
    assert u["value"] == 50 and u["reason"] is None and "nor a goal" in u["interpretation"]
    over = work_utilization(Metrics(work=3600, task_seconds=5400))
    assert over["value"] == 100 and "capped" in over["reason"]
    assert work_utilization(Metrics(work=600, task_seconds=600))["value"] is None


def test_summary_lines_name_the_measurements_behind_them() -> None:
    m = Metrics(active=6 * 3600 + 42 * 60, productive=5 * 3600 + 21 * 60, extended_idle=32 * 60)
    m.tasks_completed, m.tasks_due_open = 7, 1
    lines = {line["key"]: line for line in summary(m)}
    assert lines["active"]["value"] == "6h 42m" and lines["active"]["metrics"] == ["active_seconds"]
    assert lines["task_completion"]["value"] == "88%"
    assert lines["productive"]["value"] == "5h 21m" and lines["extended_idle"]["value"] == "32m"
    observed = insights(
        Metrics(work=8 * 3600, active=7 * 3600, idle=3600, extended_idle=45 * 60), None, [], 1
    )
    assert any(i["metrics"][0] == "extended_idle_seconds" for i in observed)
