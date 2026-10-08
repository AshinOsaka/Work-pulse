from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app import __version__
from app.core.dependencies import MongoDep, SettingsDep
from app.schemas.health import ComponentHealth, HealthResponse
from app.utils.time import utcnow

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", response_model=HealthResponse, summary="Readiness check including dependencies")
@router.get("/ready", response_model=HealthResponse, summary="Readiness probe (same as /health)")
async def health(request: Request, settings: SettingsDep, mongo: MongoDep) -> JSONResponse:
    try:
        latency = await mongo.ping()
        database = ComponentHealth(status="ok", latency_ms=round(latency, 2))
    except Exception as exc:
        logger.warning("Health check: database unavailable (%s)", exc)
        database = ComponentHealth(status="unavailable")

    checks = {"database": database}
    broker = getattr(request.app.state, "broker", None)
    if broker is not None and broker.shared:
        try:
            checks["realtime"] = ComponentHealth(status="ok", latency_ms=round(await broker.ping(), 2))
        except Exception as exc:
            logger.warning("Health check: Redis unavailable (%s)", type(exc).__name__)
            checks["realtime"] = ComponentHealth(status="unavailable")

    healthy = all(c.status == "ok" for c in checks.values())
    body = HealthResponse(
        status="ok" if healthy else "degraded",
        service=settings.app_name,
        version=__version__,
        environment=settings.environment,
        timestamp=utcnow(),
        checks=checks,
    )
    return JSONResponse(status_code=200 if healthy else 503, content=body.model_dump(mode="json"))


@router.get("/live", summary="Liveness probe (no dependency checks)")
async def live() -> dict[str, str]:
    return {"status": "ok"}
