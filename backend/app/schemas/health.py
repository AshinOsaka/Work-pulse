from __future__ import annotations

from datetime import datetime
from typing import Literal

from app.schemas.common import APIModel


class ComponentHealth(APIModel):
    status: Literal["ok", "unavailable"]
    latency_ms: float | None = None


class HealthResponse(APIModel):
    status: Literal["ok", "degraded"]
    service: str
    version: str
    environment: str
    timestamp: datetime
    checks: dict[str, ComponentHealth]
