"""Time claims, per company: an employee's claims by day, and the ones in a reviewer's scope."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from bson import ObjectId
from pymongo import ASCENDING, DESCENDING, IndexModel

from app.models.time_claim import TimeClaim, TimeClaimStatus
from app.repositories.base import TenantRepository


class TimeClaimRepository(TenantRepository[TimeClaim]):
    collection_name = "time_claims"
    model = TimeClaim
    indexes = (
        IndexModel(
            [("company_id", ASCENDING), ("employee_id", ASCENDING), ("day", ASCENDING)],
            name="company_employee_day",
        ),
        IndexModel(
            [("company_id", ASCENDING), ("status", ASCENDING), ("started_at", DESCENDING)],
            name="company_status_started",
        ),
    )

    async def for_day(self, company_id: ObjectId, employee_id: ObjectId, day: str) -> list[TimeClaim]:
        """The employee's claims on that day that still count or wait for a decision (not rejected)."""
        return await self._find_many(
            self._scoped(
                company_id,
                {"employee_id": employee_id, "day": day, "status": {"$ne": TimeClaimStatus.REJECTED}},
            ),
            sort=[("started_at", ASCENDING)],
            limit=200,
        )

    async def approved_between(
        self, company_id: ObjectId, employee_ids: Sequence[ObjectId], start_day: str, end_day: str
    ) -> list[TimeClaim]:
        if not employee_ids:
            return []
        return await self._find_many(
            self._scoped(
                company_id,
                {
                    "employee_id": {"$in": list(employee_ids)},
                    "day": {"$gte": start_day, "$lte": end_day},
                    "status": TimeClaimStatus.APPROVED,
                },
            ),
            sort=[("started_at", ASCENDING)],
            limit=20000,
        )

    async def search(
        self, company_id: ObjectId, query: Mapping[str, Any], skip: int, limit: int
    ) -> tuple[list[TimeClaim], int]:
        scoped = self._scoped(company_id, query)
        items = await self._find_many(scoped, sort=[("started_at", DESCENDING)], skip=skip, limit=limit)
        return items, await self._count(scoped)

    async def update_status(
        self, company_id: ObjectId, claim_id: ObjectId, changes: Mapping[str, Any]
    ) -> TimeClaim | None:
        return await self.update_by_id(company_id, claim_id, changes)


def overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    return a_start < b_end and b_start < a_end
