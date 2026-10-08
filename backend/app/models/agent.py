"""Data recorded from the desktop agent: work sessions and raw agent events."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models.base import PyObjectId, TenantModel


class PresenceChange(BaseModel):
    at: datetime
    status: Literal["active", "idle"]


class WorkSession(TenantModel):
    """A clocked work session, opened and closed by agent events."""

    employee_id: PyObjectId
    device_id: PyObjectId
    client_session_id: str
    started_at: datetime
    ended_at: datetime | None = None
    end_reason: str | None = None
    active_seconds: int | None = None
    idle_seconds: int | None = None
    #: Every active/idle change within the session, kept with it (raw agent events expire after 90 days).
    presence_changes: list[PresenceChange] = Field(default_factory=list)


class AgentEvent(TenantModel):
    """Raw, validated event as received from an agent (kept for 90 days)."""

    employee_id: PyObjectId
    device_id: PyObjectId
    event_id: str
    type: str
    occurred_at: datetime
    payload: dict[str, Any] = Field(default_factory=dict)
