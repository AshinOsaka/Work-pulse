"""Notifications: what a person was told, when, and how often (throttled repeats are counted, not repeated)."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from app.models.base import PyObjectId, TenantModel


class NotificationType(StrEnum):
    EMPLOYEE_OFFLINE = "employee_offline"
    DEVICE_OFFLINE = "device_offline"
    EXTENDED_IDLE = "extended_idle"
    SHIFT_STARTED = "shift_started"
    SHIFT_ENDED = "shift_ended"
    TASK_OVERDUE = "task_overdue"
    PROJECT_DEADLINE = "project_deadline"
    LIVE_SESSION_STARTED = "live_session_started"
    LIVE_SESSION_ENDED = "live_session_ended"
    SCREENSHOT_POLICY = "screenshot_policy"


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class Notification(TenantModel):
    recipient_user_id: PyObjectId
    type: NotificationType
    severity: Severity
    title: str
    body: str
    #: The employee the notification is about, if any (for filtering and links).
    employee_id: PyObjectId | None = None
    employee_name: str | None = None
    #: In-app path to open, e.g. "/projects/…?task=…".
    link: str | None = None
    #: Repeats of the same thing within the throttle window are folded into this notification.
    subject_key: str
    count: int = 1
    last_occurred_at: datetime
    read_at: datetime | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class ChannelPrefs(BaseModel):
    in_app: bool = True
    email: bool = False


class NotificationPreferences(TenantModel):
    user_id: PyObjectId
    #: Per notification type; missing types use the defaults from the catalogue.
    types: dict[str, ChannelPrefs] = Field(default_factory=dict)
    #: Repeats about the same subject within this many minutes are combined (and never re-emailed).
    throttle_minutes: int = 30


class AlertEvent(TenantModel):
    """One-time events already handled (e.g. "task X became overdue on 3 Oct"), so they are never sent twice."""

    dedupe_key: str
