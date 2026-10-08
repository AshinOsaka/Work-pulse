"""Screenshot monitoring: policy, gallery and transparency schemas."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.models.organization import ScreenshotMode
from app.schemas.common import APIModel
from app.schemas.organization import EmployeeRef

_CLOCK = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

INTERVAL_MIN, INTERVAL_MAX = 1, 120
RETENTION_MIN, RETENTION_MAX = 1, 365


def _check_clock(value: str | None) -> str | None:
    if value is not None and not _CLOCK.fullmatch(value):
        raise ValueError("Use 24-hour HH:MM.")
    return value


class ScreenshotPolicyOut(APIModel):
    enabled: bool
    interval_minutes: int
    work_hours_only: bool
    work_start: str
    work_end: str
    work_days: list[int]
    retention_days: int


class ScreenshotPolicyUpdate(APIModel):
    enabled: bool | None = None
    interval_minutes: int | None = Field(default=None, ge=INTERVAL_MIN, le=INTERVAL_MAX)
    work_hours_only: bool | None = None
    work_start: str | None = None
    work_end: str | None = None
    work_days: list[int] | None = Field(default=None, max_length=7)
    retention_days: int | None = Field(default=None, ge=RETENTION_MIN, le=RETENTION_MAX)

    _start = field_validator("work_start")(_check_clock)
    _end = field_validator("work_end")(_check_clock)

    @field_validator("work_days")
    @classmethod
    def _days(cls, value: list[int] | None) -> list[int] | None:
        if value is None:
            return None
        if any(d < 1 or d > 7 for d in value):
            raise ValueError("Days are ISO weekdays: 1 (Monday) to 7 (Sunday).")
        if not value:
            raise ValueError("Choose at least one working day.")
        return sorted(set(value))


class EmployeeScreenshotSettingsUpdate(APIModel):
    mode: ScreenshotMode
    interval_minutes: int | None = Field(default=None, ge=INTERVAL_MIN, le=INTERVAL_MAX)


class EffectiveScreenshotPolicyOut(APIModel):
    enabled: bool
    interval_minutes: int
    work_hours_only: bool
    work_start: str
    work_end: str
    work_days: list[int]
    retention_days: int
    timezone: str
    source: Literal["workspace", "employee"]


class EmployeeScreenshotSettings(APIModel):
    employee_id: str
    mode: ScreenshotMode
    interval_minutes: int | None
    effective: EffectiveScreenshotPolicyOut


class ScreenshotItem(APIModel):
    id: str
    employee: EmployeeRef
    captured_at: datetime
    width: int
    height: int
    thumbnail_url: str


class ScreenshotPage(APIModel):
    items: list[ScreenshotItem]
    #: Pass as `before` to load the next (older) page; null when there is nothing more.
    next_before: datetime | None
    day: date
    timezone: str


class ScreenshotDetail(ScreenshotItem):
    image_url: str
    device_name: str | None
    #: Foreground application recorded by activity tracking at capture time, when available.
    application: str | None
    size_bytes: int
    expires_at: datetime
    url_expires_in: int


class TimelineBucket(APIModel):
    hour: int
    count: int


class TimelineCapture(APIModel):
    id: str
    captured_at: datetime


class ScreenshotTimeline(APIModel):
    day: date
    timezone: str
    total: int
    buckets: list[TimelineBucket]
    #: Individual capture times, only when one employee is selected.
    captures: list[TimelineCapture] | None


class ScreenshotUploadResult(APIModel):
    id: str
    duplicate: bool


class MonitoringScreenshots(APIModel):
    enabled: bool
    interval_minutes: int
    work_hours_only: bool
    work_start: str
    work_end: str
    work_days: list[int]
    timezone: str
    retention_days: int
    #: Allowed right now by the schedule (a work session must also be running).
    in_schedule_now: bool
    last_captured_at: datetime | None


class MonitoringStatus(APIModel):
    """What is recorded about the signed-in person: shown to them for transparency."""

    has_employee_record: bool
    agent_connected: bool
    session_active: bool
    track_applications: bool
    capture_window_titles: bool
    screenshots: MonitoringScreenshots | None
    #: True while something is actively being recorded right now.
    monitoring_active: bool
    live_view_enabled: bool = False
    #: Name of the person watching this screen live right now, if anyone.
    live_viewer: str | None = None


class AgentScreenshotPolicy(APIModel):
    enabled: bool
    interval_seconds: int
    work_hours_only: bool
    work_start: str
    work_end: str
    work_days: list[int]
    timezone: str


class ScreenshotPolicyValidated(ScreenshotPolicyOut):
    @model_validator(mode="after")
    def _hours(self) -> ScreenshotPolicyValidated:
        if self.work_hours_only and self.work_start == self.work_end:
            raise ValueError("Working hours must start and end at different times.")
        return self
