from __future__ import annotations

from datetime import datetime
from typing import Any

from app.schemas.common import APIModel


class ActivityActor(APIModel):
    id: str
    name: str
    employee_id: str | None


class ActivitySubject(APIModel):
    employee_id: str
    name: str


class ActivityItem(APIModel):
    id: str
    action: str
    occurred_at: datetime
    actor: ActivityActor | None
    subject: ActivitySubject | None
    metadata: dict[str, Any]
