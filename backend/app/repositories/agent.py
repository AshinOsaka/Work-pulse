"""Repositories for agent-reported data."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any

from bson import ObjectId
from pymongo import ASCENDING, DESCENDING, IndexModel
from pymongo.errors import DuplicateKeyError

from app.models.agent import AgentEvent, WorkSession
from app.repositories.base import TenantRepository

EVENT_RETENTION_SECONDS = 90 * 86_400


#: How far back overlap queries look for *closed* sessions. A closed session that started earlier than this before
#: a period is not counted in it (open sessions are always found). Work sessions are normally a day or less.
MAX_CLOSED_SESSION = timedelta(days=31)


class WorkSessionRepository(TenantRepository[WorkSession]):
    collection_name = "work_sessions"
    model = WorkSession
    indexes = (
        IndexModel(
            [("device_id", ASCENDING), ("client_session_id", ASCENDING)],
            name="uniq_device_session",
            unique=True,
        ),
        IndexModel(
            [("company_id", ASCENDING), ("employee_id", ASCENDING), ("started_at", DESCENDING)],
            name="company_employee_started",
        ),
        IndexModel([("company_id", ASCENDING), ("started_at", DESCENDING)], name="company_started"),
        IndexModel([("company_id", ASCENDING), ("ended_at", ASCENDING)], name="company_ended"),
    )

    async def open_session(self, session: WorkSession) -> bool:
        """Insert a session; False if this client session id was already recorded."""
        try:
            await self.create(session.company_id, session)
        except DuplicateKeyError:
            return False
        return True

    async def close_session(
        self, company_id: ObjectId, device_id: ObjectId, client_session_id: str, changes: dict[str, Any]
    ) -> WorkSession | None:
        return await self._update_one(
            self._scoped(
                company_id, {"device_id": device_id, "client_session_id": client_session_id, "ended_at": None}
            ),
            changes,
        )

    async def record_presence(
        self, company_id: ObjectId, device_id: ObjectId, client_session_id: str, at: datetime, status: str
    ) -> None:
        await self._collection.update_one(
            self._scoped(company_id, {"device_id": device_id, "client_session_id": client_session_id}),
            {"$push": {"presence_changes": {"$each": [{"at": at, "status": status}], "$slice": -5000}}},
        )

    async def get_by_client_id(
        self, company_id: ObjectId, device_id: ObjectId, client_session_id: str
    ) -> WorkSession | None:
        return await self._find_one(
            self._scoped(company_id, {"device_id": device_id, "client_session_id": client_session_id})
        )

    async def overlapping(
        self, company_id: ObjectId, employee_ids: Sequence[ObjectId], start: datetime, end: datetime
    ) -> list[WorkSession]:
        """Sessions that overlap [start, end) — open sessions count until now.

        Both look-ups are bounded (they used to walk each person's entire history): closed sessions are found among
        those started at most `MAX_CLOSED_SESSION` before the range, open ones through the `ended_at` index.
        """
        people = list(employee_ids)
        closed = await self._find_many(
            self._scoped(
                company_id,
                {
                    "employee_id": {"$in": people},
                    "started_at": {"$lt": end, "$gte": start - MAX_CLOSED_SESSION},
                    "ended_at": {"$gt": start},
                },
            ),
            limit=100_000,
        )
        still_open = await self._find_many(
            self._scoped(
                company_id, {"ended_at": None, "employee_id": {"$in": people}, "started_at": {"$lt": end}}
            ),
            limit=100_000,
        )
        return closed + still_open


class AgentEventRepository(TenantRepository[AgentEvent]):
    collection_name = "agent_events"
    model = AgentEvent
    indexes = (
        IndexModel(
            [("device_id", ASCENDING), ("event_id", ASCENDING)], name="uniq_device_event", unique=True
        ),
        IndexModel([("company_id", ASCENDING), ("occurred_at", DESCENDING)], name="company_occurred"),
        IndexModel(
            [("company_id", ASCENDING), ("employee_id", ASCENDING), ("occurred_at", DESCENDING)],
            name="company_employee_occurred",
        ),
        IndexModel(
            [("created_at", ASCENDING)], name="ttl_created_at", expireAfterSeconds=EVENT_RETENTION_SECONDS
        ),
    )

    async def record(self, event: AgentEvent) -> bool:
        """Idempotent insert keyed by (device, client event id). False = duplicate."""
        try:
            await self.create(event.company_id, event)
        except DuplicateKeyError:
            return False
        return True

    async def last_received(self, company_id: ObjectId, device_id: ObjectId) -> datetime | None:
        latest = await self._find_many(
            self._scoped(company_id, {"device_id": device_id}), sort=[("created_at", DESCENDING)], limit=1
        )
        return latest[0].created_at if latest else None
