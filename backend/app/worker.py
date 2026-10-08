"""The background worker process: `python -m app.worker`.

Runs the jobs in `app.services.background` (notification dispatch, alert scans, retention, report generation,
productivity cache warming) without serving HTTP. Run one or more next to the API processes (which then set
`BACKGROUND_JOBS=false`). Several workers are safe: queues are claimed atomically and cluster-wide jobs hold leases.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
import sys
import tempfile
import time
from pathlib import Path

from app import __version__
from app.core.broker import build_broker
from app.core.config import get_settings
from app.core.database import MongoDatabase
from app.core.keys import url_signing_key
from app.core.logging import configure_logging
from app.core.object_storage import build_object_storage
from app.core.observability import init_observability, start_metrics_server
from app.core.signed_urls import UrlSigner
from app.services.background import BackgroundJobs
from app.services.bootstrap_service import BootstrapService
from app.services.email_service import build_email_sender
from app.services.notifications.notifier import Notifier, OutboxRepository
from app.websocket.manager import ConnectionManager

logger = logging.getLogger("workpulse.worker")

#: Touched every HEARTBEAT_SECONDS while the event loop is responsive and the jobs run (container health check).
HEARTBEAT_FILE = Path(
    os.environ.get("WORKER_HEARTBEAT_FILE", Path(tempfile.gettempdir()) / "workpulse-worker.alive")
)
HEARTBEAT_SECONDS = 15
HEARTBEAT_STALE_SECONDS = 60


async def heartbeat(jobs: BackgroundJobs) -> None:
    while True:
        if jobs.running:
            await asyncio.to_thread(HEARTBEAT_FILE.write_text, str(time.time()))
        await asyncio.sleep(HEARTBEAT_SECONDS)


def check() -> int:
    """`python -m app.worker --check`: 0 when the worker's heartbeat is fresh (Docker HEALTHCHECK)."""
    try:
        age = time.time() - float(HEARTBEAT_FILE.read_text())
    except (OSError, ValueError):
        return 1
    return 0 if age < HEARTBEAT_STALE_SECONDS else 1


async def run() -> None:
    settings = get_settings()
    configure_logging(settings)
    init_observability(settings, "worker")
    if settings.metrics_enabled and settings.worker_metrics_port:
        start_metrics_server(settings.worker_metrics_port)
    mongo = MongoDatabase(settings)
    await mongo.connect()
    await BootstrapService(mongo.db).run()
    await OutboxRepository.ensure_indexes(mongo.db)
    broker = build_broker(settings.redis_url.get_secret_value() if settings.redis_url else None)
    await broker.start()
    notifier = Notifier(mongo.db, broker)
    notifier.start()
    jobs = BackgroundJobs(
        db=mongo.db,
        settings=settings,
        broker=broker,
        storage=build_object_storage(settings),
        signer=UrlSigner(url_signing_key(settings), settings.screenshot_url_ttl_seconds),
        # Pushes go through the broker to whichever API process holds the browser's socket.
        sockets=ConnectionManager(broker),
        email=build_email_sender(settings),
        notifier=notifier,
    )
    await jobs.start()
    logger.info("%s worker v%s started (%s)", settings.app_name, __version__, settings.environment)

    beat = asyncio.create_task(heartbeat(jobs), name="worker-heartbeat")
    stopping = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):  # Windows: Ctrl+C still raises KeyboardInterrupt
            loop.add_signal_handler(sig, stopping.set)
    try:
        await stopping.wait()
    finally:
        beat.cancel()
        await asyncio.to_thread(HEARTBEAT_FILE.unlink, missing_ok=True)
        await jobs.stop()
        await notifier.stop()
        await broker.stop()
        await mongo.close()
        logger.info("Worker stopped")


def main() -> None:
    if "--check" in sys.argv[1:]:
        sys.exit(check())
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(run())


if __name__ == "__main__":
    main()
