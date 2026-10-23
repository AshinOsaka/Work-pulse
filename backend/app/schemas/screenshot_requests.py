"""Request/response shapes for screenshot download requests."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import Field

from app.models.screenshot_request import ScreenshotRequestStatus
from app.schemas.common import APIModel, ObjectIdStr


class ScreenshotRequestCreate(APIModel):
    employee_id: ObjectIdStr
    #: Local date (company time zone) to package.
    day: date


class ScreenshotRequestOut(APIModel):
    id: str
    employee_id: str
    employee_name: str
    requested_by_name: str
    day: date
    status: ScreenshotRequestStatus
    progress: int = Field(ge=0, le=100)
    screenshot_count: int | None
    filename: str | None
    size_bytes: int | None
    error: str | None
    created_at: datetime
    finished_at: datetime | None
    expires_at: datetime | None
    #: Short-lived, requester-bound download link; present only while the ZIP is ready.
    download_url: str | None
