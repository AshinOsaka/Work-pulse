"""The employee's effective screenshot policy, as delivered by the server.

Mirrors `backend/app/services/screenshot_policy.py`. The server re-checks
every upload, so these rules can only make the agent capture *less*.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def _clock(value: str) -> time:
    hours, minutes = value.split(":")
    return time(int(hours), int(minutes))


@dataclass(frozen=True)
class ScreenshotPolicy:
    enabled: bool = False
    interval_seconds: int = 600
    work_hours_only: bool = True
    work_start: str = "09:00"
    work_end: str = "18:00"
    work_days: frozenset[int] = field(default_factory=lambda: frozenset({1, 2, 3, 4, 5}))
    timezone: str = "UTC"

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ScreenshotPolicy:
        if not data:
            return cls()  # nothing from the server yet: never capture
        try:
            return cls(
                enabled=bool(data.get("enabled", False)),
                interval_seconds=max(60, int(data.get("interval_seconds", 600))),
                work_hours_only=bool(data.get("work_hours_only", True)),
                work_start=str(data.get("work_start", "09:00")),
                work_end=str(data.get("work_end", "18:00")),
                work_days=frozenset(int(d) for d in data.get("work_days", [1, 2, 3, 4, 5])),
                timezone=str(data.get("timezone", "UTC")),
            )
        except (TypeError, ValueError):
            return cls()

    def _zone(self) -> ZoneInfo:
        try:
            return ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError):
            return ZoneInfo("UTC")

    def in_work_hours(self, at: datetime) -> bool:
        local = at.astimezone(self._zone())
        start, end, now = _clock(self.work_start), _clock(self.work_end), local.time()
        today = local.isoweekday()
        if start < end:
            return today in self.work_days and start <= now < end
        yesterday = 7 if today == 1 else today - 1
        return (today in self.work_days and now >= start) or (yesterday in self.work_days and now < end)

    def in_schedule(self, at: datetime) -> bool:
        return self.enabled and (not self.work_hours_only or self.in_work_hours(at))

    @property
    def interval_label(self) -> str:
        minutes = self.interval_seconds // 60
        return f"every {minutes} min" if minutes != 1 else "every minute"
