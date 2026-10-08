"""Connection state shared by the heartbeat, sync and UI layers."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from enum import StrEnum


class ConnectionState(StrEnum):
    SIGNED_OUT = "signed_out"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    OFFLINE = "offline"
    REVOKED = "revoked"


LABELS = {
    ConnectionState.SIGNED_OUT: "Not signed in",
    ConnectionState.CONNECTING: "Connecting…",
    ConnectionState.CONNECTED: "Connected",
    ConnectionState.OFFLINE: "Offline — events are saved locally",
    ConnectionState.REVOKED: "Device access revoked",
}


class ConnectionMonitor:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state = ConnectionState.SIGNED_OUT
        self._last_success: float | None = None
        self._listeners: list[Callable[[ConnectionState], None]] = []

    @property
    def state(self) -> ConnectionState:
        return self._state

    @property
    def last_success(self) -> float | None:
        return self._last_success

    def subscribe(self, listener: Callable[[ConnectionState], None]) -> None:
        self._listeners.append(listener)

    def set(self, state: ConnectionState) -> None:
        with self._lock:
            changed = state != self._state
            self._state = state
            if state == ConnectionState.CONNECTED:
                self._last_success = time.time()
        if changed:
            for listener in list(self._listeners):
                listener(state)
