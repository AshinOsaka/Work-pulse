"""Generated reports: a request, its progress, and the encrypted file it produced."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from app.models.base import PyObjectId, TenantModel


class ReportType(StrEnum):
    ATTENDANCE = "attendance"
    WORK_HOURS = "work_hours"
    ACTIVITY = "activity"
    APPLICATIONS = "applications"
    WEBSITES = "websites"
    SCREENSHOTS = "screenshots"
    PROJECTS = "projects"
    TASKS = "tasks"
    PRODUCTIVITY = "productivity"
    LIVE_SESSIONS = "live_sessions"


class ReportFormat(StrEnum):
    CSV = "csv"
    XLSX = "xlsx"
    PDF = "pdf"


class ReportPeriod(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    CUSTOM = "custom"


class ReportStatus(StrEnum):
    QUEUED = "queued"  # "Preparing report…" in the UI
    PREPARING = "preparing"  # resolving access and collecting data
    GENERATING = "generating"  # writing the file
    READY = "ready"
    FAILED = "failed"
    EXPIRED = "expired"  # the file was removed after the retention period


ACTIVE_REPORT_STATUSES = (ReportStatus.QUEUED, ReportStatus.PREPARING, ReportStatus.GENERATING)


class ReportFilters(BaseModel):
    employee_ids: list[PyObjectId] = Field(default_factory=list)
    department_id: PyObjectId | None = None
    team_id: PyObjectId | None = None
    #: Permission role of the employee's account (EMPLOYEE, TEAM_LEAD, …).
    role: str | None = None
    #: Job role (work profile).
    work_profile_id: PyObjectId | None = None
    project_id: PyObjectId | None = None


class ReportJob(TenantModel):
    requested_by: PyObjectId
    requested_by_name: str
    report_type: ReportType
    format: ReportFormat
    period: ReportPeriod
    #: Local dates (company time zone), inclusive, as YYYY-MM-DD.
    start: str
    end: str
    filters: ReportFilters = Field(default_factory=ReportFilters)
    status: ReportStatus = ReportStatus.QUEUED
    #: 0-100, for the progress bar.
    progress: int = 0
    row_count: int | None = None
    #: Encrypted file in private object storage; never exposed directly.
    object_key: str | None = None
    filename: str | None = None
    content_type: str | None = None
    size_bytes: int | None = None
    #: A message safe to show the requester (never a stack trace).
    error: str | None = None
    notes: list[str] = Field(default_factory=list)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    #: When the file is deleted (retention).
    expires_at: datetime | None = None
    downloads: int = 0
