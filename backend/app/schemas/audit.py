"""Audit trail (read-only)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.schemas.common import APIModel, Page


class AuditPerson(APIModel):
    id: str
    name: str
    email: str | None = None


class AuditEntryOut(APIModel):
    id: str
    at: datetime
    action: str
    #: Plain-language description, e.g. "Viewed a screenshot".
    label: str
    category: str | None
    actor: AuditPerson | None
    #: The employee the event was about, if any.
    subject: AuditPerson | None
    target_type: str | None
    target_id: str | None
    ip_address: str | None
    device: str | None
    details: dict[str, Any]


class AuditCategoryOut(APIModel):
    key: str
    label: str


AuditPage = Page[AuditEntryOut]
