"""Notifications, per-user preferences and the one-time event log."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from bson import ObjectId
from pymongo import ASCENDING, DESCENDING, IndexModel, ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.models.notification import AlertEvent, Notification, NotificationPreferences
from app.repositories.base import TenantRepository
from app.utils.time import utcnow

RETENTION = timedelta(days=90)


class NotificationRepository(TenantRepository[Notification]):
    collection_name = "notifications"
    model = Notification
    indexes = (
        IndexModel(
            [("company_id", ASCENDING), ("recipient_user_id", ASCENDING), ("last_occurred_at", DESCENDING)],
            name="recipient_recent",
        ),
        IndexModel(
            [("company_id", ASCENDING), ("recipient_user_id", ASCENDING), ("read_at", ASCENDING)],
            name="recipient_unread",
        ),
        IndexModel(
            [
                ("company_id", ASCENDING),
                ("recipient_user_id", ASCENDING),
                ("type", ASCENDING),
                ("subject_key", ASCENDING),
                ("last_occurred_at", DESCENDING),
            ],
            name="throttle",
        ),
        # Notifications are kept for 90 days.
        IndexModel(
            [("created_at", ASCENDING)], name="ttl_created", expireAfterSeconds=int(RETENTION.total_seconds())
        ),
    )

    async def recent_same(
        self, company_id: ObjectId, user_id: ObjectId, type_: str, subject_key: str, since: datetime
    ) -> Notification | None:
        return await self._find_one(
            self._scoped(
                company_id,
                {
                    "recipient_user_id": user_id,
                    "type": type_,
                    "subject_key": subject_key,
                    "last_occurred_at": {"$gte": since},
                },
            )
        )

    async def fold(
        self, company_id: ObjectId, notification_id: ObjectId, changes: dict[str, Any]
    ) -> Notification | None:
        doc = await self._collection.find_one_and_update(
            self._scoped(company_id, {"_id": notification_id}),
            {"$inc": {"count": 1}, "$set": {**changes, "read_at": None, "updated_at": utcnow()}},
            return_document=ReturnDocument.AFTER,
        )
        return self.model.model_validate(doc) if doc else None

    async def created_since(self, company_id: ObjectId, user_id: ObjectId, since: datetime) -> int:
        return await self._collection.count_documents(
            self._scoped(company_id, {"recipient_user_id": user_id, "created_at": {"$gte": since}})
        )

    async def unread_count(self, company_id: ObjectId, user_id: ObjectId) -> int:
        return await self._collection.count_documents(
            self._scoped(company_id, {"recipient_user_id": user_id, "read_at": None})
        )

    async def page(
        self, company_id: ObjectId, user_id: ObjectId, query: dict[str, Any], skip: int, limit: int
    ) -> tuple[list[Notification], int]:
        scoped = self._scoped(company_id, {"recipient_user_id": user_id, **query})
        items = await self._find_many(scoped, sort=[("last_occurred_at", DESCENDING)], skip=skip, limit=limit)
        return items, await self._collection.count_documents(scoped)

    async def mark(self, company_id: ObjectId, user_id: ObjectId, query: dict[str, Any], read: bool) -> int:
        result = await self._collection.update_many(
            self._scoped(company_id, {"recipient_user_id": user_id, **query}),
            {"$set": {"read_at": utcnow() if read else None, "updated_at": utcnow()}},
        )
        return result.modified_count


class NotificationPreferencesRepository(TenantRepository[NotificationPreferences]):
    collection_name = "notification_preferences"
    model = NotificationPreferences
    indexes = (
        IndexModel([("company_id", ASCENDING), ("user_id", ASCENDING)], name="uniq_user", unique=True),
    )

    async def for_user(self, company_id: ObjectId, user_id: ObjectId) -> NotificationPreferences | None:
        return await self._find_one(self._scoped(company_id, {"user_id": user_id}))

    async def for_users(
        self, company_id: ObjectId, user_ids: list[ObjectId]
    ) -> dict[ObjectId, NotificationPreferences]:
        found = await self._find_many(self._scoped(company_id, {"user_id": {"$in": user_ids}}), limit=10_000)
        return {p.user_id: p for p in found}

    async def save(self, prefs: NotificationPreferences) -> NotificationPreferences:
        now = utcnow()
        doc = await self._collection.find_one_and_update(
            {"company_id": prefs.company_id, "user_id": prefs.user_id},
            {
                "$set": {
                    "types": {k: v.model_dump() for k, v in prefs.types.items()},
                    "throttle_minutes": prefs.throttle_minutes,
                    "updated_at": now,
                },
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return self.model.model_validate(doc)


class AlertEventRepository(TenantRepository[AlertEvent]):
    collection_name = "alert_events"
    model = AlertEvent
    indexes = (
        IndexModel([("company_id", ASCENDING), ("dedupe_key", ASCENDING)], name="uniq_event", unique=True),
        IndexModel([("created_at", ASCENDING)], name="ttl_created", expireAfterSeconds=60 * 60 * 24 * 60),
    )

    async def claim(self, company_id: ObjectId, dedupe_key: str) -> bool:
        """True the first time a key is seen; False for every repeat (across restarts and processes)."""
        try:
            await self.create(company_id, AlertEvent(company_id=company_id, dedupe_key=dedupe_key))
        except DuplicateKeyError:
            return False
        return True
