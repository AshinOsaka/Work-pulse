"""MongoDB connection lifecycle (PyMongo native async API)."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any

from pymongo import AsyncMongoClient
from pymongo.errors import PyMongoError

if TYPE_CHECKING:
    from pymongo.asynchronous.database import AsyncDatabase

    from app.core.config import Settings

logger = logging.getLogger(__name__)

Document = dict[str, Any]


class MongoDatabase:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: AsyncMongoClient[Document] | None = None

    async def connect(self) -> None:
        self._client = AsyncMongoClient(
            self._settings.mongodb_url,
            serverSelectionTimeoutMS=self._settings.mongodb_server_selection_timeout_ms,
            maxPoolSize=self._settings.mongodb_max_pool_size,
            minPoolSize=self._settings.mongodb_min_pool_size,
            maxIdleTimeMS=self._settings.mongodb_max_idle_time_ms,
            waitQueueTimeoutMS=self._settings.mongodb_wait_queue_timeout_ms,
            retryWrites=True,
            retryReads=True,
            tz_aware=True,
            uuidRepresentation="standard",
            appname="workpulse-api",
        )
        retries = max(1, self._settings.mongodb_connect_retries)
        for attempt in range(1, retries + 1):
            try:
                await self.ping()
                logger.info("Connected to MongoDB database '%s'", self._settings.mongodb_db)
                return
            except PyMongoError as exc:
                if attempt == retries:
                    logger.error("MongoDB unreachable after %d attempts", attempt)
                    raise
                logger.warning("MongoDB not ready (attempt %d/%d): %s", attempt, retries, exc)
                await asyncio.sleep(attempt)

    @property
    def client(self) -> AsyncMongoClient[Document]:
        if self._client is None:
            raise RuntimeError("MongoDB client is not connected")
        return self._client

    @property
    def db(self) -> AsyncDatabase[Document]:
        return self.client[self._settings.mongodb_db]

    async def ping(self) -> float:
        """Round-trip the server and return latency in milliseconds."""
        started = time.perf_counter()
        await self.client.admin.command("ping")
        return (time.perf_counter() - started) * 1000

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None
