"""Activity tracking read models and policy."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import Field, field_validator

from app.schemas.common import APIModel


class ActivityPolicyUpdate(APIModel):
    track_applications: bool | None = None
    capture_window_titles: bool | None = None
    track_websites: bool | None = None
    excluded_apps: list[str] | None = Field(default=None, max_length=200)

    @field_validator("excluded_apps")
    @classmethod
    def _clean(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        unique: dict[str, str] = {}
        for raw in value:
            name = raw.strip() if raw else ""
            if name:
                unique.setdefault(
                    name.lower(), name
                )  # matching is case-insensitive, so de-duplicate that way
        cleaned = sorted(unique.values(), key=str.lower)
        if any(len(v) > 120 for v in cleaned):
            raise ValueError("Application names must be at most 120 characters.")
        return cleaned


class AppUsage(APIModel):
    app_id: str
    app_name: str
    seconds: float
    active_seconds: float
    employees: int


class ApplicationUsageReport(APIModel):
    start: date
    end: date
    timezone: str
    total_seconds: float
    active_seconds: float
    applications: list[AppUsage]


class SegmentOut(APIModel):
    app_id: str
    app_name: str
    window_title: str | None
    started_at: datetime
    ended_at: datetime
    duration_seconds: int
    active_seconds: int
    activity_level: int


class EmployeeActivityDay(APIModel):
    employee_id: str
    day: date
    timezone: str
    tracked_seconds: float
    active_seconds: float
    applications: list[AppUsage]
    segments: list[SegmentOut]
    truncated: bool
