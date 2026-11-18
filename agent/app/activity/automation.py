"""Noticing automated input: a mouse moved by something other than a hand, or input made by software.

Two patterns, from the per-minute input summaries (numbers only — see `input_counter`):

* **Moving without a person** (a USB "mouse jiggler", the mouse on a watch, a fan or a vibrating phone): the mouse
  moves most of every minute, with no click, no scroll and no key press, for `check_after` minutes in a row. People
  move a mouse in bursts and click or type now and then. WorkPulse then asks "Are you still working?" in a small
  window. One click on it (or any click or key press) answers it. If nobody answers within `answer_minutes`, the
  time is reported to the manager as possible automated activity, with the numbers.
* **Software-made input** (a mouse-mover app, or a remote-control tool such as AnyDesk): software input for
  `software_after` minutes in a row with no real keyboard or mouse use at all. That input is already ignored for
  active time; the report says it happened.

Nothing here changes how work time is counted; it only reports what was seen. Every report has a start and an end.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from app.activity.input_counter import InputStats, MinuteStats

logger = logging.getLogger(__name__)

#: A minute counts as "moving without a person" with movement in at least this many of its 60 seconds.
MOVING_SECONDS = 30
#: A minute counts as "software input only" with software input in at least this many seconds.
SOFTWARE_SECONDS = 1


@dataclass(frozen=True)
class AutomationPolicy:
    enabled: bool = True
    check_after: int = 15
    answer_minutes: int = 3
    software_after: int = 10

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> AutomationPolicy:
        if not data:
            return cls()
        return cls(
            enabled=bool(data.get("detect_automation", True)),
            check_after=max(5, min(120, int(data.get("presence_check_minutes", 15)))),
            answer_minutes=3,
            software_after=10,
        )


class CheckState(StrEnum):
    NONE = "none"
    ASKING = "asking"  # the "Are you still working?" window is open
    FLAGGED = "flagged"  # not answered in time: reported, still open until someone is back


def _iso(at: float) -> str:
    return datetime.fromtimestamp(at, UTC).isoformat()


@dataclass
class _Streak:
    kind: str  # "hardware" | "software"
    started_at: float
    last_index: int
    #: Wall-clock start of the streak's latest minute.
    last_started_at: float = 0.0
    minutes: int = 0
    move_minutes: int = 0
    max_span: int = 0
    apps: list[str] = field(default_factory=list)

    def add(self, minute: MinuteStats, app: str | None) -> None:
        self.minutes += 1
        self.last_index = minute.index
        self.last_started_at = minute.started_at
        if minute.move_seconds:
            self.move_minutes += 1
        self.max_span = max(self.max_span, minute.span)
        if app and app not in self.apps and len(self.apps) < 3:
            self.apps.append(app)


def moving_without_person(minute: MinuteStats) -> bool:
    return minute.move_seconds >= MOVING_SECONDS and minute.clicks == 0 and minute.keys == 0


def software_only(minute: MinuteStats) -> bool:
    return (
        minute.injected_seconds >= SOFTWARE_SECONDS
        and minute.move_seconds == 0
        and minute.clicks == 0
        and minute.keys == 0
    )


class AutomationDetector:
    """Fed once per second by the activity monitor; emits `automation.check` events."""

    def __init__(
        self,
        emit: Callable[[dict[str, Any]], None],
        stats: Callable[[], InputStats | None],
        *,
        on_unanswered: Callable[[], None] = lambda: None,
        wall: Callable[[], float] = time.time,
    ) -> None:
        self._emit = emit
        self._stats = stats
        self._on_unanswered = on_unanswered
        self._wall = wall
        self.policy = AutomationPolicy()
        self._hardware: _Streak | None = None
        self._software: _Streak | None = None
        self._software_reported: str | None = None
        self.state = CheckState.NONE
        self._check_id: str | None = None
        self._asked_at = 0.0
        self._asked_action_age = 0.0

    # ------------------------------------------------------------------ for the window
    @property
    def asking(self) -> bool:
        """The "Are you still working?" window should be on screen."""
        return self.state in (CheckState.ASKING, CheckState.FLAGGED)

    def confirm(self) -> None:
        """The person clicked "Yes, I'm working"."""
        self._resolve(self._wall(), answered=True)

    # ------------------------------------------------------------------ the loop
    def set_policy(self, policy: AutomationPolicy) -> None:
        self.policy = policy
        if not policy.enabled:
            self.reset(self._wall())

    def reset(self, at: float) -> None:
        """Work stopped (or detection was switched off): close whatever is open."""
        if self.state != CheckState.NONE:
            self._resolve(at, answered=False)
        self._end_software(at)
        self._hardware = None

    def tick(self, working: bool, app: str | None) -> None:
        stats = self._stats()
        now = self._wall()
        if stats is None or not self.policy.enabled or not working:
            if stats is not None:
                stats.take_minutes()
            self.reset(now)
            return
        current = stats.minute_index()
        for minute in stats.take_minutes():
            self._minute(minute, app)
        # A whole minute with no input at all also ends a streak.
        if self._hardware and current - self._hardware.last_index >= 2:
            self._end_hardware(self._hardware.last_started_at + 60)
        if self._software and current - self._software.last_index >= 2:
            self._end_software(self._software.last_started_at + 60)
        if self.state == CheckState.ASKING:
            # Any real click or key press since the question answers it: a person is there.
            if stats.seconds_since_action() < self._asked_action_age:
                self._resolve(now, answered=True)
            elif now - self._asked_at >= self.policy.answer_minutes * 60:
                self._flag(now)
            else:
                self._asked_action_age = stats.seconds_since_action()
        elif self.state == CheckState.FLAGGED and stats.seconds_since_action() < 2:
            self._resolve(now, answered=False)

    def _minute(self, minute: MinuteStats, app: str | None) -> None:
        if moving_without_person(minute):
            streak = self._hardware
            if streak is None or minute.index != streak.last_index + 1:
                if streak is not None:
                    self._end_hardware(minute.started_at)
                streak = self._hardware = _Streak("hardware", minute.started_at, minute.index)
            streak.add(minute, app)
            if self.state == CheckState.NONE and streak.minutes >= self.policy.check_after:
                self._ask()
        elif self._hardware is not None:
            self._end_hardware(minute.started_at)

        if software_only(minute):
            streak = self._software
            if streak is None or minute.index != streak.last_index + 1:
                self._end_software(minute.started_at)
                streak = self._software = _Streak("software", minute.started_at, minute.index)
            streak.add(minute, app)
            if self._software_reported is None and streak.minutes >= self.policy.software_after:
                self._software_reported = str(uuid.uuid4())
                self._send(self._software_reported, "software", "detected", streak)
        elif self._software is not None:
            self._end_software(minute.started_at)

    # ------------------------------------------------------------------ hardware pattern: ask, then report
    def _ask(self) -> None:
        stats = self._stats()
        self.state = CheckState.ASKING
        self._check_id = str(uuid.uuid4())
        self._asked_at = self._wall()
        self._asked_action_age = stats.seconds_since_action() if stats else 0.0
        logger.info("Automated mouse movement suspected: asking whether someone is working")

    def _flag(self, now: float) -> None:
        self.state = CheckState.FLAGGED
        if self._hardware and self._check_id:
            self._send(self._check_id, "hardware", "unanswered", self._hardware)
        logger.info("Presence check not answered: reported as possible automated activity")
        try:
            self._on_unanswered()
        except Exception:
            logger.warning("Presence check follow-up failed", exc_info=True)

    def _resolve(self, at: float, answered: bool) -> None:
        state, check_id, streak = self.state, self._check_id, self._hardware
        self.state = CheckState.NONE
        self._check_id = None
        if check_id is None:
            return
        streak = streak or _Streak("hardware", self._asked_at, 0)
        if state == CheckState.ASKING:
            self._send(check_id, "hardware", "confirmed" if answered else "ended", streak, ended_at=at)
        elif state == CheckState.FLAGGED:
            self._send(check_id, "hardware", "ended", streak, ended_at=at)
        # Once answered, the streak starts again from zero.
        self._hardware = None

    def _end_hardware(self, at: float) -> None:
        if self.state != CheckState.NONE:
            self._resolve(at, answered=False)
        self._hardware = None

    def _end_software(self, at: float) -> None:
        streak, reported = self._software, self._software_reported
        self._software = None
        self._software_reported = None
        if streak is not None and reported is not None:
            self._send(reported, "software", "ended", streak, ended_at=at)

    def _send(self, check_id: str, kind: str, outcome: str, streak: _Streak, ended_at: float | None = None) -> None:
        now = self._wall()
        event: dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "type": "automation.check",
            "occurred_at": _iso(now),
            "check_id": check_id,
            "kind": kind,
            "outcome": outcome,
            "started_at": _iso(streak.started_at),
            "minutes": streak.minutes,
            "move_minutes": streak.move_minutes,
            "max_span_px": min(streak.max_span, 100_000),
            "apps": streak.apps,
        }
        if kind == "hardware" and self._asked_at:
            event["asked_at"] = _iso(self._asked_at)
        if ended_at is not None:
            event["ended_at"] = _iso(max(ended_at, streak.started_at))
        self._emit(event)
