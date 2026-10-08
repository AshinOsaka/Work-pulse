from __future__ import annotations

from bson import ObjectId
from pymongo import ASCENDING, DESCENDING, IndexModel

from app.models.role import PermissionDocument, RoleDocument
from app.repositories.base import BaseRepository
from app.utils.time import utcnow


class RoleRepository(BaseRepository[RoleDocument]):
    """System roles have `company_id=None`; custom roles (future) carry a company_id."""

    collection_name = "roles"
    model = RoleDocument
    indexes = (
        IndexModel([("company_id", ASCENDING), ("key", ASCENDING)], name="uniq_company_key", unique=True),
        IndexModel([("is_system", ASCENDING)], name="is_system"),
    )

    async def upsert_system_role(self, role: RoleDocument) -> None:
        fields = role.model_dump(by_alias=True, exclude={"id", "created_at", "company_id"})
        fields["updated_at"] = utcnow()
        await self._collection.update_one(
            {"company_id": None, "key": role.key},
            {"$set": fields, "$setOnInsert": {"_id": role.id, "created_at": role.created_at}},
            upsert=True,
        )

    async def list_for_company(self, company_id: ObjectId) -> list[RoleDocument]:
        return await self._find_many(
            {"company_id": {"$in": [None, company_id]}}, sort=[("level", DESCENDING)]
        )


class PermissionRepository(BaseRepository[PermissionDocument]):
    collection_name = "permissions"
    model = PermissionDocument
    indexes = (IndexModel([("key", ASCENDING)], name="uniq_key", unique=True),)

    async def upsert(self, permission: PermissionDocument) -> None:
        fields = permission.model_dump(by_alias=True, exclude={"id", "created_at"})
        fields["updated_at"] = utcnow()
        await self._collection.update_one(
            {"key": permission.key},
            {"$set": fields, "$setOnInsert": {"_id": permission.id, "created_at": permission.created_at}},
            upsert=True,
        )

    async def list_all(self) -> list[PermissionDocument]:
        return await self._find_many({}, sort=[("category", ASCENDING), ("key", ASCENDING)], limit=500)
