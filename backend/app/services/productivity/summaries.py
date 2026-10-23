"""Durable daily summaries: one finalised, permanent record per person and local day.

The rollups (`activity_daily`, `website_daily`) and work sessions are kept long term, but the *computed*
per-day result — time accounting, category seconds, focus and switching, customer time — lives only in the
45-day `productivity_daily` cache, which is keyed by a rule fingerprint and expires. Raw `activity_segments`
(which focus and switching are derived from) are kept only briefly (see the finaliser).

`daily_summaries` is the permanent home for the finalised numbers. It is written **before** raw segments are
purged ("finalise first"), so long-horizon reports (15-day, monthly and beyond) stay correct and fast without
re-reading raw data. Each document is one `Metrics.as_dict()` payload plus the engine version that produced it;
a later engine change simply writes a new version and old versions are ignored.

Unlike the cache, this collection has **no TTL** — it is the system of record for historical productivity.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Any

from bson import ObjectId
from pymongo import ASCENDING, IndexModel, UpdateOne
from pymongo.asynchronous.database import AsyncDatabase

from app.repositories.base import BaseRepository, Document
from app.services.productivity.engine import Metrics
from app.services.productivity.rules import ENGINE_VERSION
from app.utils.time import utcnow


class DailySummaryRepository(BaseRepository[Any]):
    collection_name = "daily_summaries"
    indexes = (
        IndexModel(
            [("company_id", ASCENDING), ("employee_id", ASCENDING), ("day", ASCENDING)],
            name="uniq_company_employee_day",
            unique=True,
        ),
        IndexModel([("company_id", ASCENDING), ("day", ASCENDING)], name="company_day"),
    )

    def __init__(self, db: AsyncDatabase[Document]) -> None:
        self._db = db
        self._collection = db[self.collection_name]

    async def upsert_many(
        self, company_id: ObjectId, rows: Sequence[tuple[ObjectId, date, Metrics]]
    ) -> int:
        """Store (or replace) the finalised metrics for each (employee, day). Returns the number written."""
        if not rows:
            return 0
        now = utcnow()
        operations = [
            UpdateOne(
                {"company_id": company_id, "employee_id": employee_id, "day": day.isoformat()},
                {
                    "$set": {
                        "metrics": metrics.as_dict(),
                        "engine_version": ENGINE_VERSION,
                        "finalized_at": now,
                    },
                    "$setOnInsert": {"created_at": now},
                },
                upsert=True,
            )
            for employee_id, day, metrics in rows
        ]
        await self._collection.bulk_write(operations, ordered=False)
        return len(operations)

    async def metrics_for(
        self, company_id: ObjectId, employee_ids: Sequence[ObjectId], start: date, end: date
    ) -> dict[tuple[ObjectId, date], Metrics]:
        """Finalised metrics per (employee, day) for [start, end], current engine version only."""
        if not employee_ids:
            return {}
        cursor = self._collection.find(
            {
                "company_id": company_id,
                "employee_id": {"$in": list(employee_ids)},
                "day": {"$gte": start.isoformat(), "$lte": end.isoformat()},
                "engine_version": ENGINE_VERSION,
            },
            {"_id": 0, "employee_id": 1, "day": 1, "metrics": 1},
        )
        out: dict[tuple[ObjectId, date], Metrics] = {}
        async for doc in cursor:
            out[(doc["employee_id"], date.fromisoformat(doc["day"]))] = Metrics.from_dict(doc["metrics"])
        return out

    async def finalized_employees_on(
        self, company_id: ObjectId, day: date, employee_ids: Sequence[ObjectId]
    ) -> set[ObjectId]:
        """Which of these employees have a finalised summary for the day (used to gate raw-data purging)."""
        if not employee_ids:
            return set()
        cursor = self._collection.find(
            {"company_id": company_id, "day": day.isoformat(), "employee_id": {"$in": list(employee_ids)}},
            {"_id": 0, "employee_id": 1},
        )
        return {doc["employee_id"] async for doc in cursor}
