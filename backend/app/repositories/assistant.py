"""Assistant conversations (each person's own; append-only)."""

from __future__ import annotations

from typing import Any

from bson import ObjectId
from pymongo import ASCENDING, DESCENDING, IndexModel

from app.models.assistant import Conversation
from app.repositories.base import TenantRepository
from app.utils.time import utcnow


class ConversationRepository(TenantRepository[Conversation]):
    collection_name = "assistant_conversations"
    model = Conversation
    indexes = (
        IndexModel(
            [("company_id", ASCENDING), ("user_id", ASCENDING), ("updated_at", DESCENDING)],
            name="user_recent",
        ),
        # Conversations are kept for 90 days after their last message.
        IndexModel([("updated_at", ASCENDING)], name="ttl_updated", expireAfterSeconds=90 * 24 * 3600),
    )

    async def for_user(self, company_id: ObjectId, user_id: ObjectId, limit: int = 50) -> list[Conversation]:
        return await self._find_many(
            self._scoped(company_id, {"user_id": user_id}), sort=[("updated_at", DESCENDING)], limit=limit
        )

    async def own(
        self, company_id: ObjectId, user_id: ObjectId, conversation_id: ObjectId
    ) -> Conversation | None:
        return await self._find_one(self._scoped(company_id, {"_id": conversation_id, "user_id": user_id}))

    async def append(
        self,
        company_id: ObjectId,
        conversation_id: ObjectId,
        transcript: list[dict[str, Any]],
        turns: list[dict[str, Any]],
    ) -> None:
        """Append only: earlier messages are never rewritten."""
        update: dict[str, Any] = {"$set": {"updated_at": utcnow()}}
        push: dict[str, Any] = {}
        if transcript:
            push["transcript"] = {"$each": transcript}
        if turns:
            push["turns"] = {"$each": turns}
        if push:
            update["$push"] = push
        await self._collection.update_one(self._scoped(company_id, {"_id": conversation_id}), update)

    async def delete_all(self, company_id: ObjectId, user_id: ObjectId) -> int:
        result = await self._collection.delete_many(self._scoped(company_id, {"user_id": user_id}))
        return result.deleted_count
