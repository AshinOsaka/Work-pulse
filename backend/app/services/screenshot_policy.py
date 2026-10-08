"""Effective screenshot policy for one employee, and the working-hours rule.

The agent evaluates the same rules before capturing, and the API re-checks
every upload, so a capture outside the policy is never stored even if a
device misbehaves.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.models.company import Company, ScreenshotPolicy
from app.models.organization import Employee, ScreenshotMode


@dataclass(frozen=True, slots=True)
class EffectiveScreenshotPolicy:
    enabled: bool
    interval_minutes: int
    work_hours_only: bool
    work_start: str
    work_end: str
    work_days: tuple[int, ...]
    retention_days: int
    timezone: str
    #: "workspace" or "employee": where `enabled`/`interval` come from.
    source: str

    @property
    def retention(self) -> timedelta:
        return timedelta(days=self.retention_days)


def effective_policy(company: Company, employee: Employee) -> EffectiveScreenshotPolicy:
    base: ScreenshotPolicy = company.screenshot_policy
    override = employee.screenshot_override
    if override.mode == ScreenshotMode.INHERIT:
        enabled, source = base.enabled, "workspace"
    else:
        enabled, source = override.mode == ScreenshotMode.ENABLED, "employee"
    interval = override.interval_minutes or base.interval_minutes
    return EffectiveScreenshotPolicy(
        enabled=enabled,
        interval_minutes=interval,
        work_hours_only=base.work_hours_only,
        work_start=base.work_start,
        work_end=base.work_end,
        work_days=tuple(base.work_days),
        retention_days=base.retention_days,
        timezone=employee.timezone or company.timezone,
        source=source,
    )


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def _clock(value: str) -> time:
    hours, minutes = value.split(":")
    return time(int(hours), int(minutes))


def in_work_hours(policy: EffectiveScreenshotPolicy, at: datetime) -> bool:
    """Whether `at` falls in working hours, in the employee's timezone. Overnight shifts are supported."""
    local = at.astimezone(_zone(policy.timezone))
    start, end, now = _clock(policy.work_start), _clock(policy.work_end), local.time()
    today = local.isoweekday()
    if start < end:
        return today in policy.work_days and start <= now < end
    yesterday = 7 if today == 1 else today - 1
    return (today in policy.work_days and now >= start) or (yesterday in policy.work_days and now < end)


def capture_allowed(policy: EffectiveScreenshotPolicy, at: datetime) -> bool:
    return policy.enabled and (not policy.work_hours_only or in_work_hours(policy, at))
