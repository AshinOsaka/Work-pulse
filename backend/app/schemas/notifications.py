"""Notification centre API."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.models.notification import NotificationType, Severity
from app.schemas.common import APIModel
from app.schemas.organization import Ref


class NotificationOut(APIModel):
    id: str
    type: NotificationType
    severity: Severity
    title: str
    body: str
    employee: Ref | None
    link: str | None
    #: How many times this happened within the throttle window (shown as "x3").
    count: int
    read: bool
    created_at: datetime
    last_occurred_at: datetime


class NotificationPage(APIModel):
    items: list[NotificationOut]
    total: int
    unread: int
    page: int
    page_size: int


class UnreadCount(APIModel):
    unread: int


class MarkRequest(APIModel):
    ids: list[str] = Field(default_factory=list, max_length=500)
    #: Instead of ids: everything matching the list filters (all = no filter).
    all: bool = False
    type: NotificationType | None = None
    severity: Severity | None = None
    read: bool = True


class MarkResult(APIModel):
    updated: int
    unread: int


class ChannelPrefsOut(APIModel):
    in_app: bool
    email: bool


class TypePreference(APIModel):
    type: NotificationType
    label: str
    description: str
    audience: str
    severity: Severity
    #: False when the user's role never receives this type.
    applies: bool
    channels: ChannelPrefsOut


class FutureChannel(APIModel):
    key: str
    label: str
    available: bool


class PreferencesOut(APIModel):
    throttle_minutes: int
    types: list[TypePreference]
    email_address: str
    channels: list[FutureChannel]


class PreferencesUpdate(APIModel):
    throttle_minutes: int | None = Field(default=None, ge=5, le=1440)
    types: dict[NotificationType, ChannelPrefsOut] = Field(default_factory=dict)
