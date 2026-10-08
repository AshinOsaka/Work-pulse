from __future__ import annotations

from datetime import datetime
from typing import Literal

from app.models.organization import DeviceOs
from app.schemas.common import APIModel
from app.schemas.organization import EmployeeRef, Ref

PresenceStatus = Literal["active", "idle", "offline"]


class PresenceDevice(APIModel):
    id: str
    name: str
    os: DeviceOs
    agent_version: str | None
    last_seen_at: datetime | None


class EmployeePresence(APIModel):
    employee: EmployeeRef
    team: Ref | None
    status: PresenceStatus
    #: Agent connected (recent heartbeat), whether or not a work session is running.
    connected: bool
    #: When the current status began.
    since: datetime | None
    session_started_at: datetime | None
    device: PresenceDevice | None
    #: Foreground application while working (when application tracking is enabled).
    current_app: str | None = None


class PresenceCounts(APIModel):
    online: int
    active: int
    idle: int
    offline: int


class PresenceOverview(APIModel):
    employees: list[EmployeePresence]
    counts: PresenceCounts
    as_of: datetime


class WorkHoursSummary(APIModel):
    period: Literal["daily", "weekly", "monthly"]
    timezone: str
    current_hours: float
    previous_hours: float
    #: Hours per bucket, oldest first; the last entry is the current period.
    history: list[float]
