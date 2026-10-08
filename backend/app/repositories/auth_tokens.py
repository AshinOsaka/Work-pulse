from __future__ import annotations

from typing import TypeVar

from bson import ObjectId
from pymongo import ASCENDING, DESCENDING, IndexModel

from app.models.auth_tokens import (
    EmailVerificationToken,
    InvitationToken,
    OneTimeToken,
    PasswordResetToken,
    RefreshToken,
)
from app.repositories.base import TenantRepository
from app.utils.time import utcnow

OneTimeTokenT = TypeVar("OneTimeTokenT", bound=OneTimeToken)


def _token_indexes() -> tuple[IndexModel, ...]:
    return (
        IndexModel([("token_hash", ASCENDING)], name="uniq_token_hash", unique=True),
        IndexModel([("company_id", ASCENDING), ("user_id", ASCENDING)], name="company_user"),
        IndexModel([("user_id", ASCENDING)], name="user_id"),
        # MongoDB purges documents automatically once `expires_at` passes.
        IndexModel([("expires_at", ASCENDING)], name="ttl_expires_at", expireAfterSeconds=0),
        IndexModel([("created_at", DESCENDING)], name="created_at"),
    )


class RefreshTokenRepository(TenantRepository[RefreshToken]):
    collection_name = "refresh_tokens"
    model = RefreshToken
    indexes = (*_token_indexes(), IndexModel([("family_id", ASCENDING)], name="family_id"))

    async def find_by_hash(self, token_hash: str) -> RefreshToken | None:
        """Unscoped by design: the token itself identifies the tenant."""
        return await self._find_one({"token_hash": token_hash})

    async def consume(self, token_id: ObjectId) -> bool:
        """Atomically mark a token as rotated. False if it was already used."""
        now = utcnow()
        result = await self._collection.update_one(
            {"_id": token_id, "revoked_at": None},
            {
                "$set": {
                    "revoked_at": now,
                    "revoked_reason": "rotated",
                    "last_used_at": now,
                    "updated_at": now,
                }
            },
        )
        return result.modified_count == 1

    async def revoke_by_hash(self, token_hash: str, reason: str) -> bool:
        now = utcnow()
        result = await self._collection.update_one(
            {"token_hash": token_hash, "revoked_at": None},
            {"$set": {"revoked_at": now, "revoked_reason": reason, "updated_at": now}},
        )
        return result.modified_count == 1

    async def revoke_family(self, family_id: str, reason: str) -> int:
        now = utcnow()
        result = await self._collection.update_many(
            {"family_id": family_id, "revoked_at": None},
            {"$set": {"revoked_at": now, "revoked_reason": reason, "updated_at": now}},
        )
        return result.modified_count

    async def revoke_all_for_user(
        self, company_id: ObjectId, user_id: ObjectId, reason: str, keep_family: str | None = None
    ) -> int:
        now = utcnow()
        query: dict[str, object] = {"user_id": user_id, "revoked_at": None}
        if keep_family is not None:
            query["family_id"] = {"$ne": keep_family}
        result = await self._collection.update_many(
            self._scoped(company_id, query),
            {"$set": {"revoked_at": now, "revoked_reason": reason, "updated_at": now}},
        )
        return result.modified_count


class _OneTimeTokenRepository(TenantRepository[OneTimeTokenT]):
    async def find_valid_by_hash(self, token_hash: str) -> OneTimeTokenT | None:
        return await self._find_one(
            {"token_hash": token_hash, "used_at": None, "expires_at": {"$gt": utcnow()}}
        )

    async def mark_used(self, token_id: ObjectId) -> bool:
        now = utcnow()
        result = await self._collection.update_one(
            {"_id": token_id, "used_at": None}, {"$set": {"used_at": now, "updated_at": now}}
        )
        return result.modified_count == 1

    async def invalidate_for_user(self, company_id: ObjectId, user_id: ObjectId) -> None:
        now = utcnow()
        await self._collection.update_many(
            self._scoped(company_id, {"user_id": user_id, "used_at": None}),
            {"$set": {"used_at": now, "updated_at": now}},
        )


class PasswordResetTokenRepository(_OneTimeTokenRepository[PasswordResetToken]):
    collection_name = "password_reset_tokens"
    model = PasswordResetToken
    indexes = _token_indexes()


class EmailVerificationTokenRepository(_OneTimeTokenRepository[EmailVerificationToken]):
    collection_name = "email_verification_tokens"
    model = EmailVerificationToken
    indexes = _token_indexes()


class InvitationTokenRepository(_OneTimeTokenRepository[InvitationToken]):
    collection_name = "invitation_tokens"
    model = InvitationToken
    indexes = _token_indexes()
