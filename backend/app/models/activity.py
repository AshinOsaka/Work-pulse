"""Application activity reported by the desktop agent (metadata only)."""

from __future__ import annotations

from datetime import datetime

from app.models.base import PyObjectId, TenantModel


class ActivitySegment(TenantModel):
    """A continuous span of time with one application (and optionally window) in the foreground."""

    employee_id: PyObjectId
    device_id: PyObjectId
    event_id: str
    session_id: str
    app_id: str
    app_name: str
    #: Only stored when the company policy allows it, never for sensitive apps, always redacted.
    window_title: str | None = None
    #: Host name of the active browser tab, only when the policy tracks websites (never paths or queries).
    domain: str | None = None
    started_at: datetime
    ended_at: datetime
    duration_seconds: int
    active_seconds: int
    #: Share of the segment with recent keyboard/mouse input, 0-100 (no input content is captured).
    activity_level: int
