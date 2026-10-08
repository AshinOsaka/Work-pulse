"""Repository base classes.

`TenantRepository` is the multi-tenancy guard rail: every public method takes a
`company_id` and injects it into the query, so tenant-owned data cannot be read
or written across companies by accident. Unscoped look-ups must be added as
explicit, clearly named methods on concrete repositories (e.g. login by e-mail).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, ClassVar, Generic, TypeVar

from bson import ObjectId
from pymongo import IndexModel, ReturnDocument
from pymongo.asynchronous.collection import AsyncCollection
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.collation import Collation
from pymongo.errors import OperationFailure

from app.models.base import MongoModel, TenantModel
from app.utils.time import utcnow

logger = logging.getLogger(__name__)

Document = dict[str, Any]
SortSpec = Sequence[tuple[str, int]]

ModelT = TypeVar("ModelT", bound=MongoModel)
TenantModelT = TypeVar("TenantModelT", bound=TenantModel)

_IMMUTABLE_FIELDS = frozenset({"_id", "id", "company_id", "created_at"})

# Case-insensitive collation for human-entered names (sorting and uniqueness).
CASE_INSENSITIVE = Collation(locale="en", strength=2)

#: MongoDB error codes for "an index with this name/keys exists with different options".
_INDEX_CONFLICTS = {85, 86}


def _same_option(current: Any, wanted: Any) -> bool:
    """Server-reported options include defaults (e.g. a full collation), so dicts compare as subsets."""
    if isinstance(wanted, Mapping) and isinstance(current, Mapping):
        return all(_same_option(current.get(k), v) for k, v in wanted.items())
    return bool(current == wanted)


async def sync_indexes(collection: AsyncCollection[Document], indexes: Sequence[IndexModel]) -> None:
    """Create indexes, and bring existing ones in line when a release changed their definition.

    `createIndexes` fails when an index of the same name exists with other options, which would stop the API from
    starting after an upgrade. A changed TTL is applied in place (`collMod`, no rebuild); any other change drops and
    rebuilds that one index.
    """
    try:
        await collection.create_indexes(list(indexes))
        return
    except OperationFailure as exc:
        if exc.code not in _INDEX_CONFLICTS:
            raise
    existing = await collection.index_information()
    for model in indexes:
        spec = model.document
        name = spec["name"]
        current = existing.get(name)
        if current is not None:
            keys = list(spec["key"].items())
            ttl, current_ttl = spec.get("expireAfterSeconds"), current.get("expireAfterSeconds")
            others = {k: v for k, v in spec.items() if k not in ("key", "name", "expireAfterSeconds")}
            same_others = all(_same_option(current.get(k), v) for k, v in others.items())
            if current["key"] == keys and same_others and ttl == current_ttl:
                continue
            if current["key"] == keys and same_others and ttl is not None and current_ttl is not None:
                logger.warning("Index %s.%s: TTL %ss -> %ss", collection.name, name, current_ttl, ttl)
                await collection.database.command(
                    {"collMod": collection.name, "index": {"name": name, "expireAfterSeconds": ttl}}
                )
                continue
            logger.warning("Index %s.%s changed definition; rebuilding it", collection.name, name)
            await collection.drop_index(name)
        await collection.create_indexes([model])


class BaseRepository(Generic[ModelT]):
    collection_name: ClassVar[str]
    model: type[ModelT]
    indexes: ClassVar[tuple[IndexModel, ...]] = ()
    # Index names from earlier releases that must be dropped (e.g. options changed).
    obsolete_indexes: ClassVar[tuple[str, ...]] = ()

    def __init__(self, db: AsyncDatabase[Document]) -> None:
        self._db = db
        self._collection: AsyncCollection[Document] = db[self.collection_name]

    @classmethod
    async def ensure_indexes(cls, db: AsyncDatabase[Document]) -> None:
        collection = db[cls.collection_name]
        if cls.obsolete_indexes:
            existing = await collection.index_information()
            for name in cls.obsolete_indexes:
                if name in existing:
                    await collection.drop_index(name)
        if cls.indexes:
            await sync_indexes(collection, cls.indexes)

    def _to_model(self, document: Document) -> ModelT:
        return self.model.from_document(document)

    async def _find_one(self, query: Mapping[str, Any]) -> ModelT | None:
        document = await self._collection.find_one(query)
        return self._to_model(document) if document else None

    async def _find_many(
        self,
        query: Mapping[str, Any],
        *,
        sort: SortSpec | None = None,
        skip: int = 0,
        limit: int = 100,
        collation: Collation | None = None,
    ) -> list[ModelT]:
        cursor = self._collection.find(query, collation=collation)
        if sort:
            cursor = cursor.sort(list(sort))
        cursor = cursor.skip(skip).limit(limit)
        return [self._to_model(document) async for document in cursor]

    async def _insert(self, entity: ModelT) -> ModelT:
        await self._collection.insert_one(entity.to_document())
        return entity

    async def _update_one(self, query: Mapping[str, Any], changes: Mapping[str, Any]) -> ModelT | None:
        safe_changes = {k: v for k, v in changes.items() if k not in _IMMUTABLE_FIELDS}
        document = await self._collection.find_one_and_update(
            query,
            {"$set": {**safe_changes, "updated_at": utcnow()}},
            return_document=ReturnDocument.AFTER,
        )
        return self._to_model(document) if document else None

    async def _count(self, query: Mapping[str, Any], collation: Collation | None = None) -> int:
        if collation is None:
            return await self._collection.count_documents(query)
        return await self._collection.count_documents(query, collation=collation)

    async def _delete_one(self, query: Mapping[str, Any]) -> bool:
        result = await self._collection.delete_one(query)
        return result.deleted_count == 1


class GlobalRepository(BaseRepository[ModelT]):
    """Repository for platform-level (non tenant-owned) collections."""

    async def get_by_id(self, entity_id: ObjectId) -> ModelT | None:
        return await self._find_one({"_id": entity_id})

    async def create(self, entity: ModelT) -> ModelT:
        return await self._insert(entity)

    async def update_by_id(self, entity_id: ObjectId, changes: Mapping[str, Any]) -> ModelT | None:
        return await self._update_one({"_id": entity_id}, changes)

    async def delete_by_id(self, entity_id: ObjectId) -> bool:
        return await self._delete_one({"_id": entity_id})


class TenantRepository(BaseRepository[TenantModelT]):
    """Repository for tenant-owned collections; all access is company scoped."""

    @staticmethod
    def _scoped(company_id: ObjectId, query: Mapping[str, Any] | None = None) -> Document:
        return {**(query or {}), "company_id": company_id}

    async def get_by_id(self, company_id: ObjectId, entity_id: ObjectId) -> TenantModelT | None:
        return await self._find_one(self._scoped(company_id, {"_id": entity_id}))

    async def find_many(
        self,
        company_id: ObjectId,
        query: Mapping[str, Any] | None = None,
        *,
        sort: SortSpec | None = (("created_at", -1),),
        skip: int = 0,
        limit: int = 100,
    ) -> list[TenantModelT]:
        return await self._find_many(self._scoped(company_id, query), sort=sort, skip=skip, limit=limit)

    async def find_by_ids(
        self, company_id: ObjectId, ids: Iterable[ObjectId]
    ) -> dict[ObjectId, TenantModelT]:
        """Batch look-up keyed by id; unknown or foreign ids are silently omitted."""
        unique = list({i for i in ids if i is not None})
        if not unique:
            return {}
        found = await self._find_many(self._scoped(company_id, {"_id": {"$in": unique}}), limit=len(unique))
        return {entity.id: entity for entity in found}

    async def exists(self, company_id: ObjectId, query: Mapping[str, Any]) -> bool:
        return (
            await self._collection.find_one(self._scoped(company_id, query), projection={"_id": 1})
            is not None
        )

    async def count(self, company_id: ObjectId, query: Mapping[str, Any] | None = None) -> int:
        return await self._count(self._scoped(company_id, query))

    async def create(self, company_id: ObjectId, entity: TenantModelT) -> TenantModelT:
        if entity.company_id != company_id:
            raise ValueError("Entity company_id does not match the tenant scope")
        return await self._insert(entity)

    async def update_by_id(
        self, company_id: ObjectId, entity_id: ObjectId, changes: Mapping[str, Any]
    ) -> TenantModelT | None:
        return await self._update_one(self._scoped(company_id, {"_id": entity_id}), changes)

    async def set_fields(self, company_id: ObjectId, entity_id: ObjectId, changes: Mapping[str, Any]) -> bool:
        """Like `update_by_id` without reading the document back (one round trip less on hot paths)."""
        result = await self._collection.update_one(
            self._scoped(company_id, {"_id": entity_id}), {"$set": {**changes, "updated_at": utcnow()}}
        )
        return result.matched_count == 1

    async def delete_by_id(self, company_id: ObjectId, entity_id: ObjectId) -> bool:
        return await self._delete_one(self._scoped(company_id, {"_id": entity_id}))
