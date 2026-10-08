from __future__ import annotations

from datetime import datetime

from bson import ObjectId
from pymongo import ASCENDING, DESCENDING, IndexModel, ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.models.security import AuthSession, RateLimitBucket
from app.repositories.base import BaseRepository, TenantRepository
from app.utils.time import utcnow


class AuthSessionRepository(TenantRepository[AuthSession]):
    collection_name = "auth_sessions"
    model = AuthSession
    indexes = (
        IndexModel(
            [("company_id", ASCENDING), ("user_id", ASCENDING), ("last_seen_at", DESCENDING)],
            name="user_recent",
        ),
        # Expired sessions are purged automatically; revoked ones age out the same way.
        IndexModel([("expires_at", ASCENDING)], name="ttl_expires_at", expireAfterSeconds=0),
    )

    async def find_active(self, session_id: ObjectId) -> AuthSession | None:
        """Unscoped by design: the signed access token names the session (and its tenant is checked by the caller)."""
        return await self._find_one({"_id": session_id, "revoked_at": None, "expires_at": {"$gt": utcnow()}})

    async def for_user(self, company_id: ObjectId, user_id: ObjectId) -> list[AuthSession]:
        return await self._find_many(
            self._scoped(
                company_id, {"user_id": user_id, "revoked_at": None, "expires_at": {"$gt": utcnow()}}
            ),
            sort=[("last_seen_at", DESCENDING)],
            limit=100,
        )

    async def touch(
        self, session_id: ObjectId, *, expires_at: datetime, ip: str | None, agent: str | None
    ) -> None:
        now = utcnow()
        await self._collection.update_one(
            {"_id": session_id, "revoked_at": None},
            {
                "$set": {
                    "last_seen_at": now,
                    "updated_at": now,
                    "expires_at": expires_at,
                    "ip_address": ip,
                    "user_agent": agent,
                }
            },
        )

    async def revoke(
        self, company_id: ObjectId, session_id: ObjectId, reason: str, user_id: ObjectId | None = None
    ) -> bool:
        now = utcnow()
        query: dict[str, object] = {"_id": session_id, "revoked_at": None}
        if user_id is not None:
            query["user_id"] = user_id
        result = await self._collection.update_one(
            self._scoped(company_id, query),
            {"$set": {"revoked_at": now, "revoked_reason": reason, "updated_at": now}},
        )
        return result.modified_count == 1

    async def revoke_unscoped(self, session_id: ObjectId, reason: str) -> None:
        """Token-theft response: the refresh token names the session, before any tenant context exists."""
        now = utcnow()
        await self._collection.update_one(
            {"_id": session_id, "revoked_at": None},
            {"$set": {"revoked_at": now, "revoked_reason": reason, "updated_at": now}},
        )

    async def revoke_all(
        self, company_id: ObjectId, user_id: ObjectId, reason: str, keep: ObjectId | None = None
    ) -> list[ObjectId]:
        query: dict[str, object] = {"user_id": user_id, "revoked_at": None}
        if keep is not None:
            query["_id"] = {"$ne": keep}
        ids = [d["_id"] async for d in self._collection.find(self._scoped(company_id, query), {"_id": 1})]
        if ids:
            now = utcnow()
            await self._collection.update_many(
                {"_id": {"$in": ids}},
                {"$set": {"revoked_at": now, "revoked_reason": reason, "updated_at": now}},
            )
        return ids


class RateLimitRepository(BaseRepository[RateLimitBucket]):
    collection_name = "rate_limits"
    model = RateLimitBucket
    indexes = (
        IndexModel([("key", ASCENDING)], name="uniq_key", unique=True),
        IndexModel([("expires_at", ASCENDING)], name="ttl_expires_at", expireAfterSeconds=0),
    )

    async def increment(self, key: str, expires_at: datetime) -> int:
        update = {"$inc": {"count": 1}, "$setOnInsert": {"expires_at": expires_at, "created_at": utcnow()}}
        try:
            document = await self._collection.find_one_and_update(
                {"key": key}, update, upsert=True, return_document=ReturnDocument.AFTER
            )
        except DuplicateKeyError:  # two first hits raced on the upsert; the second one now updates
            document = await self._collection.find_one_and_update(
                {"key": key}, update, return_document=ReturnDocument.AFTER
            )
        return int(document["count"]) if document else 1

    async def count(self, key: str) -> int:
        document = await self._collection.find_one(
            {"key": key, "expires_at": {"$gt": utcnow()}}, {"count": 1}
        )
        return int(document["count"]) if document else 0

    async def clear(self, key: str) -> None:
        await self._collection.delete_one({"key": key})
