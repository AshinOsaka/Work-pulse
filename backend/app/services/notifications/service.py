"""The notification centre: a person's own notifications and preferences (nobody sees anyone else's)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.auth.permissions import permissions_for_role
from app.auth.principal import Principal
from app.models.notification import (
    ChannelPrefs,
    Notification,
    NotificationPreferences,
    NotificationType,
    Severity,
)
from app.repositories.notification import NotificationPreferencesRepository, NotificationRepository
from app.schemas.notifications import (
    ChannelPrefsOut,
    FutureChannel,
    MarkRequest,
    MarkResult,
    NotificationOut,
    NotificationPage,
    PreferencesOut,
    PreferencesUpdate,
    TypePreference,
)
from app.schemas.organization import Ref
from app.services.helpers import parse_ref
from app.services.notifications.catalog import CATALOG
from app.services.notifications.notifier import prefs_for

FUTURE_CHANNELS = [
    FutureChannel(key="in_app", label="In-app", available=True),
    FutureChannel(key="email", label="E-mail", available=True),
    FutureChannel(key="slack", label="Slack", available=False),
    FutureChannel(key="teams", label="Microsoft Teams", available=False),
    FutureChannel(key="webhook", label="Webhook", available=False),
]


def out(n: Notification) -> NotificationOut:
    return NotificationOut(
        id=str(n.id),
        type=n.type,
        severity=n.severity,
        title=n.title,
        body=n.body,
        employee=Ref(id=str(n.employee_id), name=n.employee_name or "") if n.employee_id else None,
        link=n.link,
        count=n.count,
        read=n.read_at is not None,
        created_at=n.created_at,
        last_occurred_at=n.last_occurred_at,
    )


class NotificationService:
    def __init__(
        self, notifications: NotificationRepository, prefs: NotificationPreferencesRepository
    ) -> None:
        self._notifications = notifications
        self._prefs = prefs

    @staticmethod
    def _query(
        *,
        read: bool | None = None,
        type_: NotificationType | None = None,
        severity: Severity | None = None,
        employee_id: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> dict[str, Any]:
        query: dict[str, Any] = {}
        if read is True:
            query["read_at"] = {"$ne": None}
        elif read is False:
            query["read_at"] = None
        if type_:
            query["type"] = type_
        if severity:
            query["severity"] = severity
        if employee := parse_ref(employee_id, "employee_id"):
            query["employee_id"] = employee
        if since or until:
            query["last_occurred_at"] = {k: v for k, v in (("$gte", since), ("$lt", until)) if v}
        return query

    async def list(
        self,
        principal: Principal,
        *,
        read: bool | None,
        type_: NotificationType | None,
        severity: Severity | None,
        employee_id: str | None,
        since: datetime | None,
        until: datetime | None,
        page: int,
        page_size: int,
    ) -> NotificationPage:
        query = self._query(
            read=read, type_=type_, severity=severity, employee_id=employee_id, since=since, until=until
        )
        items, total = await self._notifications.page(
            principal.company_id, principal.user_id, query, (page - 1) * page_size, page_size
        )
        return NotificationPage(
            items=[out(n) for n in items],
            total=total,
            unread=await self._notifications.unread_count(principal.company_id, principal.user_id),
            page=page,
            page_size=page_size,
        )

    async def unread(self, principal: Principal) -> int:
        return await self._notifications.unread_count(principal.company_id, principal.user_id)

    async def mark(self, principal: Principal, data: MarkRequest) -> MarkResult:
        if data.all:
            query = self._query(type_=data.type, severity=data.severity)
        else:
            ids = [i for i in (parse_ref(x, "ids") for x in data.ids) if i is not None]
            query = {"_id": {"$in": ids}}
        updated = await self._notifications.mark(principal.company_id, principal.user_id, query, data.read)
        return MarkResult(updated=updated, unread=await self.unread(principal))

    # ------------------------------------------------------------------ preferences
    async def preferences(self, principal: Principal) -> PreferencesOut:
        prefs = await self._prefs.for_user(principal.company_id, principal.user_id)
        perms = permissions_for_role(principal.user.role)
        return PreferencesOut(
            throttle_minutes=prefs.throttle_minutes if prefs else 30,
            email_address=principal.user.email,
            channels=FUTURE_CHANNELS,
            types=[
                TypePreference(
                    type=info.key,
                    label=info.label,
                    description=info.description,
                    audience=info.audience,
                    severity=info.severity,
                    applies=info.permission is None or info.permission in perms,
                    channels=ChannelPrefsOut(**prefs_for(prefs, info.key).model_dump()),
                )
                for info in CATALOG.values()
            ],
        )

    async def update_preferences(self, principal: Principal, data: PreferencesUpdate) -> PreferencesOut:
        current = await self._prefs.for_user(principal.company_id, principal.user_id)
        types = dict(current.types) if current else {}
        for key, channels in data.types.items():
            types[key.value] = ChannelPrefs(in_app=channels.in_app, email=channels.email)
        await self._prefs.save(
            NotificationPreferences(
                company_id=principal.company_id,
                user_id=principal.user_id,
                types=types,
                throttle_minutes=data.throttle_minutes or (current.throttle_minutes if current else 30),
            )
        )
        return await self.preferences(principal)


__all__ = ["NotificationService", "out"]
