"""Productivity rules and the per-day website rollup."""

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
