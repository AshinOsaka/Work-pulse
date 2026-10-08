from __future__ import annotations

from typing import Any

from pydantic import Field

from app.models.base import PyObjectId, TenantModel


class AuditLog(TenantModel):
    action: str
    actor_user_id: PyObjectId | None = None
    # The employee the event is about; lets activity feeds be filtered by access scope.
    subject_employee_id: PyObjectId | None = None
    target_type: str | None = None
    target_id: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
