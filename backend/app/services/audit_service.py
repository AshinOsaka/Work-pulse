from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from bson import ObjectId

from app.models.audit_log import AuditLog
from app.repositories.audit_log import AuditLogRepository
from app.services.context import RequestMeta

logger = logging.getLogger(__name__)


class AuditService:
    def __init__(self, repository: AuditLogRepository) -> None:
        self._repository = repository

    async def record(
        self,
        action: str,
        *,
        company_id: ObjectId,
        actor_user_id: ObjectId | None = None,
        target_type: str | None = None,
        target_id: str | None = None,
        subject_employee_id: ObjectId | None = None,
        meta: RequestMeta | None = None,
        metadata: dict[str, Any] | None = None,
        occurred_at: datetime | None = None,
    ) -> None:
        """Persist an audit event. Failures are logged, never raised to the caller."""
        entry = AuditLog(
            company_id=company_id,
            action=action,
            actor_user_id=actor_user_id,
            target_type=target_type,
            target_id=target_id,
            subject_employee_id=subject_employee_id,
            ip_address=meta.ip_address if meta else None,
            user_agent=meta.user_agent if meta else None,
            metadata=metadata or {},
        )
        if occurred_at is not None:
            # Events reported later (e.g. queued offline by the agent) keep their real time.
            entry.created_at = occurred_at
        try:
            await self._repository.create(company_id, entry)
        except Exception:
            logger.exception("Failed to write audit event %s", action)
