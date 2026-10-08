from __future__ import annotations

from collections.abc import Sequence

from bson import ObjectId
from pymongo import ASCENDING, DESCENDING, IndexModel

from app.models.audit_log import AuditLog
from app.repositories.base import TenantRepository


class AuditLogRepository(TenantRepository[AuditLog]):
    collection_name = "audit_logs"
    model = AuditLog
    indexes = (
        IndexModel([("company_id", ASCENDING), ("created_at", DESCENDING)], name="company_created_at"),
        IndexModel([("company_id", ASCENDING), ("action", ASCENDING)], name="company_action"),
        IndexModel([("actor_user_id", ASCENDING)], name="actor_user_id"),
        IndexModel(
            [("company_id", ASCENDING), ("subject_employee_id", ASCENDING), ("created_at", DESCENDING)],
            name="company_subject_created_at",
        ),
    )

    async def recent(
        self,
        company_id: ObjectId,
        actions: Sequence[str],
        *,
        subject_employee_ids: Sequence[ObjectId] | None = None,
        limit: int = 20,
    ) -> list[AuditLog]:
        """Newest events of the given kinds; optionally only those about specific employees."""
        query: dict[str, object] = {"action": {"$in": list(actions)}}
        if subject_employee_ids is not None:
            query["subject_employee_id"] = {"$in": list(subject_employee_ids)}
        return await self.find_many(
            company_id, query, sort=[("created_at", DESCENDING), ("_id", DESCENDING)], limit=limit
        )
