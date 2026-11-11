from __future__ import annotations

from bson import ObjectId
from pymongo import ASCENDING, DESCENDING, IndexModel

from app.models.role import PermissionDocument, RoleDocument
from app.repositories.base import BaseRepository, GlobalRepository
from app.utils.time import utcnow


class RoleRepository(GlobalRepository[RoleDocument]):
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
        """System roles and the company's roles; a company's version of a built-in role replaces the system one."""
        docs = await self._find_many(
            {"company_id": {"$in": [None, company_id]}}, sort=[("level", DESCENDING)]
        )
        own = {d.key for d in docs if d.company_id == company_id}
        return [d for d in docs if d.company_id == company_id or d.key not in own]

    async def get_effective(self, company_id: ObjectId, key: str) -> RoleDocument | None:
        """Resolve a role key visible to the company: a company role wins over a system role of the same key."""
        docs = await self._find_many({"company_id": {"$in": [None, company_id]}, "key": key})
        docs.sort(key=lambda d: 0 if d.company_id == company_id else 1)
        return docs[0] if docs else None

    async def get_company_role(self, company_id: ObjectId, key: str) -> RoleDocument | None:
        return await self._find_one({"company_id": company_id, "key": key})

    async def key_taken(self, company_id: ObjectId, key: str) -> bool:
        return await self._count({"company_id": {"$in": [None, company_id]}, "key": key}) > 0

    async def update_company_role(
        self, company_id: ObjectId, key: str, changes: dict[str, object]
    ) -> RoleDocument | None:
        role = await self.get_company_role(company_id, key)
        if role is None:
            return None
        return await self.update_by_id(role.id, changes)

    async def delete_company_role(self, company_id: ObjectId, key: str) -> bool:
        role = await self.get_company_role(company_id, key)
        if role is None:
            return False
        return await self.delete_by_id(role.id)


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
