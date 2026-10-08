"""Activity storage, optimised for write volume.

* `activity_segments` — raw segments. A whole agent batch is written with ONE
  unordered `insert_many`; the unique (device_id, event_id) index makes
  retries idempotent without a read-before-write.
* `activity_daily` — pre-aggregated per employee, local day and application.
  Updated with ONE `bulk_write` of `$inc` upserts per batch, so reports read a
  handful of small documents instead of scanning raw segments.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from bson import ObjectId
from pymongo import ASCENDING, DESCENDING, IndexModel, UpdateOne
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import BulkWriteError

from app.models.activity import ActivitySegment
from app.repositories.base import BaseRepository, Document, TenantRepository
from app.utils.time import utcnow

SEGMENT_RETENTION_SECONDS = 180 * 86_400
_DUPLICATE_KEY = 11000


class ActivitySegmentRepository(TenantRepository[ActivitySegment]):
    collection_name = "activity_segments"
    model = ActivitySegment
    indexes = (
        IndexModel(
            [("device_id", ASCENDING), ("event_id", ASCENDING)], name="uniq_device_event", unique=True
        ),
        IndexModel(
            [("company_id", ASCENDING), ("employee_id", ASCENDING), ("started_at", DESCENDING)],
            name="company_employee_started",
        ),
        IndexModel([("company_id", ASCENDING), ("started_at", DESCENDING)], name="company_started"),
        # "When did this open session last show activity?" reads one index entry per session.
        IndexModel(
            [("company_id", ASCENDING), ("session_id", ASCENDING), ("ended_at", DESCENDING)],
            name="company_session_ended",
        ),
        # Raw segments expire; the daily rollup keeps long-term history.
        IndexModel(
            [("created_at", ASCENDING)], name="ttl_created_at", expireAfterSeconds=SEGMENT_RETENTION_SECONDS
        ),
    )

    async def insert_batch(self, segments: Sequence[ActivitySegment]) -> set[str]:
        """Insert all segments in one round trip; returns the event ids that were new."""
        if not segments:
            return set()
        try:
            await self._collection.insert_many([s.to_document() for s in segments], ordered=False)
            return {s.event_id for s in segments}
        except BulkWriteError as exc:
            errors = exc.details.get("writeErrors", [])
            if any(e.get("code") != _DUPLICATE_KEY for e in errors):
                raise
            failed = {e["index"] for e in errors}
            return {s.event_id for i, s in enumerate(segments) if i not in failed}

    async def last_activity(self, company_id: ObjectId, session_ids: Sequence[str]) -> dict[str, datetime]:
        """Latest recorded segment end per work session (evidence of when an unclosed session stopped)."""
        if not session_ids:
            return {}
        rows = await (
            await self._collection.aggregate(
                [
                    {"$match": {"company_id": company_id, "session_id": {"$in": list(session_ids)}}},
                    # Sorted like the index, so $first is answered from the index (no document reads).
                    {"$sort": {"company_id": 1, "session_id": 1, "ended_at": -1}},
                    {"$group": {"_id": "$session_id", "last": {"$first": "$ended_at"}}},
                ]
            )
        ).to_list()
        return {row["_id"]: row["last"] for row in rows}

    async def light_for_employees(
        self,
        company_id: ObjectId,
        employee_ids: Sequence[ObjectId],
        start: datetime,
        end: datetime,
        limit: int,
    ) -> list[Document]:
        """Just what focus and switching analysis needs, oldest first."""
        cursor = (
            self._collection.find(
                self._scoped(
                    company_id,
                    {
                        "employee_id": {"$in": list(employee_ids)},
                        "started_at": {"$lt": end},
                        "ended_at": {"$gt": start},
                    },
                ),
                projection={
                    "_id": 0,
                    "employee_id": 1,
                    "app_id": 1,
                    "app_name": 1,
                    "domain": 1,
                    "started_at": 1,
                    "ended_at": 1,
                },
            )
            .sort("started_at", ASCENDING)
            .limit(limit)
        )
        return [doc async for doc in cursor]

    async def for_employee(
        self, company_id: ObjectId, employee_id: ObjectId, start: datetime, end: datetime, limit: int = 2000
    ) -> list[ActivitySegment]:
        return await self._find_many(
            self._scoped(
                company_id,
                {"employee_id": employee_id, "started_at": {"$lt": end}, "ended_at": {"$gt": start}},
            ),
            sort=[("started_at", ASCENDING)],
            limit=limit,
        )


@dataclass(frozen=True, slots=True)
class DailyIncrement:
    company_id: ObjectId
    employee_id: ObjectId
    day: date
    app_id: str
    app_name: str
    seconds: float
    active_seconds: float


class ActivityDailyRepository(BaseRepository[Any]):
    """Rollup collection; documents are written with upserts rather than as models."""

    collection_name = "activity_daily"
    indexes = (
        IndexModel(
            [
                ("company_id", ASCENDING),
                ("employee_id", ASCENDING),
                ("day", ASCENDING),
                ("app_id", ASCENDING),
            ],
            name="uniq_company_employee_day_app",
            unique=True,
        ),
        IndexModel([("company_id", ASCENDING), ("day", ASCENDING)], name="company_day"),
    )

    def __init__(self, db: AsyncDatabase[Document]) -> None:
        self._db = db
        self._collection = db[self.collection_name]

    async def increment(self, rows: Sequence[DailyIncrement]) -> None:
        """Apply all increments in a single unordered bulk write."""
        if not rows:
            return
        merged: dict[tuple[ObjectId, ObjectId, str, str], DailyIncrement] = {}
        for row in rows:  # collapse duplicates in the batch first: fewer operations
            key = (row.company_id, row.employee_id, row.day.isoformat(), row.app_id)
            prev = merged.get(key)
            merged[key] = (
                row
                if prev is None
                else DailyIncrement(
                    row.company_id,
                    row.employee_id,
                    row.day,
                    row.app_id,
                    row.app_name,
                    prev.seconds + row.seconds,
                    prev.active_seconds + row.active_seconds,
                )
            )
        now = utcnow()
        operations = [
            UpdateOne(
                {
                    "company_id": r.company_id,
                    "employee_id": r.employee_id,
                    "day": r.day.isoformat(),
                    "app_id": r.app_id,
                },
                {
                    "$inc": {"seconds": round(r.seconds, 2), "active_seconds": round(r.active_seconds, 2)},
                    "$set": {"app_name": r.app_name, "updated_at": now},
                    "$setOnInsert": {"created_at": now},
                },
                upsert=True,
            )
            for r in merged.values()
        ]
        await self._collection.bulk_write(operations, ordered=False)

    async def rows(
        self, company_id: ObjectId, employee_ids: Sequence[ObjectId], start: date, end: date
    ) -> list[Document]:
        """Raw rollup rows (employee, day, application) for [start, end]."""
        cursor = self._collection.find(
            {
                "company_id": company_id,
                "employee_id": {"$in": list(employee_ids)},
                "day": {"$gte": start.isoformat(), "$lte": end.isoformat()},
            },
            projection={"_id": 0, "employee_id": 1, "day": 1, "app_id": 1, "app_name": 1, "seconds": 1},
        )
        return [doc async for doc in cursor]

    async def totals_by_app(
        self, company_id: ObjectId, employee_ids: Sequence[ObjectId], start: date, end: date
    ) -> list[dict[str, Any]]:
        """Seconds per application across employees for [start, end] (inclusive local days)."""
        pipeline: list[Document] = [
            {
                "$match": {
                    "company_id": company_id,
                    "employee_id": {"$in": list(employee_ids)},
                    "day": {"$gte": start.isoformat(), "$lte": end.isoformat()},
                }
            },
            {
                "$group": {
                    "_id": "$app_id",
                    "app_name": {"$last": "$app_name"},
                    "seconds": {"$sum": "$seconds"},
                    "active_seconds": {"$sum": "$active_seconds"},
                    "employees": {"$addToSet": "$employee_id"},
                }
            },
            {
                "$project": {
                    "app_name": 1,
                    "seconds": 1,
                    "active_seconds": 1,
                    "employees": {"$size": "$employees"},
                }
            },
            {"$sort": {"seconds": -1}},
        ]
        cursor = await self._collection.aggregate(pipeline)
        return [document async for document in cursor]

    async def totals_by_employee(
        self, company_id: ObjectId, employee_ids: Sequence[ObjectId], start: date, end: date
    ) -> list[dict[str, Any]]:
        pipeline: list[Document] = [
            {
                "$match": {
                    "company_id": company_id,
                    "employee_id": {"$in": list(employee_ids)},
                    "day": {"$gte": start.isoformat(), "$lte": end.isoformat()},
                }
            },
            {
                "$group": {
                    "_id": "$employee_id",
                    "seconds": {"$sum": "$seconds"},
                    "active_seconds": {"$sum": "$active_seconds"},
                    "apps": {"$push": {"app_name": "$app_name", "seconds": "$seconds"}},
                }
            },
            {"$sort": {"seconds": -1}},
        ]
        cursor = await self._collection.aggregate(pipeline)
        return [document async for document in cursor]
