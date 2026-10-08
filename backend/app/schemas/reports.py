"""Reports API."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import Field

from app.models.report import ReportFormat, ReportPeriod, ReportStatus, ReportType
from app.schemas.common import APIModel

ObjectIdPattern = r"^[0-9a-f]{24}$"


class ReportTypeOut(APIModel):
    key: ReportType
    label: str
    description: str
    #: Filters that apply to this type: employee, department, team, role, work_profile, project.
    filters: list[str]
    #: Whether the requester has the permissions this type needs.
    allowed: bool
    requires: str | None


class ReportFiltersIn(APIModel):
    employee_ids: list[str] = Field(default_factory=list, max_length=500)
    department_id: str | None = Field(default=None, pattern=ObjectIdPattern)
    team_id: str | None = Field(default=None, pattern=ObjectIdPattern)
    role: str | None = Field(default=None, pattern=r"^(EMPLOYEE|TEAM_LEAD|MANAGER|COMPANY_ADMIN)$")
    work_profile_id: str | None = Field(default=None, pattern=ObjectIdPattern)
    project_id: str | None = Field(default=None, pattern=ObjectIdPattern)


class ReportRequest(APIModel):
    report_type: ReportType
    format: ReportFormat = ReportFormat.CSV
    period: ReportPeriod = ReportPeriod.CUSTOM
    start: date
    end: date
    filters: ReportFiltersIn = Field(default_factory=ReportFiltersIn)


class ReportPreview(APIModel):
    title: str
    columns: list[dict[str, str]]
    #: Display-formatted values for the first rows.
    rows: list[dict[str, Any]]
    total_rows: int
    people: int
    notes: list[str]


class ReportJobOut(APIModel):
    id: str
    report_type: ReportType
    label: str
    format: ReportFormat
    period: ReportPeriod
    start: date
    end: date
    status: ReportStatus
    progress: int
    row_count: int | None
    filename: str | None
    size_bytes: int | None
    error: str | None
    notes: list[str]
    created_at: datetime
    finished_at: datetime | None
    expires_at: datetime | None
    #: Short-lived, bound to the requester; only when ready.
    download_url: str | None
