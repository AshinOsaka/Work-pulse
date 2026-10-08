"""Notification centre: a person's own notifications and delivery preferences."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import NotificationServiceDep
from app.auth.dependencies import CurrentPrincipal
from app.models.notification import NotificationType, Severity
from app.schemas.common import ObjectIdStr
from app.schemas.notifications import (
    MarkRequest,
    MarkResult,
    NotificationPage,
    PreferencesOut,
    PreferencesUpdate,
    UnreadCount,
)

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=NotificationPage)
async def list_notifications(
    principal: CurrentPrincipal,
    service: NotificationServiceDep,
    read: bool | None = None,
    type: NotificationType | None = None,
    severity: Severity | None = None,
    employee_id: Annotated[ObjectIdStr | None, Query()] = None,
    since: datetime | None = None,
    until: datetime | None = None,
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> NotificationPage:
    return await service.list(
        principal,
        read=read,
        type_=type,
        severity=severity,
        employee_id=employee_id,
        since=since,
        until=until,
        page=page,
        page_size=page_size,
    )


@router.get("/unread-count", response_model=UnreadCount)
async def unread_count(principal: CurrentPrincipal, service: NotificationServiceDep) -> UnreadCount:
    return UnreadCount(unread=await service.unread(principal))


@router.post("/mark", response_model=MarkResult, summary="Mark notifications read or unread")
async def mark(
    payload: MarkRequest, principal: CurrentPrincipal, service: NotificationServiceDep
) -> MarkResult:
    return await service.mark(principal, payload)


@router.get("/preferences", response_model=PreferencesOut)
async def preferences(principal: CurrentPrincipal, service: NotificationServiceDep) -> PreferencesOut:
    return await service.preferences(principal)


@router.put("/preferences", response_model=PreferencesOut)
async def update_preferences(
    payload: PreferencesUpdate, principal: CurrentPrincipal, service: NotificationServiceDep
) -> PreferencesOut:
    return await service.update_preferences(principal, payload)
