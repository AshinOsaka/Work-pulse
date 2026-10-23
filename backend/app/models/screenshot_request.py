"""Screenshot download requests: a manager asks for one employee's screenshots on one day, packaged as a ZIP.

The images themselves live in encrypted object storage. A request is a small queued job (like a report): a
worker gathers that day's captures for the employee, bundles them into one encrypted ZIP, and the requester
downloads it through a short-lived, signed, requester-bound URL. Requests, packaging, downloads and deletions
are audited, and the ZIP is deleted after the retention period.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from app.models.base import PyObjectId, TenantModel


class ScreenshotRequestStatus(StrEnum):
    QUEUED = "queued"  # "Preparing download…"
    PREPARING = "preparing"  # resolving access and listing captures
    PACKAGING = "packaging"  # fetching and zipping the images
    READY = "ready"
    EMPTY = "empty"  # no screenshots were captured for that person on that day
    FAILED = "failed"
    EXPIRED = "expired"  # the ZIP was removed after the retention period


ACTIVE_REQUEST_STATUSES = (
    ScreenshotRequestStatus.QUEUED,
    ScreenshotRequestStatus.PREPARING,
    ScreenshotRequestStatus.PACKAGING,
)


class ScreenshotRequest(TenantModel):
    requested_by: PyObjectId
    requested_by_name: str
    employee_id: PyObjectId
    employee_name: str
    #: Local date (company time zone), as YYYY-MM-DD.
    day: str
    status: ScreenshotRequestStatus = ScreenshotRequestStatus.QUEUED
    #: 0-100, for the progress bar.
    progress: int = 0
    screenshot_count: int | None = None
    #: Encrypted ZIP in private object storage; never exposed directly.
    object_key: str | None = None
    filename: str | None = None
    content_type: str | None = None
    size_bytes: int | None = None
    #: A message safe to show the requester (never a stack trace).
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    #: When the ZIP is deleted (retention).
    expires_at: datetime | None = None
    downloads: int = 0
