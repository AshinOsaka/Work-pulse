"""Builders for the events the agent reports.

This module is the complete list of what the agent sends: work-session
boundaries, active/idle transitions, application-usage segments and agent
lifecycle. Nothing else.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from app import __version__


def _event(kind: str, at: float, **fields: Any) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "type": kind,
        "occurred_at": datetime.fromtimestamp(at, UTC).isoformat(),
        **fields,
    }


def session_started(session_id: str, at: float) -> dict[str, Any]:
    return _event("session.started", at, session_id=session_id)


def session_stopped(
    session_id: str, at: float, reason: str, active_seconds: float, idle_seconds: float
) -> dict[str, Any]:
    return _event(
        "session.stopped",
        at,
        session_id=session_id,
        reason=reason,
        active_seconds=int(active_seconds),
        idle_seconds=int(idle_seconds),
    )


def presence_changed(session_id: str, status: str, at: float) -> dict[str, Any]:
    return _event("presence.changed", at, session_id=session_id, status=status)


def agent_started(at: float) -> dict[str, Any]:
    return _event("agent.started", at, agent_version=__version__)


def agent_stopped(reason: str, at: float) -> dict[str, Any]:
    return _event("agent.stopped", at, reason=reason)


def activity_segment(
    *,
    session_id: str,
    app_id: str,
    app_name: str,
    window_title: str | None,
    started_at: float,
    domain: str | None = None,
    ended_at: float,
    active_seconds: float,
    activity_level: int,
) -> dict[str, Any]:
    """Foreground application usage for a span of time (metadata only)."""
    return _event(
        "activity.segment",
        ended_at,
        session_id=session_id,
        app_id=app_id,
        app_name=app_name,
        window_title=window_title,
        **({"domain": domain} if domain else {}),
        started_at=datetime.fromtimestamp(started_at, UTC).isoformat(),
        ended_at=datetime.fromtimestamp(ended_at, UTC).isoformat(),
        active_seconds=int(active_seconds),
        activity_level=max(0, min(100, int(activity_level))),
    )
