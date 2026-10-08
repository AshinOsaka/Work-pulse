"""Phase 5: application activity tracking on the device (privacy rules, segments, batching)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest

from app.activity.foreground import ForegroundApp
from app.activity.privacy import ActivityPolicy, is_sensitive, permitted_title, redact_title
from app.activity.tracker import MAX_SEGMENT_SECONDS, ActivityTracker
from app.agent import Agent, tracking_label
from tests.conftest import PASSWORD, FakeApi, FakeIdle, FakeProbe

CODE = ForegroundApp("code.exe", "Visual Studio Code", "main.py - WorkPulse")
CHROME = ForegroundApp("chrome.exe", "Google Chrome", "Pull request #12 - GitHub")
TITLES = ActivityPolicy(capture_window_titles=True)


class Clock:
    def __init__(self) -> None:
        self.now = 1_000_000.0

    def __call__(self) -> float:
        return self.now


def drive(tracker: ActivityTracker, clock: Clock, seconds: int, *, session: str = "s1", working: bool = True) -> None:
    """Sample once per simulated second, as the activity monitor does."""
    for _ in range(seconds):
        tracker.sample(session, working)
        clock.now += 1
    tracker.sample(session, working)


class Harness:
    def __init__(self, policy: ActivityPolicy | None = None, app: ForegroundApp | None = CODE) -> None:
        self.events: list[dict[str, Any]] = []
        self.clock = Clock()
        self.idle = FakeIdle()
        self.probe = FakeProbe(app)
        self.tracker = ActivityTracker(self.events.append, self.probe, self.idle, policy=policy, clock=self.clock)

    def run(self, seconds: int, working: bool = True) -> None:
        drive(self.tracker, self.clock, seconds, working=working)


# --- privacy rules ---------------------------------------------------------------------------


def test_titles_are_never_kept_for_sensitive_apps_or_private_browsing() -> None:
    assert is_sensitive("KeePassXC.exe", "Database.kdbx")
    assert is_sensitive("chrome.exe", "New Tab - Incognito")
    assert is_sensitive("msedge.exe", "Bank - [InPrivate] - Microsoft Edge")
    assert is_sensitive("slack.exe", "general")
    assert not is_sensitive("code.exe", "main.py")

    assert permitted_title(TITLES, "1password.exe", "Vault") is None
    assert permitted_title(TITLES, "firefox.exe", "Mozilla Firefox Private Browsing") is None
    assert permitted_title(ActivityPolicy(), "code.exe", "main.py") is None  # titles are off by default
    assert permitted_title(TITLES, "code.exe", "main.py") == "main.py"


def test_titles_are_redacted() -> None:
    title = redact_title("Invoice for jane.doe@example.com https://pay.example.com/x?id=1 card 4111 1111 1111 1111")
    assert title == "Invoice for [email] [link] card [number]"
    long = redact_title("x" * 500)
    assert long is not None and len(long) == 200


def test_policy_from_server_payload() -> None:
    policy = ActivityPolicy.from_dict(
        {"track_applications": True, "capture_window_titles": True, "excluded_apps": [" Spotify ", ""]}
    )
    assert policy.excludes("spotify.exe", "Spotify") and not policy.excludes("code.exe", "Visual Studio Code")
    assert ActivityPolicy.from_dict(None) == ActivityPolicy()
    assert tracking_label(ActivityPolicy(track_applications=False)) == "Work time only"


# --- segments --------------------------------------------------------------------------------


def test_one_segment_per_application_run() -> None:
    h = Harness()
    h.run(30)
    h.probe.app = CHROME
    h.run(20)
    h.tracker.close()

    assert [e["type"] for e in h.events] == ["activity.segment", "activity.segment"]
    first, second = h.events
    assert first["app_id"] == "code.exe" and first["app_name"] == "Visual Studio Code"
    assert first["session_id"] == "s1" and first["window_title"] is None
    assert first["active_seconds"] == pytest.approx(30) and first["activity_level"] == 100
    assert second["app_id"] == "chrome.exe" and second["active_seconds"] == pytest.approx(20)
    # Metadata only: nothing beyond these fields is ever produced.
    assert set(first) == {
        "id", "type", "occurred_at", "session_id", "app_id", "app_name", "window_title",
        "started_at", "ended_at", "active_seconds", "activity_level",
    }  # fmt: skip


def test_titles_only_read_and_sent_when_permitted() -> None:
    h = Harness()
    h.run(5)
    h.tracker.close()
    assert h.probe.title_requests and not any(h.probe.title_requests)  # the title is not even read
    assert h.events[0]["window_title"] is None

    h = Harness(policy=TITLES)
    h.run(5)
    h.probe.app = ForegroundApp("code.exe", "Visual Studio Code", "README.md - WorkPulse")
    h.run(5)
    h.tracker.close()
    assert [e["window_title"] for e in h.events] == ["main.py - WorkPulse", "README.md - WorkPulse"]


def test_low_input_lowers_activity_level_and_idle_closes_the_segment() -> None:
    h = Harness()
    h.run(20)
    h.idle.seconds = 60  # reading: no input for a minute, session not yet idle
    h.run(20)
    h.run(10, working=False)  # session went idle
    assert len(h.events) == 1
    segment = h.events[0]
    assert segment["active_seconds"] == pytest.approx(20)
    assert segment["activity_level"] == 50


def test_excluded_disabled_and_non_apps_produce_nothing() -> None:
    h = Harness(policy=ActivityPolicy(excluded_apps=frozenset({"visual studio code"})))
    h.run(30)
    h.tracker.close()
    assert h.events == []

    h = Harness(policy=ActivityPolicy(track_applications=False))
    h.run(30)
    h.tracker.close()
    assert h.events == [] and h.tracker.current_app_name is None
    assert h.probe.title_requests == []  # the foreground window is not even looked at

    h = Harness(app=ForegroundApp("lockapp.exe", "Lock App"))
    h.run(30)
    h.tracker.close()
    assert h.events == []


def test_flicker_is_dropped_and_long_runs_are_split() -> None:
    h = Harness()
    h.run(1)
    h.probe.app = CHROME
    h.run(30)
    h.tracker.close()
    assert [e["app_id"] for e in h.events] == ["chrome.exe"]

    h = Harness()
    h.run(MAX_SEGMENT_SECONDS * 2 + 60)
    h.tracker.close()
    assert len(h.events) == 3
    assert all(e["active_seconds"] <= MAX_SEGMENT_SECONDS for e in h.events)


def test_sleep_gap_is_not_counted() -> None:
    h = Harness()
    h.run(10)
    h.clock.now += 3600  # laptop lid closed for an hour
    h.run(10)
    h.tracker.close()
    assert len(h.events) == 2
    assert all(e["active_seconds"] <= 11 for e in h.events)


def test_clock_set_back_does_not_corrupt_segments() -> None:
    h = Harness()
    h.run(10)
    h.clock.now -= 600  # system clock adjusted backwards
    h.run(10)
    h.tracker.close()
    assert len(h.events) == 2
    assert all(e["ended_at"] > e["started_at"] for e in h.events)


def test_policy_change_closes_the_open_segment() -> None:
    h = Harness()
    h.run(10)
    h.tracker.set_policy(TITLES)
    assert len(h.events) == 1 and h.events[0]["window_title"] is None


# --- agent integration -----------------------------------------------------------------------


def signed_in(make_agent: Callable[..., Agent], probe: FakeProbe) -> tuple[Agent, Clock]:
    agent = make_agent(probe=probe)
    agent.sign_in("ada@example.com", PASSWORD)
    clock = Clock()
    agent.tracker._clock = clock  # simulated time for the tracker only
    return agent, clock


def event_requests(fake_api: FakeApi) -> int:
    return sum(1 for _, path in fake_api.requests if path.endswith("/agent/events"))


def test_segments_are_batched_into_few_requests(make_agent: Callable[..., Agent], fake_api: FakeApi) -> None:
    probe = FakeProbe(CODE)
    agent, clock = signed_in(make_agent, probe)
    agent.start_session()
    session_id = agent.sessions.session_id or ""
    for i in range(121):  # 120 application switches -> 120 segments
        probe.app = CODE if i % 2 == 0 else CHROME
        drive(agent.tracker, clock, 10, session=session_id)
    agent.tracker.close()
    assert agent.tracker.segments_emitted == 121

    before = event_requests(fake_api)
    agent.sync.flush()
    requests = event_requests(fake_api) - before
    assert fake_api.types().count("activity.segment") == 121
    assert requests <= 3  # batches of max_batch_size (50), never one request per event
    assert len(agent.queue) == 0


def test_monitor_tracks_only_during_an_active_session(make_agent: Callable[..., Agent], fake_api: FakeApi) -> None:
    probe = FakeProbe(CODE)
    agent, clock = signed_in(make_agent, probe)
    agent.monitor.step()
    assert probe.title_requests == []  # nothing is sampled outside a work session

    agent.start_session()
    agent.monitor.step()
    assert agent.tracker.current_app_name == "Visual Studio Code"
    snap = agent.snapshot()
    assert snap.current_app == "Visual Studio Code"
    assert snap.tracking_label == "Applications (no window titles)"

    agent.heartbeat.beat()
    assert fake_api.heartbeats[-1]["current_app"] == "Visual Studio Code"

    for _ in range(4):
        clock.now += 1
        agent.monitor.step()
    agent.stop_session()
    assert agent.tracker.current_app_name is None
    agent.sync.flush()
    types = fake_api.types()
    assert types.index("activity.segment") < types.index("session.stopped")


def test_server_policy_is_applied_and_persisted(make_agent: Callable[..., Agent], fake_api: FakeApi) -> None:
    fake_api.policy["activity"] = {
        "track_applications": True,
        "capture_window_titles": True,
        "excluded_apps": ["Steam"],
    }
    agent, _ = signed_in(make_agent, FakeProbe(CODE))
    assert agent.tracker.policy.capture_window_titles
    assert agent.tracker.policy.excludes("steam.exe", "Steam")

    fake_api.policy["activity"] = {"track_applications": False, "capture_window_titles": False, "excluded_apps": []}
    agent.heartbeat.beat()
    assert not agent.tracker.policy.track_applications
    assert agent.snapshot().tracking_label == "Work time only"

    agent.start_session()
    agent.heartbeat.beat()
    assert fake_api.heartbeats[-1]["current_app"] is None
