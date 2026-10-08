"""Background jobs: notification dispatch, alert scanning, screenshot retention, report generation, cache warming.

In production these run in the dedicated worker process (`python -m app.worker`, the `worker` service in Compose),
and API processes set `BACKGROUND_JOBS=false` so request handling never competes with heavy background work.
For a single-process setup (development) the API runs them itself. Running them in several processes at once is
safe either way: queues are claimed atomically and cluster-wide jobs hold a lease, so each piece of work happens once.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

from pymongo.asynchronous.database import AsyncDatabase

from app.core.broker import Broker
from app.core.config import Settings
from app.core.object_storage import ObjectStorage
from app.core.signed_urls import UrlSigner
from app.services.email_service import EmailSender
from app.services.notifications.notifier import Dispatcher, Notifier
from app.services.notifications.scanner import AlertScanner
from app.services.productivity.warmer import ProductivityWarmer
from app.services.reports.worker import ReportWorker
from app.services.retention import run_retention
from app.websocket.manager import ConnectionManager

logger = logging.getLogger(__name__)


class BackgroundJobs:
    def __init__(
        self,
        *,
        db: AsyncDatabase[dict[str, Any]],
        settings: Settings,
        broker: Broker,
        storage: ObjectStorage,
        signer: UrlSigner,
        sockets: ConnectionManager,
        email: EmailSender,
        notifier: Notifier,
    ) -> None:
        from app.api.deps import build_report_engine, get_productivity_service, get_scope_service

        self._db = db
        self._settings = settings
        self._broker = broker
        self._storage = storage
        self.dispatcher = Dispatcher(notifier, db, settings, sockets, email, broker)
        self.scanner = AlertScanner(db, settings, notifier, broker)
        self.reports = ReportWorker(
            db, storage, settings, lambda: build_report_engine(db, settings, storage, signer)
        )
        self.warmer = ProductivityWarmer(
            db, settings, broker, lambda: get_productivity_service(db, settings, get_scope_service(db))
        )
        self._retention: asyncio.Task[None] | None = None
        self.running = False

    async def start(self) -> None:
        await self.dispatcher.start()
        self.scanner.start()
        self._retention = asyncio.create_task(
            run_retention(self._db, self._storage, self._settings, self._broker), name="screenshot-retention"
        )
        await self.reports.start()
        self.warmer.start()
        self.running = True
        logger.info("Background jobs started")

    async def stop(self) -> None:
        if not self.running:
            return
        await self.warmer.stop()
        await self.reports.stop()
        await self.scanner.stop()
        await self.dispatcher.stop()
        if self._retention:
            self._retention.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._retention
        self.running = False
