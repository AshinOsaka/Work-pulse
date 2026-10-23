"""Screenshot download requests: a small queue claimed atomically by the worker, plus each requester's history."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from bson import ObjectId
from pymongo import ASCENDING, DESCENDING, IndexModel, ReturnDocument

from app.models.screenshot_request import (
    ACTIVE_REQUEST_STATUSES,
    ScreenshotRequest,
    ScreenshotRequestStatus,
)
from app.repositories.base import TenantRepository
from app.utils.time import utcnow


class ScreenshotRequestRepository(TenantRepository[ScreenshotRequest]):
    collection_name = "screenshot_requests"
    model = ScreenshotRequest
    indexes = (
        IndexModel(
            [("company_id", ASCENDING), ("requested_by", ASCENDING), ("created_at", DESCENDING)],
            name="company_requester_created",
        ),
        IndexModel([("status", ASCENDING), ("created_at", ASCENDING)], name="status_created"),
        IndexModel([("expires_at", ASCENDING)], name="expires_at", sparse=True),
    )

    async def for_requester(
        self, company_id: ObjectId, user_id: ObjectId, limit: int = 50
    ) -> list[ScreenshotRequest]:
        return await self._find_many(
            self._scoped(company_id, {"requested_by": user_id}),
            sort=[("created_at", DESCENDING)],
            limit=limit,
        )

    async def active_for_requester(self, company_id: ObjectId, user_id: ObjectId) -> int:
        return await self._collection.count_documents(
            self._scoped(
                company_id, {"requested_by": user_id, "status": {"$in": list(ACTIVE_REQUEST_STATUSES)}}
            )
        )

    # Unscoped by design: the worker serves every workspace, oldest request first.
    async def claim_next(self) -> ScreenshotRequest | None:
        now = utcnow()
        doc = await self._collection.find_one_and_update(
            {"status": ScreenshotRequestStatus.QUEUED},
            {"$set": {"status": ScreenshotRequestStatus.PREPARING, "progress": 5, "started_at": now, "updated_at": now}},
            sort=[("created_at", ASCENDING)],
            return_document=ReturnDocument.AFTER,
        )
        return self.model.model_validate(doc) if doc else None

    async def progress(self, request_id: ObjectId, changes: dict[str, Any]) -> None:
        await self._collection.update_one(
            {"_id": request_id}, {"$set": {**changes, "updated_at": utcnow()}}
        )

    async def requeue_interrupted(self) -> int:
        """Requests a previous process was packaging start again from the beginning."""
        result = await self._collection.update_many(
            {"status": {"$in": [ScreenshotRequestStatus.PREPARING, ScreenshotRequestStatus.PACKAGING]}},
            {"$set": {"status": ScreenshotRequestStatus.QUEUED, "progress": 0, "updated_at": utcnow()}},
        )
        return result.modified_count

    async def expired(self, now: datetime, limit: int = 200) -> list[ScreenshotRequest]:
        return await self._find_many(
            {"status": ScreenshotRequestStatus.READY, "expires_at": {"$lte": now}},
            sort=[("expires_at", 1)],
            limit=limit,
        )

    async def count_downloads(self, company_id: ObjectId, request_id: ObjectId) -> None:
        await self._collection.update_one(
            self._scoped(company_id, {"_id": request_id}), {"$inc": {"downloads": 1}}
        )
