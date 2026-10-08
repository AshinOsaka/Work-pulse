"""Screenshot metadata storage."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any

from bson import ObjectId
from pymongo import ASCENDING, DESCENDING, IndexModel

from app.models.screenshot import Screenshot
from app.repositories.base import Document, TenantRepository


class ScreenshotRepository(TenantRepository[Screenshot]):
    collection_name = "screenshots"
    model = Screenshot
    indexes = (
        IndexModel(
            [("device_id", ASCENDING), ("client_id", ASCENDING)], name="uniq_device_client", unique=True
        ),
        IndexModel(
            [("company_id", ASCENDING), ("employee_id", ASCENDING), ("captured_at", DESCENDING)],
            name="company_employee_captured",
        ),
        IndexModel([("company_id", ASCENDING), ("captured_at", DESCENDING)], name="company_captured"),
        IndexModel([("device_id", ASCENDING), ("captured_at", DESCENDING)], name="device_captured"),
        # Not a TTL index: expiry must delete the stored objects first (see purge in ScreenshotService).
        IndexModel([("expires_at", ASCENDING)], name="expires_at"),
    )

    async def get_by_client_id(
        self, company_id: ObjectId, device_id: ObjectId, client_id: str
    ) -> Screenshot | None:
        return await self._find_one(
            self._scoped(company_id, {"device_id": device_id, "client_id": client_id})
        )

    async def last_for_device(self, company_id: ObjectId, device_id: ObjectId) -> Screenshot | None:
        found = await self._find_many(
            self._scoped(company_id, {"device_id": device_id}), sort=[("captured_at", DESCENDING)], limit=1
        )
        return found[0] if found else None

    async def last_for_employee(self, company_id: ObjectId, employee_id: ObjectId) -> Screenshot | None:
        found = await self._find_many(
            self._scoped(company_id, {"employee_id": employee_id}),
            sort=[("captured_at", DESCENDING)],
            limit=1,
        )
        return found[0] if found else None

    async def page(
        self,
        company_id: ObjectId,
        employee_ids: Sequence[ObjectId],
        start: datetime,
        end: datetime,
        *,
        before: datetime | None,
        limit: int,
    ) -> list[Screenshot]:
        """Newest first, keyset-paginated on captured_at."""
        upper = min(end, before) if before else end
        return await self._find_many(
            self._scoped(
                company_id,
                {"employee_id": {"$in": list(employee_ids)}, "captured_at": {"$gte": start, "$lt": upper}},
            ),
            sort=[("captured_at", DESCENDING), ("_id", DESCENDING)],
            limit=limit,
        )

    async def in_range(
        self,
        company_id: ObjectId,
        employee_ids: Sequence[ObjectId],
        start: datetime,
        end: datetime,
        limit: int,
    ) -> list[Screenshot]:
        """Metadata of screenshots captured in [start, end) for reports (never the images)."""
        return await self._find_many(
            self._scoped(
                company_id,
                {"employee_id": {"$in": list(employee_ids)}, "captured_at": {"$gte": start, "$lt": end}},
            ),
            sort=[("captured_at", 1)],
            limit=limit,
        )

    async def capture_times(
        self,
        company_id: ObjectId,
        employee_ids: Sequence[ObjectId],
        start: datetime,
        end: datetime,
        limit: int,
    ) -> list[Document]:
        """Lightweight projection for timelines: no object keys or sizes."""
        cursor = (
            self._collection.find(
                self._scoped(
                    company_id,
                    {"employee_id": {"$in": list(employee_ids)}, "captured_at": {"$gte": start, "$lt": end}},
                ),
                projection={"_id": 1, "captured_at": 1, "employee_id": 1},
            )
            .sort("captured_at", ASCENDING)
            .limit(limit)
        )
        return [doc async for doc in cursor]

    async def reset_expiry(self, company_id: ObjectId, retention: timedelta) -> int:
        """Apply a changed retention period to everything already stored."""
        result = await self._collection.update_many(
            {"company_id": company_id},
            [{"$set": {"expires_at": {"$add": ["$captured_at", int(retention.total_seconds() * 1000)]}}}],
        )
        return result.modified_count

    # Unscoped by design: the retention sweeper works across all tenants.
    async def expired(self, now: datetime, limit: int) -> list[Screenshot]:
        return await self._find_many(
            {"expires_at": {"$lte": now}}, sort=[("expires_at", ASCENDING)], limit=limit
        )

    async def delete_ids(self, ids: Sequence[ObjectId]) -> int:
        result = await self._collection.delete_many({"_id": {"$in": list(ids)}})
        return result.deleted_count

    async def stats(self, company_id: ObjectId) -> dict[str, Any]:
        rows = await (
            await self._collection.aggregate(
                [
                    {"$match": {"company_id": company_id}},
                    {
                        "$group": {
                            "_id": None,
                            "count": {"$sum": 1},
                            "bytes": {"$sum": {"$add": ["$size_bytes", "$thumb_size_bytes"]}},
                        }
                    },
                ]
            )
        ).to_list()
        return rows[0] if rows else {"count": 0, "bytes": 0}
