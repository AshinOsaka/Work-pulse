"""Productivity rules and the per-day website and window-title rollups."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from bson import ObjectId
from pymongo import ASCENDING, IndexModel, UpdateOne
from pymongo.asynchronous.database import AsyncDatabase

from app.models.productivity import ProductivityRule, RuleScope, WorkProfile
from app.repositories.base import CASE_INSENSITIVE, BaseRepository, Document, TenantRepository
from app.utils.time import utcnow


class ProductivityRuleRepository(TenantRepository[ProductivityRule]):
    collection_name = "productivity_rules"
    model = ProductivityRule
    indexes = (
        IndexModel(
            [
                ("company_id", ASCENDING),
                ("kind", ASCENDING),
                ("pattern", ASCENDING),
                ("scope", ASCENDING),
                ("scope_id", ASCENDING),
                ("role", ASCENDING),
            ],
            name="uniq_rule",
            unique=True,
        ),
    )

    async def all_for_company(self, company_id: ObjectId) -> list[ProductivityRule]:
        return await self._find_many(
            self._scoped(company_id), sort=[("kind", 1), ("pattern", 1)], limit=10_000
        )

    async def delete_for_scope(self, company_id: ObjectId, scope: RuleScope, scope_id: ObjectId) -> int:
        result = await self._collection.delete_many(
            self._scoped(company_id, {"scope": scope, "scope_id": scope_id})
        )
        return result.deleted_count

    async def count_by_scope_id(self, company_id: ObjectId, scope: RuleScope) -> dict[ObjectId, int]:
        rows = await (
            await self._collection.aggregate(
                [
                    {"$match": {"company_id": company_id, "scope": scope}},
                    {"$group": {"_id": "$scope_id", "n": {"$sum": 1}}},
                ]
            )
        ).to_list()
        return {row["_id"]: row["n"] for row in rows}


class WorkProfileRepository(TenantRepository[WorkProfile]):
    collection_name = "work_profiles"
    model = WorkProfile
    indexes = (
        IndexModel(
            [("company_id", ASCENDING), ("name", ASCENDING)],
            name="uniq_company_name",
            unique=True,
            collation=CASE_INSENSITIVE,
        ),
    )

    async def all_for_company(self, company_id: ObjectId) -> list[WorkProfile]:
        return await self._find_many(self._scoped(company_id), sort=[("name", 1)], limit=500)


@dataclass(frozen=True, slots=True)
class WebsiteIncrement:
    company_id: ObjectId
    employee_id: ObjectId
    day: date
    app_id: str
    domain: str
    seconds: float
    active_seconds: float


class WebsiteDailyRepository(BaseRepository[Any]):
    """Seconds per employee, local day, browser and domain. Written with `$inc` upserts like `activity_daily`."""

    collection_name = "website_daily"
    indexes = (
        IndexModel(
            [
                ("company_id", ASCENDING),
                ("employee_id", ASCENDING),
                ("day", ASCENDING),
                ("app_id", ASCENDING),
                ("domain", ASCENDING),
            ],
            name="uniq_company_employee_day_app_domain",
            unique=True,
        ),
        IndexModel([("company_id", ASCENDING), ("day", ASCENDING)], name="company_day"),
    )

    def __init__(self, db: AsyncDatabase[Document]) -> None:
        self._db = db
        self._collection = db[self.collection_name]

    async def increment(self, rows: Sequence[WebsiteIncrement]) -> None:
        if not rows:
            return
        merged: dict[tuple[Any, ...], list[float]] = {}
        for r in rows:
            key = (r.company_id, r.employee_id, r.day.isoformat(), r.app_id, r.domain)
            acc = merged.setdefault(key, [0.0, 0.0])
            acc[0] += r.seconds
            acc[1] += r.active_seconds
        now = utcnow()
        await self._collection.bulk_write(
            [
                UpdateOne(
                    {"company_id": k[0], "employee_id": k[1], "day": k[2], "app_id": k[3], "domain": k[4]},
                    {
                        "$inc": {"seconds": round(v[0], 2), "active_seconds": round(v[1], 2)},
                        "$set": {"updated_at": now},
                        "$setOnInsert": {"created_at": now},
                    },
                    upsert=True,
                )
                for k, v in merged.items()
            ],
            ordered=False,
        )

    async def rows(
        self, company_id: ObjectId, employee_ids: Sequence[ObjectId], start: date, end: date
    ) -> list[Document]:
        cursor = self._collection.find(
            {
                "company_id": company_id,
                "employee_id": {"$in": list(employee_ids)},
                "day": {"$gte": start.isoformat(), "$lte": end.isoformat()},
            },
            projection={
                "_id": 0,
                "employee_id": 1,
                "day": 1,
                "app_id": 1,
                "domain": 1,
                "seconds": 1,
                "active_seconds": 1,
            },
        )
        return [doc async for doc in cursor]

    async def totals_by_domain(
        self, company_id: ObjectId, employee_ids: Sequence[ObjectId], start: date, end: date, limit: int = 50
    ) -> list[dict[str, Any]]:
        """Seconds per domain across employees for [start, end] (inclusive local days), most used first."""
        if not employee_ids:
            return []
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
                    "_id": "$domain",
                    "seconds": {"$sum": "$seconds"},
                    "active_seconds": {"$sum": "$active_seconds"},
                    "employees": {"$addToSet": "$employee_id"},
                }
            },
            {"$project": {"seconds": 1, "active_seconds": 1, "employees": {"$size": "$employees"}}},
            {"$sort": {"seconds": -1}},
            {"$limit": limit},
        ]
        cursor = await self._collection.aggregate(pipeline)
        return [document async for document in cursor]


@dataclass(frozen=True, slots=True)
class TitleIncrement:
    company_id: ObjectId
    employee_id: ObjectId
    day: date
    app_id: str
    domain: str | None
    title: str
    seconds: float
    active_seconds: float


class WindowTitleDailyRepository(BaseRepository[Any]):
    """Seconds per employee, local day, application, domain and (already redacted) window title.

    Written only when the workspace captures window titles, with `$inc` upserts like `website_daily`, so the
    per-title breakdown outlives the short-lived raw segments. ``domain`` is None for time without a website.
    """

    collection_name = "window_title_daily"
    indexes = (
        IndexModel(
            [
                ("company_id", ASCENDING),
                ("employee_id", ASCENDING),
                ("day", ASCENDING),
                ("app_id", ASCENDING),
                ("domain", ASCENDING),
                ("title", ASCENDING),
            ],
            name="uniq_company_employee_day_app_domain_title",
            unique=True,
        ),
    )

    def __init__(self, db: AsyncDatabase[Document]) -> None:
        self._db = db
        self._collection = db[self.collection_name]

    async def increment(self, rows: Sequence[TitleIncrement]) -> None:
        if not rows:
            return
        merged: dict[tuple[Any, ...], list[float]] = {}
        for r in rows:
            key = (r.company_id, r.employee_id, r.day.isoformat(), r.app_id, r.domain, r.title)
            acc = merged.setdefault(key, [0.0, 0.0])
            acc[0] += r.seconds
            acc[1] += r.active_seconds
        now = utcnow()
        await self._collection.bulk_write(
            [
                UpdateOne(
                    {
                        "company_id": k[0],
                        "employee_id": k[1],
                        "day": k[2],
                        "app_id": k[3],
                        "domain": k[4],
                        "title": k[5],
                    },
                    {
                        "$inc": {"seconds": round(v[0], 2), "active_seconds": round(v[1], 2)},
                        "$set": {"updated_at": now},
                        "$setOnInsert": {"created_at": now},
                    },
                    upsert=True,
                )
                for k, v in merged.items()
            ],
            ordered=False,
        )

    async def totals_by_title(
        self,
        company_id: ObjectId,
        employee_id: ObjectId,
        start: date,
        end: date,
        *,
        app_id: str | None = None,
        domain: str | None = None,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        """Seconds per title for one website (by domain) or one application's time without a website."""
        match: Document = {
            "company_id": company_id,
            "employee_id": employee_id,
            "day": {"$gte": start.isoformat(), "$lte": end.isoformat()},
        }
        if domain is not None:
            match["domain"] = domain
        else:
            match["app_id"] = app_id
            match["domain"] = None
        pipeline: list[Document] = [
            {"$match": match},
            {"$group": {"_id": "$title", "seconds": {"$sum": "$seconds"}}},
            {"$sort": {"seconds": -1, "_id": 1}},
            {"$limit": limit},
        ]
        cursor = await self._collection.aggregate(pipeline)
        return [document async for document in cursor]
