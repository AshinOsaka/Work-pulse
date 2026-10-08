"""Structured logging with request correlation IDs."""

from __future__ import annotations

import json
import logging
import re
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.config import Settings

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

_STANDARD_ATTRS = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {
    "message",
    "asctime",
    "request_id",
}


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get() or "-"
        return True


_SECRET_PARAMS = re.compile(
    r"((?:token|access_token|refresh_token|password|secret)=)[^&\s\"']+", re.IGNORECASE
)


class SecretRedactionFilter(logging.Filter):
    """Credentials must never reach logs. Browsers pass the access token in the query string of
    WebSocket URLs, which uvicorn logs verbatim ('"WebSocket /path?token=..." [accepted]')."""

    #: The development `console` e-mail backend deliberately prints links (with their one-time tokens) to the
    #: log, because that is how e-mail is delivered locally. Production uses a real e-mail backend.
    EXEMPT = ("app.services.email_service",)

    def filter(self, record: logging.LogRecord) -> bool:
        if record.name.startswith(self.EXEMPT):
            return True
        message = record.getMessage()
        redacted = _SECRET_PARAMS.sub(r"\1[redacted]", message)
        if redacted != message:
            record.msg, record.args = redacted, ()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD_ATTRS:
                payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(settings: Settings) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(RequestIdFilter())
    handler.addFilter(SecretRedactionFilter())
    if settings.log_json:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-8s [%(request_id)s] %(name)s: %(message)s")
        )

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.log_level.upper())

    # Route uvicorn through our handler; we emit our own access log line.
    for name in ("uvicorn", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers = []
        uvicorn_logger.propagate = True
    logging.getLogger("uvicorn.access").disabled = True
    logging.getLogger("pymongo").setLevel(logging.WARNING)
