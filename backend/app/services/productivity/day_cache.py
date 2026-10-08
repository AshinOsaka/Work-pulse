"""Per person, per day results of the expensive part of productivity analysis, reused across requests.

Classifying usage against the rules and finding focus sessions means reading every activity segment. For a team
view over a week at 1,000 people that is ~200,000 documents per request. The result for a *past* day only changes
when the rules that apply to the person change, or when late data arrives (the agent's offline queue), so it is
cached:

* **key:** employee, local day, and a fingerprint of the rules that apply to the person (`RuleBook.fingerprint`).
  Changing a rule, a work profile, or someone's team or role changes the fingerprint, so stale entries are simply
  never read again (and expire).
* **past days:** valid until invalidated; ingestion invalidates the days a late upload touched.
* **today:** valid for `TODAY_TTL` (data keeps arriving), then recomputed.

Entries are derived data: deleting the whole collection is always safe.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

from bson import ObjectId
from pymongo import ASCENDING, IndexModel, UpdateMany
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import BulkWriteError

from app.repositories.base import BaseRepository, Document
from app.services.productivity.engine import FocusSession, UsageItem
from app.utils.time import utcnow

TODAY_TTL = timedelta(minutes=2)
#: Unused entries disappear after this long (fingerprints that changed, people who left).
RETENTION_SECONDS = 45 * 86_400


@dataclass
class DayResult:
    """Everything `_compute` needs for one person and day beyond time accounting."""

    productive: float = 0.0
    neutral: float = 0.0
    unproductive: float = 0.0
    unclassified: float = 0.0
    items: list[UsageItem] = field(default_factory=list)
    focus: list[FocusSession] = field(default_factory=list)
    focus_count: int = 0
    focus_seconds: float = 0.0
    longest_focus_seconds: float = 0.0
    context_switches: int = 0
    #: Focus and switching need segments; results computed without them carry only categories and usage.
    with_focus: bool = True
    #: Work, active, idle, extended idle and away seconds, once the day is settled (past, no open session).
    time: tuple[float, float, float, float, float] | None = None

    def to_document(self) -> dict[str, Any]:
        return {
            "productive": self.productive,
            "neutral": self.neutral,
            "unproductive": self.unproductive,
            "unclassified": self.unclassified,
            "items": [
                [i.kind, i.key, i.name, round(i.seconds, 2), i.category, i.rule_scope, i.rule_pattern]
                for i in self.items
            ],
            "focus": [[f.start, f.end, round(f.productive_seconds, 2), f.apps] for f in self.focus],
            "focus_count": self.focus_count,
            "focus_seconds": self.focus_seconds,
            "longest_focus_seconds": self.longest_focus_seconds,
            "context_switches": self.context_switches,
            "with_focus": self.with_focus,
            "time": list(self.time) if self.time is not None else None,
        }

    @classmethod
    def from_document(cls, doc: Document) -> DayResult:
        return cls(
            productive=doc["productive"],
            neutral=doc["neutral"],
            unproductive=doc["unproductive"],
            unclassified=doc["unclassified"],
            items=[UsageItem(*row) for row in doc["items"]],
            focus=[FocusSession(_utc(s), _utc(e), p, dict(apps)) for s, e, p, apps in doc["focus"]],
            focus_count=doc["focus_count"],
            focus_seconds=doc["focus_seconds"],
            longest_focus_seconds=doc["longest_focus_seconds"],
            context_switches=doc["context_switches"],
            with_focus=doc.get("with_focus", True),
            time=tuple(doc["time"]) if doc.get("time") else None,
        )


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


class ProductivityDayRepository(BaseRepository[Any]):
    collection_name = "productivity_daily"
    indexes = (
        IndexModel(
            [("company_id", ASCENDING), ("employee_id", ASCENDING), ("day", ASCENDING), ("fp", ASCENDING)],
            name="uniq_company_employee_day_fp",
            unique=True,
        ),
        IndexModel(
            [("computed_at", ASCENDING)], name="ttl_computed_at", expireAfterSeconds=RETENTION_SECONDS
        ),
    )

    def __init__(self, db: AsyncDatabase[Document]) -> None:
        self._db = db
        self._collection = db[self.collection_name]

    async def load(
        self,
        company_id: ObjectId,
        wanted: dict[ObjectId, str],
        days: list[date],
        today: date,
        *,
        need_focus: bool,
    ) -> dict[tuple[ObjectId, date], DayResult]:
        """Valid entries for these people (with their current fingerprint) and days."""
        if not wanted or not days:
            return {}
        fresh_after = utcnow() - TODAY_TTL
        found: dict[tuple[ObjectId, date], DayResult] = {}
        cursor = self._collection.find(
            {
                "company_id": company_id,
                "employee_id": {"$in": list(wanted)},
                "day": {"$gte": days[0].isoformat(), "$lte": days[-1].isoformat()},
            },
            {"_id": 0, "created_at": 0, "updated_at": 0},
        )
        async for doc in cursor:
            if doc["fp"] != wanted.get(doc["employee_id"]):
                continue
            day = date.fromisoformat(doc["day"])
            if day >= today and _utc(doc["computed_at"]) < fresh_after:
                continue
            if need_focus and not doc.get("with_focus", True):
                continue
            found[(doc["employee_id"], day)] = DayResult.from_document(doc)
        return found

    async def store(self, company_id: ObjectId, rows: list[tuple[ObjectId, date, str, DayResult]]) -> None:
        """Replace these entries: one bulk delete and one bulk insert (14,000 upserts took ~10 s)."""
        if not rows:
            return
        now = utcnow()
        employees = list({emp for emp, _, _, _ in rows})
        days = sorted({day.isoformat() for _, day, _, _ in rows})
        fps = list({fp for _, _, fp, _ in rows})
        await self._collection.delete_many(
            {
                "company_id": company_id,
                "employee_id": {"$in": employees},
                "day": {"$in": days},
                "fp": {"$in": fps},
            }
        )
        documents = [
            {
                "company_id": company_id,
                "employee_id": emp,
                "day": day.isoformat(),
                "fp": fp,
                **result.to_document(),
                "computed_at": now,
            }
            for emp, day, fp, result in rows
        ]
        try:
            await self._collection.insert_many(documents, ordered=False)
        except (
            BulkWriteError
        ) as exc:  # a concurrent request stored the same entries first: theirs are as good
            if any(e.get("code") != 11000 for e in exc.details.get("writeErrors", [])):
                raise

    async def store_time(
        self,
        company_id: ObjectId,
        rows: list[tuple[ObjectId, date, tuple[float, float, float, float, float]]],
    ) -> None:
        """Time accounting doesn't depend on the rules, so it is attached to every fingerprint's entry."""
        if not rows:
            return
        await self._collection.bulk_write(
            [
                UpdateMany(
                    {"company_id": company_id, "employee_id": emp, "day": day.isoformat()},
                    {"$set": {"time": [round(v, 2) for v in value]}},
                )
                for emp, day, value in rows
            ],
            ordered=False,
        )

    async def invalidate(self, company_id: ObjectId, employee_id: ObjectId, days: set[str]) -> None:
        """Late data arrived for these days: their results must be recomputed."""
        if days:
            await self._collection.delete_many(
                {"company_id": company_id, "employee_id": employee_id, "day": {"$in": sorted(days)}}
            )


def stale_past_days(days: set[str], today: date) -> set[str]:
    """Only past days need invalidating; today's entries are short-lived anyway."""
    return {d for d in days if d < today.isoformat()}
