"""Live screen-viewing sessions. Media flows peer to peer; this records who watched whom, when and why it ended."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field

from app.models.base import PyObjectId, TenantModel


class LiveStatus(StrEnum):
    REQUESTED = "requested"  # created; waiting for the viewer's offer and the agent's answer
    CONNECTING = "connecting"  # offer/answer exchanged, ICE in progress
    LIVE = "live"  # media flowing
    INTERRUPTED = "interrupted"  # a side dropped; waiting for it to come back within the grace period
    ENDED = "ended"


ACTIVE_STATUSES = (LiveStatus.REQUESTED, LiveStatus.CONNECTING, LiveStatus.LIVE, LiveStatus.INTERRUPTED)


class LiveSession(TenantModel):
    employee_id: PyObjectId
    device_id: PyObjectId
    viewer_user_id: PyObjectId
    viewer_name: str
    status: LiveStatus = LiveStatus.REQUESTED
    #: When media first started flowing.
    connected_at: datetime | None = None
    #: Hard stop: request time + the policy's maximum session length.
    expires_at: datetime
    ended_at: datetime | None = None
    end_reason: str | None = None
    #: Seconds with media flowing (excludes interruptions before the first connection).
    duration_seconds: int | None = None
    reconnects: int = 0
    #: How media was negotiated (see `services/live_media.py`); "p2p" until an SFU route exists.
    media_route: str = "p2p"
    #: Set when the owning API process shut down cleanly and released the session (a deploy or restart):
    #: another process adopts it when the viewer or agent reconnects, within the reconnect grace period.
    handover_at: datetime | None = None
    #: Seconds of media so far, carried over to the process that adopts the session.
    live_seconds: float = 0.0


class LiveEventType(StrEnum):
    """One session's timeline (`live_session_events`). The audit log keeps the security record alongside it."""

    REQUESTED = "STREAM_REQUESTED"  # a viewer asked to watch
    AUTHORIZED = "STREAM_AUTHORIZED"  # permission, scope, policy, device and work session all checked
    CONNECTING = "STREAM_CONNECTING"  # offer/answer exchanged, ICE in progress
    STARTED = "STREAM_STARTED"  # media flowing for the first time
    DISCONNECTED = (
        "STREAM_DISCONNECTED"  # a side or the media path dropped; waiting for it within the grace period
    )
    RECONNECTED = "STREAM_RECONNECTED"  # media flowing again after an interruption
    STOPPED = "STREAM_STOPPED"  # ended on purpose (viewer, time limit, policy, the employee's agent)
    FAILED = "STREAM_FAILED"  # ended by a failure (never connected, connection lost, a side never came back)


#: End reasons that are a deliberate stop; anything else ends the session as a failure.
STOP_REASONS = frozenset(
    {
        "viewer_stopped",
        "max_duration",
        "work_session_stopped",
        "not_working",
        "live_view_disabled",
        "signed_out",
        "agent_stopped",
        "server_shutdown",
    }
)


class LiveSessionEvent(TenantModel):
    session_id: PyObjectId
    event: LiveEventType
    #: The user who acted (the viewer), or None for the system and the employee's agent.
    actor_id: PyObjectId | None = None
    #: "viewer" (with their role in metadata), "agent" or "system".
    actor_role: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime
