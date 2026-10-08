"""Keeps the productivity day cache warm, so people rarely wait for a cold computation.

Every `productivity_warm_seconds`, one process in the cluster (lease) walks every workspace and computes the past
`WARM_DAYS` days for everyone, in small chunks that yield to other work in between. On a warm cache this is only
cache reads; after midnight, a rule change or late uploads, it recomputes what changed before anyone opens a report.

Runs in the background worker process (see `app.worker`), never in request handling.
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
from app.models.company import CompanyStatus
from app.models.organization import EmployeeStatus
from app.repositories.company import CompanyRepository
from app.repositories.organization import EmployeeRepository
from app.services.productivity.service import ProductivityService
from app.utils.time import utcnow

logger = logging.getLogger(__name__)

#: Covers the longest default views (30-day trend, previous-period comparisons).
WARM_DAYS = 31
CHUNK = 50


class ProductivityWarmer:
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
        self._task = asyncio.create_task(self._loop(), name="productivity-warmer")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _loop(self) -> None:
        interval = self._settings.productivity_warm_seconds
        while True:
            try:
                if await self._broker.lease("productivity-warmer", interval * 3):
                    await self.warm_all()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Productivity cache warm-up failed; will retry")
            await asyncio.sleep(interval)

    async def warm_all(self) -> int:
        """Returns how many person-periods were processed."""
        started = time.monotonic()
        service = self._build()
        companies = CompanyRepository(self._db)
        employees = EmployeeRepository(self._db)
        processed = 0
        async for doc in self._db[CompanyRepository.collection_name].find(
            {"status": {"$ne": CompanyStatus.SUSPENDED}}, {"_id": 1}
        ):
            company = await companies.get_by_id(doc["_id"])
            if company is None:
                continue
            today = utcnow().astimezone(ZoneInfo(company.timezone)).date()
            ids = await employees.ids_matching(company.id, {"status": {"$ne": EmployeeStatus.TERMINATED}})
            for i in range(0, len(ids), CHUNK):
                people = list((await employees.find_by_ids(company.id, ids[i : i + CHUNK])).values())
                await service.compute(
                    company,
                    people,
                    today - timedelta(days=WARM_DAYS),
                    today - timedelta(days=1),
                    with_segments=True,
                )
                processed += len(people)
                await asyncio.sleep(0)  # let other tasks run between chunks
        logger.info("Productivity cache warm for %d people in %.1fs", processed, time.monotonic() - started)
        return processed
