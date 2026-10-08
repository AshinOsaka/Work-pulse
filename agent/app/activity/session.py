"""Work sessions: explicit start/stop by the employee, with active/idle accounting.

The session state is checkpointed (encrypted) so a crash or reboot never loses
or invents work time: on restart a recent session resumes, and a stale one is
closed at the last moment the agent knew the employee was working.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any

from app.activity import events
from app.activity.idle import IdleDetector
from app.storage.secure_store import SecureStore

logger = logging.getLogger(__name__)

_CHECKPOINT = "session"
#: A gap longer than this (sleep, crash, power loss) ends the session at the last known tick.
RESUME_GAP_SECONDS = 10 * 60
CHECKPOINT_EVERY_SECONDS = 30


class WorkStatus(StrEnum):
    NOT_WORKING = "not_working"
    ACTIVE = "active"
    IDLE = "idle"


STATUS_LABELS = {
    WorkStatus.NOT_WORKING: "Not working",
    WorkStatus.ACTIVE: "Working",
    WorkStatus.IDLE: "Idle",
}


@dataclass
class SessionState:
    session_id: str
    started_at: float
    last_tick: float
    presence: str = "active"
    presence_since: float = 0.0
    active_seconds: float = 0.0
    idle_seconds: float = 0.0


class WorkSessionManager:
    def __init__(
        self,
        emit: Callable[[dict[str, Any]], None],
        store: SecureStore,
        idle_detector: IdleDetector,
        idle_threshold: float,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._emit = emit
        self._store = store
        self._idle = idle_detector
        self._idle_threshold = idle_threshold
        self._clock = clock
        self._lock = threading.RLock()
        self._state: SessionState | None = None
        self._last_checkpoint = 0.0

    # ------------------------------------------------------------------ queries
    @property
    def running(self) -> bool:
        return self._state is not None

    @property
    def session_id(self) -> str | None:
        return self._state.session_id if self._state else None

    @property
    def status(self) -> WorkStatus:
        state = self._state
        if state is None:
            return WorkStatus.NOT_WORKING
        return WorkStatus.IDLE if state.presence == "idle" else WorkStatus.ACTIVE

    def duration(self) -> float:
        state = self._state
        return max(0.0, self._clock() - state.started_at) if state else 0.0

    def totals(self) -> tuple[float, float]:
        state = self._state
        return (state.active_seconds, state.idle_seconds) if state else (0.0, 0.0)

    def set_idle_threshold(self, seconds: float) -> None:
        self._idle_threshold = seconds

    # ------------------------------------------------------------------ commands
    def start(self) -> bool:
        with self._lock:
            if self._state is not None:
                return False
            now = self._clock()
            self._state = SessionState(session_id=str(uuid.uuid4()), started_at=now, last_tick=now, presence_since=now)
            self._emit(events.session_started(self._state.session_id, now))
            self._checkpoint(force=True)
            logger.info("Work session started")
            return True

    def stop(self, reason: str = "user", at: float | None = None) -> bool:
        with self._lock:
            state = self._state
            if state is None:
                return False
            if at is None:
                self._advance(self._clock())
                at = self._clock()
            self._emit(events.session_stopped(state.session_id, at, reason, state.active_seconds, state.idle_seconds))
            self._state = None
            self._store.delete(_CHECKPOINT)
            logger.info("Work session stopped (%s)", reason)
            return True

    def discard(self) -> None:
        """Forget the local session without reporting it (device revoked)."""
        with self._lock:
            self._state = None
            self._store.delete(_CHECKPOINT)

    def resume(self) -> None:
        """Restore a checkpointed session after a restart."""
        with self._lock:
            stored = self._store.load(_CHECKPOINT)
            if not stored:
                return
            state = SessionState(**stored)
            if self._clock() - state.last_tick > RESUME_GAP_SECONDS:
                self._state = state
                self.stop(reason="recovered", at=state.last_tick)
                logger.info("Closed a session interrupted by sleep, crash or shutdown")
            else:
                self._state = state
                logger.info("Resumed work session %s", state.session_id)

    def tick(self) -> None:
        """Called about once per second by the activity monitor."""
        with self._lock:
            if self._state is None:
                return
            now = self._clock()
            if now - self._state.last_tick > RESUME_GAP_SECONDS:
                # The machine slept or hung: end the session when activity was last observed.
                self.stop(reason="recovered", at=self._state.last_tick)
                return
            self._advance(now)
            self._checkpoint()

    # ------------------------------------------------------------------ internals
    def _advance(self, now: float) -> None:
        state = self._state
        assert state is not None
        delta = max(0.0, now - state.last_tick)
        idle_for = self._idle.idle_seconds()
        presence = "idle" if idle_for >= self._idle_threshold else "active"
        if presence != state.presence:
            if presence == "idle":
                # Idle began when input stopped, not when we noticed: re-book that span as idle.
                changed_at = max(now - idle_for, state.presence_since, state.started_at)
                moved = max(0.0, min(state.last_tick - changed_at, state.active_seconds))
                state.active_seconds -= moved
                state.idle_seconds += moved
            else:
                changed_at = now
            self._emit(events.presence_changed(state.session_id, presence, changed_at))
            state.presence = presence
            state.presence_since = changed_at
        if state.presence == "idle":
            state.idle_seconds += delta
        else:
            state.active_seconds += delta
        state.last_tick = now

    def _checkpoint(self, force: bool = False) -> None:
        now = self._clock()
        if self._state and (force or now - self._last_checkpoint >= CHECKPOINT_EVERY_SECONDS):
            self._store.save(_CHECKPOINT, asdict(self._state))
            self._last_checkpoint = now
