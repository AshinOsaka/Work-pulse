"""Live session records."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from bson import ObjectId
from pymongo import ASCENDING, DESCENDING, IndexModel

from app.models.live import ACTIVE_STATUSES, LiveEventType, LiveSession, LiveSessionEvent, LiveStatus
from app.repositories.base import TenantRepository
from app.utils.time import utcnow


class LiveSessionRepository(TenantRepository[LiveSession]):
    collection_name = "live_sessions"
    model = LiveSession
    indexes = (
        IndexModel(
            [("company_id", ASCENDING), ("employee_id", ASCENDING), ("created_at", DESCENDING)],
            name="company_employee_created",
        ),
        IndexModel([("company_id", ASCENDING), ("status", ASCENDING)], name="company_status"),
        IndexModel([("status", ASCENDING)], name="status"),
        IndexModel([("company_id", ASCENDING), ("created_at", DESCENDING)], name="company_created"),
        IndexModel(
            [("company_id", ASCENDING), ("device_id", ASCENDING), ("created_at", DESCENDING)],
            name="company_device_created",
        ),
        IndexModel(
            [("company_id", ASCENDING), ("viewer_user_id", ASCENDING), ("created_at", DESCENDING)],
            name="company_viewer_created",
        ),
        # At most one active session per person, enforced by the database (two simultaneous requests used to
        # both pass the "already live?" check and create two sessions).
        IndexModel(
            [("company_id", ASCENDING), ("employee_id", ASCENDING)],
            name="uniq_active_per_employee",
            unique=True,
            partialFilterExpression={"status": {"$in": [s.value for s in ACTIVE_STATUSES]}},
        ),
    )

    @classmethod
    async def ensure_indexes(cls, db: Any) -> None:
        """Before the uniqueness index exists, end any duplicate active sessions left by the old race (newest wins)."""
        collection = db[cls.collection_name]
        duplicates = collection.aggregate(
            [
                {"$match": {"status": {"$in": [s.value for s in ACTIVE_STATUSES]}}},
                {"$sort": {"created_at": -1}},
                {"$group": {"_id": {"c": "$company_id", "e": "$employee_id"}, "ids": {"$push": "$_id"}}},
                {"$match": {"ids.1": {"$exists": True}}},
            ]
        )
        async for group in await duplicates:
            await collection.update_many(
                {"_id": {"$in": group["ids"][1:]}},
                {"$set": {"status": LiveStatus.ENDED, "end_reason": "duplicate", "ended_at": utcnow()}},
            )
        await super().ensure_indexes(db)

    async def active_for_employee(self, company_id: ObjectId, employee_id: ObjectId) -> LiveSession | None:
        return await self._find_one(
            self._scoped(company_id, {"employee_id": employee_id, "status": {"$in": list(ACTIVE_STATUSES)}})
        )

    async def active_in_company(self, company_id: ObjectId) -> list[LiveSession]:
        return await self._find_many(
            self._scoped(company_id, {"status": {"$in": list(ACTIVE_STATUSES)}}), limit=1000
        )

    async def recent(
        self, company_id: ObjectId, employee_ids: list[ObjectId] | None, limit: int
    ) -> list[LiveSession]:
        """Newest first. `employee_ids=None` means every employee in the workspace."""
        query: dict[str, Any] = {} if employee_ids is None else {"employee_id": {"$in": employee_ids}}
        return await self._find_many(
            self._scoped(company_id, query), sort=[("created_at", DESCENDING)], limit=limit
        )

    async def in_range(
        self,
        company_id: ObjectId,
        employee_ids: Sequence[ObjectId],
        start: datetime,
        end: datetime,
        limit: int,
    ) -> list[LiveSession]:
        return await self._find_many(
            self._scoped(
                company_id,
                {"employee_id": {"$in": list(employee_ids)}, "created_at": {"$gte": start, "$lt": end}},
            ),
            sort=[("created_at", 1)],
            limit=limit,
        )

    async def set_status(
        self, company_id: ObjectId, session_id: ObjectId, changes: dict[str, Any]
    ) -> LiveSession | None:
        return await self._update_one(
            self._scoped(company_id, {"_id": session_id, "status": {"$ne": LiveStatus.ENDED}}), changes
        )

    # Unscoped by design: on start-up, sessions left open by a previous process are closed.
    async def end_orphans(self, now: datetime) -> int:
        result = await self._collection.update_many(
            {"status": {"$in": list(ACTIVE_STATUSES)}},
            {
                "$set": {
                    "status": LiveStatus.ENDED,
                    "ended_at": now,
                    "end_reason": "server_restart",
                    "updated_at": now,
                }
            },
        )
        return result.modified_count


class LiveSessionEventRepository(TenantRepository[LiveSessionEvent]):
    """The step-by-step timeline of each live session. Kept as long as the session log (the life of the workspace)."""

    collection_name = "live_session_events"
    model = LiveSessionEvent
    indexes = (
        IndexModel(
            [("company_id", ASCENDING), ("session_id", ASCENDING), ("timestamp", ASCENDING)],
            name="company_session_time",
        ),
        IndexModel([("company_id", ASCENDING), ("timestamp", DESCENDING)], name="company_time"),
        IndexModel(
            [("company_id", ASCENDING), ("event", ASCENDING), ("timestamp", DESCENDING)],
            name="company_event_time",
        ),
    )

    async def record(
        self,
        company_id: ObjectId,
        session_id: ObjectId,
        event: LiveEventType,
        *,
        actor_role: str,
        actor_id: ObjectId | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> LiveSessionEvent:
        return await self.create(
            company_id,
            LiveSessionEvent(
                company_id=company_id,
                session_id=session_id,
                event=event,
                actor_id=actor_id,
                actor_role=actor_role,
                metadata=metadata or {},
                timestamp=utcnow(),
            ),
        )

    async def for_session(
        self, company_id: ObjectId, session_id: ObjectId, limit: int = 200
    ) -> Sequence[LiveSessionEvent]:
        return await self._find_many(
            self._scoped(company_id, {"session_id": session_id}), sort=[("timestamp", ASCENDING)], limit=limit
        )
