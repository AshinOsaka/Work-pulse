"""Finalise-first activity retention.

Each sweep, one process in the cluster (lease) does two things per workspace, in this order:

1. **Finalise** the recent settled days into the durable ``daily_summaries`` (time, categories, focus,
   switching, customer time). This is the permanent system of record for long-horizon reports.
2. **Purge** raw ``activity_segments`` older than ``activity_raw_retention_hours`` — but only for the exact
   (employee, local day) pairs that are already finalised. Raw data is therefore never deleted before it has
   been summarised, so focus and switching history is preserved even though raw segments are short-lived.

Rollups (``activity_daily``, ``website_daily``) and work sessions are kept regardless; they are small and
drive the category and time figures directly. A long backstop TTL on the raw collection still removes any
ancient data this sweep's window does not reach.

Runs in the background worker (see ``app.worker``), never in request handling.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Callable
from datetime import timedelta
from typing import Any
from zoneinfo import ZoneInfo

from pymongo.asynchronous.database import AsyncDatabase

from app.core.broker import Broker
from app.core.config import Settings
from app.models.company import Company, CompanyStatus
from app.models.organization import EmployeeStatus
from app.repositories.activity import ActivitySegmentRepository
from app.repositories.company import CompanyRepository
from app.repositories.organization import EmployeeRepository
from app.services.productivity.engine import day_bounds
from app.services.productivity.service import ProductivityService
from app.services.productivity.summaries import DailySummaryRepository
from app.utils.time import utcnow

logger = logging.getLogger(__name__)

CHUNK = 50
#: Days older than the retention window that the purge still scans back to, before the backstop TTL takes over.
PURGE_SCAN_MARGIN_DAYS = 7


class ActivityFinalizer:
    def __init__(
        self,
        db: AsyncDatabase[dict[str, Any]],
        settings: Settings,
        broker: Broker,
        build_service: Callable[[], ProductivityService],
    ) -> None:
        self._db = db
        self._settings = settings
        self._broker = broker
        self._build = build_service
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop(), name="activity-finalizer")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _loop(self) -> None:
        interval = self._settings.activity_retention_sweep_seconds
        while True:
            try:
                if await self._broker.lease("activity-finalizer", interval * 3):
                    await self.sweep()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Activity finalise/purge sweep failed; will retry")
            await asyncio.sleep(interval)

    async def sweep(self) -> tuple[int, int]:
        """Finalise recent settled days and purge finalised raw data. Returns (summaries, segments deleted)."""
        started = time.monotonic()
        service = self._build()
        companies = CompanyRepository(self._db)
        summaries = DailySummaryRepository(self._db)
        segments = ActivitySegmentRepository(self._db)
        employees_repo = EmployeeRepository(self._db)
        finalized_total = 0
        purged_total = 0
        async for doc in self._db[CompanyRepository.collection_name].find(
            {"status": {"$ne": CompanyStatus.SUSPENDED}}, {"_id": 1}
        ):
            company = await companies.get_by_id(doc["_id"])
            if company is None:
                continue
            ids = await employees_repo.ids_matching(
                company.id, {"status": {"$ne": EmployeeStatus.TERMINATED}}
            )
            if not ids:
                continue
            people = list((await employees_repo.find_by_ids(company.id, ids)).values())
            tz = ZoneInfo(company.timezone)
            today = utcnow().astimezone(tz).date()
            lookback = self._settings.activity_finalize_lookback_days
            for i in range(0, len(people), CHUNK):
                finalized_total += await service.finalize(
                    company, people[i : i + CHUNK], today - timedelta(days=lookback), today - timedelta(days=1)
                )
                await asyncio.sleep(0)
            if self._settings.activity_raw_purge_enabled:
                purged_total += await self._purge(company, ids, summaries, segments, today, tz)
        logger.info(
            "Activity retention: finalised %d summaries, purged %d raw segment(s) in %.1fs",
            finalized_total,
            purged_total,
            time.monotonic() - started,
        )
        return finalized_total, purged_total

    async def _purge(
        self,
        company: Company,
        employee_ids: list[Any],
        summaries: DailySummaryRepository,
        segments: ActivitySegmentRepository,
        today: Any,
        tz: ZoneInfo,
    ) -> int:
        cutoff = utcnow() - timedelta(hours=self._settings.activity_raw_retention_hours)
        scan_from = self._settings.activity_finalize_lookback_days + PURGE_SCAN_MARGIN_DAYS
        purged = 0
        for offset in range(1, scan_from + 1):
            day = today - timedelta(days=offset)
            lo, hi = day_bounds(day, tz)
            if hi > cutoff:
                continue  # the day is not yet fully past the retention window; keep its raw segments
            finalized = await summaries.finalized_employees_on(company.id, day, employee_ids)
            if finalized:
                purged += await segments.delete_range(company.id, list(finalized), lo, hi)
            await asyncio.sleep(0)
        return purged
