"""Application activity tracking: turns foreground samples into time segments.

Sampled about once per second while a work session is active. Consecutive
samples with the same application (and permitted window title) extend one
segment; a segment closes when the application/title changes, the employee
goes idle, the session ends, or it reaches MAX_SEGMENT_SECONDS. Each closed
segment becomes ONE queued event, and the sync worker sends queued events in
batches, so the network sees a handful of requests per minute at most.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.activity import events
from app.activity.foreground import ForegroundApp, ForegroundProbe
from app.activity.idle import IdleDetector
from app.activity.privacy import NOT_AN_APPLICATION, ActivityPolicy, permitted_title

#: Input within this many seconds counts the second as "active" (only the timestamp of input is read).
ACTIVE_INPUT_WINDOW_SECONDS = 15
#: Long segments are split so data flows steadily and a crash can lose at most this much.
MAX_SEGMENT_SECONDS = 15 * 60
#: Shorter segments (alt-tab flicker) are dropped.
MIN_SEGMENT_SECONDS = 2
#: A gap between samples larger than this (sleep, hang) is never counted as usage; nor is a backwards clock jump.
MAX_SAMPLE_GAP_SECONDS = 5


@dataclass
class _Segment:
    session_id: str
    app: ForegroundApp
    title: str | None
    domain: str | None
    started_at: float
    last_sample: float
    active_seconds: float = 0.0


class ActivityTracker:
    def __init__(
        self,
        emit: Callable[[dict[str, Any]], None],
        probe: ForegroundProbe,
        idle: IdleDetector,
        *,
        policy: ActivityPolicy | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._emit = emit
        self._probe = probe
        self._idle = idle
        self._clock = clock
        self._policy = policy or ActivityPolicy()
        self._segment: _Segment | None = None
        self._lock = threading.Lock()
        self.segments_emitted = 0

    @property
    def policy(self) -> ActivityPolicy:
        return self._policy

    def set_policy(self, policy: ActivityPolicy) -> None:
        with self._lock:
            changed = policy != self._policy
            self._policy = policy
        if changed:
            self.close()  # never mix data recorded under different policies in one segment

    @property
    def current_app_name(self) -> str | None:
        segment = self._segment
        return segment.app.app_name if segment and self._policy.track_applications else None

    def sample(self, session_id: str, working: bool) -> None:
        """Record one foreground sample. `working` is False while idle or not in a session."""
        with self._lock:
            now = self._clock()
            segment = self._segment
            if segment:
                gap = now - segment.last_sample
                if gap > MAX_SAMPLE_GAP_SECONDS or gap < 0:  # sleep/hang, or the clock was set back
                    self._close_locked(at=segment.last_sample)
                    segment = None
                else:
                    if self._idle.idle_seconds() < ACTIVE_INPUT_WINDOW_SECONDS:
                        segment.active_seconds += gap
                    segment.last_sample = now

            if not working or not self._policy.track_applications:
                self._close_locked(at=now)
                return
            app = self._probe.current(
                include_title=self._policy.capture_window_titles, include_domain=self._policy.track_websites
            )
            if app is None or app.app_id in NOT_AN_APPLICATION or self._policy.excludes(app.app_id, app.app_name):
                self._close_locked(at=now)
                return
            title = permitted_title(self._policy, app.app_id, app.title)
            domain = app.domain if self._policy.track_websites else None
            if domain and self._policy.excludes_domain(domain):
                self._close_locked(at=now)
                return

            if segment and (
                segment.app.app_id != app.app_id
                or segment.title != title
                or segment.domain != domain
                or segment.session_id != session_id
            ):
                self._close_locked(at=now)
                segment = None
            if segment and now - segment.started_at >= MAX_SEGMENT_SECONDS:
                self._close_locked(at=now)
                segment = None
            if segment is None:
                self._segment = _Segment(session_id, app, title, domain, started_at=now, last_sample=now)

    def close(self, at: float | None = None) -> None:
        with self._lock:
            self._close_locked(at=self._clock() if at is None else at)

    def _close_locked(self, at: float) -> None:
        segment, self._segment = self._segment, None
        if segment is None:
            return
        end = min(max(at, segment.started_at), segment.last_sample + MAX_SAMPLE_GAP_SECONDS)
        duration = end - segment.started_at
        if duration < MIN_SEGMENT_SECONDS:
            return
        active = min(segment.active_seconds, duration)
        self._emit(
            events.activity_segment(
                session_id=segment.session_id,
                app_id=segment.app.app_id,
                app_name=segment.app.app_name,
                window_title=segment.title,
                domain=segment.domain,
                started_at=segment.started_at,
                ended_at=end,
                active_seconds=active,
                activity_level=round(100 * active / duration) if duration else 0,
            )
        )
        self.segments_emitted += 1
