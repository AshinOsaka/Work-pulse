"""Repositories for departments, teams, employees and devices."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from bson import ObjectId
from pymongo import ASCENDING, DESCENDING, IndexModel

from app.models.organization import Department, Device, DeviceStatus, Employee, EmployeeStatus, Team
from app.repositories.base import CASE_INSENSITIVE, Document, TenantRepository
from app.utils.time import utcnow

_CI = CASE_INSENSITIVE.document


def _and(*clauses: Mapping[str, Any] | None) -> Document:
    """Combine filter fragments with `$and`, dropping empty ones."""
    parts = [dict(c) for c in clauses if c]
    if not parts:
        return {}
    return parts[0] if len(parts) == 1 else {"$and": parts}


class DepartmentRepository(TenantRepository[Department]):
    collection_name = "departments"
    model = Department
    indexes = (
        IndexModel(
            [("company_id", ASCENDING), ("name", ASCENDING)],
            name="uniq_company_name_ci",
            unique=True,
            collation=_CI,
        ),
        IndexModel([("company_id", ASCENDING), ("status", ASCENDING)], name="company_status"),
        IndexModel([("company_id", ASCENDING), ("head_employee_id", ASCENDING)], name="company_head"),
        IndexModel([("created_at", DESCENDING)], name="created_at"),
    )
    obsolete_indexes = ("uniq_company_name",)

    async def list_all(self, company_id: ObjectId) -> list[Department]:
        return await self._find_many(
            self._scoped(company_id), sort=[("name", ASCENDING)], limit=1000, collation=CASE_INSENSITIVE
        )

    async def ids_headed_by(self, company_id: ObjectId, employee_id: ObjectId) -> list[ObjectId]:
        return [
            d.id for d in await self._find_many(self._scoped(company_id, {"head_employee_id": employee_id}))
        ]


class TeamRepository(TenantRepository[Team]):
    collection_name = "teams"
    model = Team
    indexes = (
        IndexModel(
            [("company_id", ASCENDING), ("name", ASCENDING)],
            name="uniq_company_name_ci",
            unique=True,
            collation=_CI,
        ),
        IndexModel([("company_id", ASCENDING), ("department_id", ASCENDING)], name="company_department"),
        IndexModel([("company_id", ASCENDING), ("lead_employee_id", ASCENDING)], name="company_lead"),
        IndexModel([("company_id", ASCENDING), ("status", ASCENDING)], name="company_status"),
        IndexModel([("created_at", DESCENDING)], name="created_at"),
    )
    obsolete_indexes = ("uniq_company_name",)

    async def list_all(self, company_id: ObjectId, department_id: ObjectId | None = None) -> list[Team]:
        query = {"department_id": department_id} if department_id else None
        return await self._find_many(
            self._scoped(company_id, query),
            sort=[("name", ASCENDING)],
            limit=1000,
            collation=CASE_INSENSITIVE,
        )

    async def ids_led_by(self, company_id: ObjectId, employee_id: ObjectId) -> list[ObjectId]:
        return [
            t.id for t in await self._find_many(self._scoped(company_id, {"lead_employee_id": employee_id}))
        ]


SORTABLE_EMPLOYEE_FIELDS = {"full_name", "job_title", "status", "employee_code", "hired_on", "created_at"}


@dataclass(frozen=True, slots=True)
class EmployeeQuery:
    search: str | None = None
    statuses: Sequence[EmployeeStatus] = ()
    department_id: ObjectId | None = None
    team_id: ObjectId | None = None
    manager_id: ObjectId | None = None
    sort: str = "full_name"
    descending: bool = False
    skip: int = 0
    limit: int = 25
    extra: Mapping[str, Any] = field(default_factory=dict)

    def to_filter(self) -> Document:
        clauses: list[Mapping[str, Any]] = []
        if self.search:
            pattern = {"$regex": re.escape(self.search.strip()), "$options": "i"}
            clauses.append(
                {
                    "$or": [
                        {"full_name": pattern},
                        {"email": pattern},
                        {"employee_code": pattern},
                        {"job_title": pattern},
                    ]
                }
            )
        if self.statuses:
            clauses.append({"status": {"$in": [s.value for s in self.statuses]}})
        if self.department_id:
            clauses.append({"department_id": self.department_id})
        if self.team_id:
            clauses.append({"team_id": self.team_id})
        if self.manager_id:
            clauses.append({"manager_employee_id": self.manager_id})
        if self.extra:
            clauses.append(self.extra)
        return _and(*clauses)


class EmployeeRepository(TenantRepository[Employee]):
    collection_name = "employees"
    model = Employee
    indexes = (
        IndexModel([("company_id", ASCENDING), ("status", ASCENDING)], name="company_status"),
        IndexModel(
            [("company_id", ASCENDING), ("employee_code", ASCENDING)],
            name="uniq_company_employee_code",
            unique=True,
            partialFilterExpression={"employee_code": {"$type": "string"}},
        ),
        IndexModel([("company_id", ASCENDING), ("email", ASCENDING)], name="uniq_company_email", unique=True),
        IndexModel(
            [("company_id", ASCENDING), ("full_name", ASCENDING)], name="company_full_name_ci", collation=_CI
        ),
        IndexModel([("user_id", ASCENDING)], name="user_id", sparse=True),
        IndexModel([("company_id", ASCENDING), ("department_id", ASCENDING)], name="company_department"),
        IndexModel([("company_id", ASCENDING), ("team_id", ASCENDING)], name="company_team"),
        IndexModel([("company_id", ASCENDING), ("work_profile_id", ASCENDING)], name="company_work_profile"),
        IndexModel([("company_id", ASCENDING), ("manager_employee_id", ASCENDING)], name="company_manager"),
        IndexModel([("company_id", ASCENDING), ("created_at", DESCENDING)], name="company_created_at"),
    )
    obsolete_indexes = ("company_email",)

    async def set_work_profile(
        self, company_id: ObjectId, profile_id: ObjectId, employee_ids: Sequence[ObjectId]
    ) -> None:
        """Make exactly these employees the profile's members (others in it are released)."""
        await self._collection.update_many(
            self._scoped(company_id, {"work_profile_id": profile_id, "_id": {"$nin": list(employee_ids)}}),
            {"$set": {"work_profile_id": None}},
        )
        if employee_ids:
            await self._collection.update_many(
                self._scoped(company_id, {"_id": {"$in": list(employee_ids)}}),
                {"$set": {"work_profile_id": profile_id}},
            )

    async def search(self, company_id: ObjectId, query: EmployeeQuery) -> tuple[list[Employee], int]:
        mongo_filter = self._scoped(company_id, query.to_filter())
        direction = DESCENDING if query.descending else ASCENDING
        sort_field = query.sort if query.sort in SORTABLE_EMPLOYEE_FIELDS else "full_name"
        items = await self._find_many(
            mongo_filter,
            sort=[(sort_field, direction), ("_id", direction)],
            skip=query.skip,
            limit=query.limit,
            collation=CASE_INSENSITIVE,
        )
        total = await self._count(mongo_filter, collation=CASE_INSENSITIVE)
        return items, total

    async def get_in_scope(
        self, company_id: ObjectId, employee_id: ObjectId, scope: Mapping[str, Any] | None
    ) -> Employee | None:
        return await self._find_one(self._scoped(company_id, _and({"_id": employee_id}, scope)))

    async def ids_matching(
        self, company_id: ObjectId, query: Mapping[str, Any] | None = None
    ) -> list[ObjectId]:
        values = await self._collection.distinct("_id", self._scoped(company_id, query))
        return [v for v in values if isinstance(v, ObjectId)]

    async def distinct_user_ids(
        self, company_id: ObjectId, scope: Mapping[str, Any] | None = None
    ) -> list[ObjectId]:
        values = await self._collection.distinct(
            "user_id", self._scoped(company_id, _and(scope, {"user_id": {"$ne": None}}))
        )
        return [v for v in values if isinstance(v, ObjectId)]

    async def set_department_for_team(
        self, company_id: ObjectId, team_id: ObjectId, department_id: ObjectId | None
    ) -> int:
        """Keep members consistent when a team moves to another department."""
        result = await self._collection.update_many(
            self._scoped(company_id, {"team_id": team_id}),
            {"$set": {"department_id": department_id, "updated_at": utcnow()}},
        )
        return result.modified_count

    async def get_by_email(self, company_id: ObjectId, email: str) -> Employee | None:
        return await self._find_one(self._scoped(company_id, {"email": email}))

    async def get_by_user_id(self, company_id: ObjectId, user_id: ObjectId) -> Employee | None:
        return await self._find_one(self._scoped(company_id, {"user_id": user_id}))

    async def list_direct_reports(self, company_id: ObjectId, employee_id: ObjectId) -> list[Employee]:
        return await self._find_many(
            self._scoped(company_id, {"manager_employee_id": employee_id}),
            sort=[("full_name", ASCENDING)],
            limit=500,
            collation=CASE_INSENSITIVE,
        )

    async def descendant_ids(
        self, company_id: ObjectId, employee_id: ObjectId, max_depth: int = 25
    ) -> set[ObjectId]:
        """All direct and indirect reports of an employee (the reporting tree)."""
        pipeline: list[Document] = [
            {"$match": {"_id": employee_id, "company_id": company_id}},
            {
                "$graphLookup": {
                    "from": self.collection_name,
                    "startWith": "$_id",
                    "connectFromField": "_id",
                    "connectToField": "manager_employee_id",
                    "as": "reports",
                    "maxDepth": max_depth,
                    "restrictSearchWithMatch": {"company_id": company_id},
                }
            },
            {"$project": {"ids": "$reports._id"}},
        ]
        cursor = await self._collection.aggregate(pipeline)
        result: set[ObjectId] = set()
        async for document in cursor:
            result.update(document.get("ids", []))
        return result

    async def distinct_manager_ids(
        self, company_id: ObjectId, scope: Mapping[str, Any] | None = None
    ) -> list[ObjectId]:
        values = await self._collection.distinct(
            "manager_employee_id",
            self._scoped(company_id, _and(scope, {"manager_employee_id": {"$ne": None}})),
        )
        return [v for v in values if isinstance(v, ObjectId)]

    async def counts_by(
        self, company_id: ObjectId, field_name: str, scope: Mapping[str, Any] | None = None
    ) -> dict[Any, int]:
        """Head-count per value of `field_name`, excluding terminated employees."""
        pipeline: list[Document] = [
            {
                "$match": self._scoped(
                    company_id, _and(scope, {"status": {"$ne": EmployeeStatus.TERMINATED.value}})
                )
            },
            {"$group": {"_id": f"${field_name}", "count": {"$sum": 1}}},
        ]
        cursor = await self._collection.aggregate(pipeline)
        return {document["_id"]: document["count"] async for document in cursor}

    async def status_counts(
        self, company_id: ObjectId, scope: Mapping[str, Any] | None = None
    ) -> dict[str, int]:
        pipeline: list[Document] = [
            {"$match": self._scoped(company_id, scope)},
            {"$group": {"_id": "$status", "count": {"$sum": 1}}},
        ]
        cursor = await self._collection.aggregate(pipeline)
        return {str(document["_id"]): document["count"] async for document in cursor}

    async def recent(
        self, company_id: ObjectId, scope: Mapping[str, Any] | None = None, limit: int = 5
    ) -> list[Employee]:
        return await self._find_many(
            self._scoped(company_id, scope), sort=[("created_at", DESCENDING)], limit=limit
        )


class DeviceRepository(TenantRepository[Device]):
    collection_name = "devices"
    model = Device
    indexes = (
        IndexModel([("company_id", ASCENDING), ("employee_id", ASCENDING)], name="company_employee"),
        IndexModel([("company_id", ASCENDING), ("status", ASCENDING)], name="company_status"),
        IndexModel([("employee_id", ASCENDING)], name="employee_id"),
        IndexModel(
            [("enrollment_code_hash", ASCENDING)],
            name="uniq_enrollment_code",
            unique=True,
            partialFilterExpression={"enrollment_code_hash": {"$type": "string"}},
        ),
        IndexModel([("last_seen_at", DESCENDING)], name="last_seen_at"),
        IndexModel([("created_at", DESCENDING)], name="created_at"),
        IndexModel(
            [("company_id", ASCENDING), ("employee_id", ASCENDING), ("fingerprint_hash", ASCENDING)],
            name="company_employee_fingerprint",
        ),
    )

    async def get_for_auth(self, device_id: ObjectId) -> Device | None:
        """Unscoped by design: device credentials identify the tenant (verified against the secret hash)."""
        return await self._find_one({"_id": device_id})

    async def find_by_enrollment_hash(self, code_hash: str) -> Device | None:
        """Unscoped by design: the one-time code itself identifies the tenant."""
        return await self._find_one({"enrollment_code_hash": code_hash, "status": DeviceStatus.PENDING.value})

    async def find_for_fingerprint(
        self, company_id: ObjectId, employee_id: ObjectId, fingerprint_hash: str
    ) -> Device | None:
        return await self._find_one(
            self._scoped(
                company_id,
                {
                    "employee_id": employee_id,
                    "fingerprint_hash": fingerprint_hash,
                    "status": {"$ne": DeviceStatus.REVOKED.value},
                },
            )
        )

    async def latest_by_employee(
        self, company_id: ObjectId, employee_ids: Sequence[ObjectId]
    ) -> dict[ObjectId, Device]:
        """The most recently seen active device for each employee."""
        devices = await self._find_many(
            self._scoped(
                company_id,
                {"employee_id": {"$in": list(employee_ids)}, "status": DeviceStatus.ACTIVE.value},
            ),
            sort=[("last_seen_at", DESCENDING)],
            limit=5000,
        )
        latest: dict[ObjectId, Device] = {}
        for device in devices:
            current = latest.get(device.employee_id)
            if current is None or (device.last_seen_at or device.created_at) > (
                current.last_seen_at or current.created_at
            ):
                latest[device.employee_id] = device
        return latest

    async def list_for_employee(self, company_id: ObjectId, employee_id: ObjectId) -> list[Device]:
        return await self.find_many(company_id, {"employee_id": employee_id})

    async def count_by_employee(
        self, company_id: ObjectId, employee_ids: Sequence[ObjectId]
    ) -> dict[ObjectId, int]:
        pipeline: list[Document] = [
            {
                "$match": self._scoped(
                    company_id, {"employee_id": {"$in": list(employee_ids)}, "status": {"$ne": "revoked"}}
                )
            },
            {"$group": {"_id": "$employee_id", "count": {"$sum": 1}}},
        ]
        cursor = await self._collection.aggregate(pipeline)
        return {document["_id"]: document["count"] async for document in cursor}
