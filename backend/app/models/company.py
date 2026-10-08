from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from app.models.base import MongoModel


class CompanyStatus(StrEnum):
    TRIAL = "trial"
    ACTIVE = "active"
    SUSPENDED = "suspended"


class CompanyPlan(StrEnum):
    TRIAL = "trial"
    STARTER = "starter"
    BUSINESS = "business"
    ENTERPRISE = "enterprise"


class ActivityPolicy(BaseModel):
    """What the desktop agent may record for this workspace (privacy-first defaults)."""

    track_applications: bool = True
    capture_window_titles: bool = False
    #: Record the domain of the active browser tab (never full addresses). Off by default.
    track_websites: bool = False
    excluded_apps: list[str] = Field(default_factory=list)


class ScreenshotPolicy(BaseModel):
    """Screenshot monitoring for this workspace. Off until an administrator turns it on."""

    enabled: bool = False
    interval_minutes: int = 10
    #: Capture only inside the working hours below, in each employee's own timezone.
    work_hours_only: bool = True
    work_start: str = "09:00"
    work_end: str = "18:00"
    #: ISO weekdays, Monday = 1.
    work_days: list[int] = Field(default_factory=lambda: [1, 2, 3, 4, 5])
    retention_days: int = 30


class LiveViewPolicy(BaseModel):
    """On-demand live screen viewing. Off until an administrator turns it on."""

    enabled: bool = False
    #: Streams end automatically after this long; the viewer can start a new one.
    max_session_minutes: int = 30


class Company(MongoModel):
    name: str
    slug: str
    status: CompanyStatus = CompanyStatus.TRIAL
    plan: CompanyPlan = CompanyPlan.TRIAL
    timezone: str = "UTC"
    industry: str | None = None
    size: str | None = None
    trial_ends_at: datetime | None = None
    activity_policy: ActivityPolicy = Field(default_factory=ActivityPolicy)
    screenshot_policy: ScreenshotPolicy = Field(default_factory=ScreenshotPolicy)
    live_policy: LiveViewPolicy = Field(default_factory=LiveViewPolicy)
