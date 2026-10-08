"""Work sessions: start/stop, idle accounting, crash recovery."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from app.activity.session import RESUME_GAP_SECONDS, WorkSessionManager, WorkStatus
from app.security.crypto import Cipher, load_master_key
from app.security.protector import KeyFileProtector
from app.storage.secure_store import SecureStore
from tests.conftest import FakeIdle


class Clock:
    def __init__(self) -> None:
        self.now = 1_700_000_000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def store(tmp_path: Path) -> SecureStore:
    return SecureStore(tmp_path, Cipher(load_master_key(tmp_path / "k", KeyFileProtector(tmp_path / ".k"))))


def manager(store: SecureStore, clock: Clock, idle: FakeIdle, emitted: list[dict[str, Any]]) -> WorkSessionManager:
    return WorkSessionManager(emitted.append, store, idle, idle_threshold=300, clock=clock)


def run(sessions: WorkSessionManager, clock: Clock, seconds: int) -> None:
    for _ in range(seconds):
        clock.now += 1
        sessions.tick()


def test_start_stop_and_durations(store: SecureStore) -> None:
    clock, idle, emitted = Clock(), FakeIdle(), []
    sessions = manager(store, clock, idle, emitted)
    assert sessions.status == WorkStatus.NOT_WORKING
    assert sessions.start() and not sessions.start()
    run(sessions, clock, 600)
    assert sessions.status == WorkStatus.ACTIVE and sessions.duration() == 600
    assert sessions.stop()

    started, stopped = emitted
    assert started["type"] == "session.started"
    assert stopped["type"] == "session.stopped" and stopped["reason"] == "user"
    assert stopped["session_id"] == started["session_id"]
    assert stopped["active_seconds"] == 600 and stopped["idle_seconds"] == 0
    assert sessions.status == WorkStatus.NOT_WORKING and not sessions.stop()


def test_idle_is_booked_from_when_input_stopped(store: SecureStore) -> None:
    clock, idle, emitted = Clock(), FakeIdle(), []
    sessions = manager(store, clock, idle, emitted)
    sessions.start()
    start = clock.now
    for _ in range(900):  # input stops after 600s; idle is detected 300s later
        clock.now += 1
        idle.seconds = max(0.0, clock.now - (start + 600))
        sessions.tick()
    assert sessions.status == WorkStatus.IDLE
    idle_event = next(e for e in emitted if e["type"] == "presence.changed")
    assert idle_event["status"] == "idle"
    active, idle_total = sessions.totals()
    assert active == pytest.approx(600, abs=2) and idle_total == pytest.approx(300, abs=2)

    idle.seconds = 0  # input resumes
    run(sessions, clock, 10)
    assert sessions.status == WorkStatus.ACTIVE
    assert [e["status"] for e in emitted if e["type"] == "presence.changed"] == ["idle", "active"]


def test_resume_after_restart_and_recovery_of_stale_session(store: SecureStore) -> None:
    clock, idle, emitted = Clock(), FakeIdle(), []
    first = manager(store, clock, idle, emitted)
    first.start()
    run(first, clock, 60)  # forces at least one checkpoint
    session_id = first.session_id

    clock.now += 120  # quick restart: the session continues
    second = manager(store, clock, idle, emitted)
    second.resume()
    assert second.running and second.session_id == session_id

    last_tick = clock.now
    clock.now += RESUME_GAP_SECONDS + 60  # long outage (sleep / power loss)
    third = manager(store, clock, idle, emitted)
    third.resume()
    assert not third.running
    stopped = emitted[-1]
    assert stopped["type"] == "session.stopped" and stopped["reason"] == "recovered"
    assert stopped["occurred_at"] <= _iso(last_tick)  # never invents time after the last observation


def test_long_gap_while_running_closes_session(store: SecureStore) -> None:
    clock, idle, emitted = Clock(), FakeIdle(), []
    sessions = manager(store, clock, idle, emitted)
    sessions.start()
    run(sessions, clock, 30)
    clock.now += RESUME_GAP_SECONDS + 5  # laptop lid closed
    sessions.tick()
    assert not sessions.running and emitted[-1]["reason"] == "recovered"


def _iso(ts: float) -> str:
    from datetime import UTC, datetime

    return datetime.fromtimestamp(ts, UTC).isoformat()
