"""Background synchronisation of the local event queue.

Events are sent oldest-first in batches. On network or server failure the
batch stays queued and is retried with exponential back-off; connectivity
returning (first successful heartbeat) releases the back-off immediately.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

from app.auth.device_auth import CredentialsRejectedError, DeviceAuthenticator, NotSignedInError
from app.heartbeat.connection import ConnectionMonitor, ConnectionState
from app.storage.event_queue import EventQueue, QueuedEvent
from app.sync.api_client import ApiClient, ApiError, ApiUnavailable, backoff_delay
from app.system.worker import Worker

logger = logging.getLogger(__name__)

MAX_BACKOFF_SECONDS = 300.0


class SyncService(Worker):
    def __init__(
        self,
        queue: EventQueue,
        auth: DeviceAuthenticator,
        api: ApiClient,
        connection: ConnectionMonitor,
        *,
        interval: Callable[[], float],
        batch_size: Callable[[], int],
        on_rejected: Callable[[CredentialsRejectedError], None],
    ) -> None:
        super().__init__("workpulse-sync")
        self._queue = queue
        self._auth = auth
        self._api = api
        self._connection = connection
        self._interval = interval
        self._batch_size = batch_size
        self._on_rejected = on_rejected
        self._failures = 0
        self.last_sync: float | None = None

    def interval(self) -> float:
        if self._failures:
            return min(MAX_BACKOFF_SECONDS, max(2.0, backoff_delay(self._failures, base=2.0, cap=MAX_BACKOFF_SECONDS)))
        return self._interval()

    def step(self) -> None:
        self.flush()

    def flush(self) -> int:
        """Send everything that is due. Returns the number of events the server acknowledged."""
        sent = 0
        retried_auth = False
        while self._auth.signed_in:
            batch = self._queue.due(self._batch_size())
            if not batch:
                self._failures = 0
                return sent
            try:
                self._send(batch)
            except NotSignedInError:
                return sent
            except CredentialsRejectedError as exc:
                self._on_rejected(exc)
                return sent
            except ApiUnavailable as exc:
                self._failures += 1
                self._queue.defer(
                    [e.event_id for e in batch], backoff_delay(self._failures, base=2.0, cap=MAX_BACKOFF_SECONDS)
                )
                self._connection.set(ConnectionState.OFFLINE)
                logger.info("Sync deferred, %d event(s) kept locally: %s", len(self._queue), exc)
                return sent
            except ApiError as exc:
                if exc.status == 401 and not retried_auth:
                    self._auth.invalidate_token()
                    retried_auth = True
                    continue
                if exc.status == 422:
                    sent += self._send_individually(batch)
                    continue
                self._failures += 1
                self._queue.defer(
                    [e.event_id for e in batch], backoff_delay(self._failures, base=2.0, cap=MAX_BACKOFF_SECONDS)
                )
                logger.warning("Sync rejected by server (%s); will retry", exc)
                return sent
            self._queue.ack([e.event_id for e in batch])
            sent += len(batch)
            self._failures = 0
            self.last_sync = time.time()
            if self._auth.signed_in:  # a request in flight during sign-out must not resurrect the state
                self._connection.set(ConnectionState.CONNECTED)
        return sent

    def _send(self, batch: list[QueuedEvent]) -> None:
        result = self._api.request(
            "POST", "/agent/events", json={"events": [e.event for e in batch]}, token=self._auth.token(), retries=1
        )
        for rejected in result.get("rejected", []):
            logger.warning("Server rejected event %s: %s", rejected.get("id"), rejected.get("reason"))

    def _send_individually(self, batch: list[QueuedEvent]) -> int:
        """Isolate a malformed event so one bad record can never block the queue."""
        delivered = 0
        for item in batch:
            try:
                self._send([item])
                delivered += 1
            except ApiError as exc:
                if exc.status != 422:
                    raise
                logger.error("Dropping invalid %s event %s", item.event.get("type"), item.event_id)
            self._queue.ack([item.event_id])
        return delivered
