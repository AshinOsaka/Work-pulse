"""Activity tracking read models and policy."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import Field, field_validator

from app.schemas.common import APIModel


class AllowedDeviceIn(APIModel):
    key: str = Field(min_length=6, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(default="", max_length=120)
    kind: str = Field(default="", max_length=20)


class ActivityPolicyUpdate(APIModel):
    track_applications: bool | None = None
    capture_window_titles: bool | None = None
    track_websites: bool | None = None
    track_input_metrics: bool | None = None
    managed_monitoring: bool | None = None
    agent_auto_update: bool | None = None
    excluded_apps: list[str] | None = Field(default=None, max_length=200)
    ignore_software_input: bool | None = None
    detect_automation: bool | None = None
    presence_check_minutes: int | None = Field(default=None, ge=5, le=120)
    track_devices: bool | None = None
    track_usb_files: bool | None = None
    device_alert_kinds: list[Literal["storage", "phone", "mouse", "keyboard", "camera", "audio"]] | None = None
    usb_file_alerts: bool | None = None
    allowed_devices: list[AllowedDeviceIn] | None = Field(default=None, max_length=500)

    @field_validator("device_alert_kinds")
    @classmethod
    def _kinds(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else sorted(set(value))

    @field_validator("allowed_devices")
    @classmethod
    def _allowed(cls, value: list[AllowedDeviceIn] | None) -> list[AllowedDeviceIn] | None:
        if value is None:
            return None
        unique: dict[str, AllowedDeviceIn] = {}
        for device in value:
            unique.setdefault(device.key, device)
        return list(unique.values())

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


class WebsiteUsage(APIModel):
    domain: str
    seconds: float
    active_seconds: float
    employees: int


class WebsiteUsageReport(APIModel):
    start: date
    end: date
    timezone: str
    #: False when the workspace does not track websites (nothing is collected); the list is then empty.
    tracking_enabled: bool
    total_seconds: float
    active_seconds: float
    websites: list[WebsiteUsage]


class SegmentOut(APIModel):
    app_id: str
    app_name: str
    window_title: str | None
    started_at: datetime
    ended_at: datetime
    duration_seconds: int
    active_seconds: int
    activity_level: int
    #: Keyboard/mouse event counts for the span (how many, never what); None when input metrics are off.
    key_events: int | None = None
    mouse_events: int | None = None


class EmployeeActivityDay(APIModel):
    employee_id: str
    day: date
    timezone: str
    tracked_seconds: float
    active_seconds: float
    applications: list[AppUsage]
    segments: list[SegmentOut]
    truncated: bool
