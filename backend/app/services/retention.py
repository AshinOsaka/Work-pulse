"""Background retention: deletes screenshots once their retention period ends."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from pymongo.asynchronous.database import AsyncDatabase

from app.core.broker import Broker, MemoryBroker
from app.core.config import Settings
from app.core.object_storage import ObjectStorage
from app.repositories.screenshot import ScreenshotRepository
from app.utils.time import utcnow

logger = logging.getLogger(__name__)


async def purge_expired_screenshots(
    screenshots: ScreenshotRepository, storage: ObjectStorage, *, batch: int = 500
) -> int:
    """Objects first, then metadata: a crash in between leaves a document to retry, never an orphaned file."""
    removed = 0
    while True:
        expired = await screenshots.expired(utcnow(), batch)
        if not expired:
            return removed
        for shot in expired:
            await storage.delete(shot.object_key, shot.thumb_key)
        removed += await screenshots.delete_ids([s.id for s in expired])
        if len(expired) < batch:
            return removed


async def run_retention(
    db: AsyncDatabase[dict[str, Any]],
    storage: ObjectStorage,
    settings: Settings,
    broker: Broker | None = None,
) -> None:
    repo = ScreenshotRepository(db)
    lease = broker or MemoryBroker()
    while True:
        try:
            # One process per cluster sweeps (the lease outlives a round, so a crashed holder is replaced).
            if not await lease.lease("screenshot-retention", settings.screenshot_retention_sweep_seconds * 3):
                await asyncio.sleep(settings.screenshot_retention_sweep_seconds)
                continue
            removed = await purge_expired_screenshots(repo, storage)
            if removed:
                logger.info("Retention: deleted %d expired screenshot(s)", removed)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Screenshot retention sweep failed; will retry")
        await asyncio.sleep(settings.screenshot_retention_sweep_seconds)
