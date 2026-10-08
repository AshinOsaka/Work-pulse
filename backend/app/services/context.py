from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RequestMeta:
    """Client metadata captured for sessions and audit events."""

    ip_address: str | None = None
    user_agent: str | None = None
