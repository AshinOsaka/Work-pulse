from __future__ import annotations

import re

from bson import ObjectId
from pymongo import ASCENDING, DESCENDING, IndexModel

from app.models.user import User, UserStatus
from app.repositories.base import CASE_INSENSITIVE, TenantRepository
from app.utils.time import utcnow


class UserRepository(TenantRepository[User]):
    collection_name = "users"
    model = User
    indexes = (
        IndexModel([("email", ASCENDING)], name="uniq_email", unique=True),
        IndexModel([("company_id", ASCENDING), ("status", ASCENDING)], name="company_status"),
        IndexModel([("company_id", ASCENDING), ("role", ASCENDING)], name="company_role"),
        IndexModel([("company_id", ASCENDING), ("created_at", DESCENDING)], name="company_created_at"),
        IndexModel([("employee_id", ASCENDING)], name="employee_id", sparse=True),
        IndexModel([("created_at", DESCENDING)], name="created_at"),
        IndexModel(
            [("company_id", ASCENDING), ("full_name", ASCENDING)],
            name="company_full_name_ci",
            collation=CASE_INSENSITIVE,
        ),
    )

    async def find_by_email_for_auth(self, email: str) -> User | None:
        """Unscoped by design: e-mail is globally unique and sign-in precedes tenant resolution."""
        return await self._find_one({"email": email})

    async def email_exists(self, email: str) -> bool:
        return await self._count({"email": email}) > 0

    async def record_login(self, company_id: ObjectId, user_id: ObjectId) -> User | None:
        return await self.update_by_id(company_id, user_id, {"last_login_at": utcnow()})

    async def search(
        self,
        company_id: ObjectId,
        *,
        search: str | None = None,
        role: str | None = None,
        skip: int = 0,
        limit: int = 25,
    ) -> tuple[list[User], int]:
        clauses: list[dict[str, object]] = []
        if search:
            pattern = {"$regex": re.escape(search.strip()), "$options": "i"}
            clauses.append({"$or": [{"full_name": pattern}, {"email": pattern}]})
        if role:
            clauses.append({"role": role})
        query = self._scoped(company_id, {"$and": clauses} if clauses else None)
        items = await self._find_many(
            query,
            sort=[("full_name", ASCENDING), ("_id", ASCENDING)],
            skip=skip,
            limit=limit,
            collation=CASE_INSENSITIVE,
        )
        return items, await self._count(query, collation=CASE_INSENSITIVE)

    async def count_active_with_role(self, company_id: ObjectId, role: str) -> int:
        return await self.count(company_id, {"role": role, "status": UserStatus.ACTIVE.value})

    async def set_mfa_step(
        self, company_id: ObjectId, user_id: ObjectId, step: int, previous: int | None
    ) -> bool:
        """Record the accepted time step only if nobody else used a code meanwhile (prevents replay races)."""
        result = await self._collection.update_one(
            self._scoped(company_id, {"_id": user_id, "mfa_last_step": previous}),
            {"$set": {"mfa_last_step": step, "updated_at": utcnow()}},
        )
        return result.modified_count == 1

    async def use_recovery_code(self, company_id: ObjectId, user_id: ObjectId, code_hash: str) -> bool:
        """Atomically remove a recovery code; False if it was already used."""
        result = await self._collection.update_one(
            self._scoped(company_id, {"_id": user_id, "mfa_recovery_codes": code_hash}),
            {"$pull": {"mfa_recovery_codes": code_hash}, "$set": {"updated_at": utcnow()}},
        )
        return result.modified_count == 1
