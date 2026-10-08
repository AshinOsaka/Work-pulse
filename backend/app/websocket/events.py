"""WebSocket event envelope.

All realtime messages share one envelope: ``{"type": str, "payload": {...}, "ts": iso8601}``.
Event names are namespaced (``<domain>.<action>``). Namespaces reserved for
future phases — not implemented yet:

* ``presence.*``   — agent online/idle/offline status
* ``activity.*``   — live activity feed
* ``alert.*``      — alert notifications
* ``signaling.*``  — WebRTC offer/answer/ICE exchange for live screen viewing
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from app.utils.time import utcnow


class EventType(StrEnum):
    CONNECTION_READY = "connection.ready"
    PING = "ping"
    PONG = "pong"
    ERROR = "error"


class WsEvent(BaseModel):
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    ts: datetime = Field(default_factory=utcnow)
