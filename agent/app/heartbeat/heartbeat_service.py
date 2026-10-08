"""Heartbeat: tells the server this device is online and what its presence is."""

from __future__ import annotations

import logging
import random
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from app import __version__
from app.activity.session import WorkSessionManager, WorkStatus
from app.auth.device_auth import CredentialsRejectedError, DeviceAuthenticator, NotSignedInError
from app.heartbeat.connection import ConnectionMonitor, ConnectionState
from app.sync.api_client import ApiClient, ApiError, ApiUnavailable, backoff_delay
from app.system.worker import Worker

logger = logging.getLogger(__name__)

JITTER = 0.1


class HeartbeatService(Worker):
    def __init__(
        self,
        auth: DeviceAuthenticator,
        api: ApiClient,
        connection: ConnectionMonitor,
        sessions: WorkSessionManager,
        *,
        interval: Callable[[], float],
        on_policy: Callable[[dict[str, Any]], None],
        on_reconnected: Callable[[], None],
        on_rejected: Callable[[CredentialsRejectedError], None],
        current_app: Callable[[], str | None] = lambda: None,
    ) -> None:
        super().__init__("workpulse-heartbeat")
        self._auth = auth
        self._api = api
        self._connection = connection
        self._sessions = sessions
        self._interval = interval
        self._on_policy = on_policy
        self._on_reconnected = on_reconnected
        self._on_rejected = on_rejected
        self._current_app = current_app
        self._failures = 0

    def interval(self) -> float:
        # While offline, probe more often than the normal interval (with back-off) to reconnect quickly.
        if self._failures:
            return min(self._interval(), max(5.0, backoff_delay(self._failures, base=5.0, cap=self._interval())))
        # +/-10% jitter: thousands of agents that reconnected together (e.g. after a server restart) drift apart
        # instead of hitting the API in lockstep every interval.
        return self._interval() * random.uniform(1 - JITTER, 1 + JITTER)  # noqa: S311 - spreading load, not crypto

    def step(self) -> None:
        self.beat()

    def beat(self) -> bool:
        if not self._auth.signed_in:
            if self._connection.state != ConnectionState.REVOKED:  # keep the reason visible
                self._connection.set(ConnectionState.SIGNED_OUT)
            return False
        status = self._sessions.status
        payload = {
            "presence": None if status == WorkStatus.NOT_WORKING else status.value,
            "session_id": self._sessions.session_id,
            "agent_version": __version__,
            "sent_at": datetime.now(UTC).isoformat(),
            "current_app": self._current_app() if status == WorkStatus.ACTIVE else None,
        }
        was_connected = self._connection.state == ConnectionState.CONNECTED
        try:
            response = self._api.request("POST", "/agent/heartbeat", json=payload, token=self._auth.token(), retries=0)
        except NotSignedInError:
            self._connection.set(ConnectionState.SIGNED_OUT)
            return False
        except CredentialsRejectedError as exc:
            self._on_rejected(exc)
            return False
        except ApiUnavailable:
            self._failures += 1
            self._connection.set(ConnectionState.OFFLINE)
            return False
        except ApiError as exc:
            if exc.code in ("device_revoked", "employee_terminated", "account_not_active"):
                self._on_rejected(CredentialsRejectedError(exc.code, exc.message))
                return False
            if exc.status == 401:
                self._auth.invalidate_token()
            self._failures += 1
            logger.warning("Heartbeat rejected: %s", exc)
            return False

        self._failures = 0
        if not self._auth.signed_in:  # signed out while the request was in flight
            return False
        self._connection.set(ConnectionState.CONNECTED)
        if policy := response.get("policy"):
            self._on_policy(policy)
        if not was_connected:
            self._on_reconnected()
        return True
