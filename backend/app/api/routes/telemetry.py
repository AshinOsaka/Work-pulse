"""Browser error reports: the web app's error tracking hook.

Uncaught errors, unhandled promise rejections and React render errors are posted here, logged as structured records
and forwarded to the error reporters (Sentry when configured). No sign-in is required, because errors on the sign-in
page matter too. Reports are size-limited and rate-limited per client address, and only the page path is accepted
(never the query string, which can carry one-time tokens).
"""

from __future__ import annotations

import logging
import re
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field, field_validator

from app.api.deps import RequestMetaDep, get_throttle
from app.core.dependencies import SettingsDep
from app.core.observability import CLIENT_ERRORS, report_message
from app.services.context import RequestMeta
from app.services.throttle import Limit, Throttle

logger = logging.getLogger("workpulse.client")

router = APIRouter(tags=["telemetry"])

_TOKENISH = re.compile(r"(token|signature|sig|code)=[^&\s]+", re.IGNORECASE)


class ClientErrorReport(BaseModel):
    kind: Literal["error", "unhandledrejection", "render", "chunk"]
    message: str = Field(max_length=1000)
    page: str = Field(max_length=300, description="Path of the page, without the query string.")
    source: str | None = Field(default=None, max_length=300)
    stack: str | None = Field(default=None, max_length=8000)
    release: str | None = Field(default=None, max_length=64)

    @field_validator("page", "source")
    @classmethod
    def _strip_query(cls, value: str | None) -> str | None:
        return value.split("?", 1)[0].split("#", 1)[0] if value else value

    @field_validator("message", "stack")
    @classmethod
    def _redact(cls, value: str | None) -> str | None:
        return _TOKENISH.sub(r"\1=[redacted]", value) if value else value


@router.post("/client-errors", status_code=status.HTTP_202_ACCEPTED, summary="Report a browser error")
async def report_client_error(
    body: ClientErrorReport,
    settings: SettingsDep,
    meta: RequestMetaDep,
    throttle: Annotated[Throttle, Depends(get_throttle)],
) -> dict[str, str]:
    await _limit(throttle, settings.client_errors_per_hour, meta)
    CLIENT_ERRORS.labels(kind=body.kind).inc()
    context = {"kind": body.kind, "page": body.page, "source": body.source, "release": body.release}
    logger.warning(
        "Browser %s on %s: %s",
        body.kind,
        body.page,
        body.message[:300],
        extra={"client_error": context | {"stack": (body.stack or "")[:2000]}},
    )
    report_message(f"Browser {body.kind}: {body.message[:300]}", **context, stack=body.stack)
    return {"status": "accepted"}


async def _limit(throttle: Throttle, per_hour: int, meta: RequestMeta) -> None:
    await throttle.hit(Limit("client-errors-ip", per_hour, 3600), meta.ip_address)
