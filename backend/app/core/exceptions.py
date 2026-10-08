"""Application error hierarchy and centralised exception handlers.

Every error leaving the API has the same envelope:

    {"error": {"code": "...", "message": "...", "details": ...}, "request_id": "..."}
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any, ClassVar

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import request_id_var

logger = logging.getLogger(__name__)


class AppError(Exception):
    status_code: ClassVar[int] = 500
    default_code: ClassVar[str] = "internal_error"
    default_message: ClassVar[str] = "An unexpected error occurred."

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        details: Any = None,
    ) -> None:
        self.message = message or self.default_message
        self.code = code or self.default_code
        self.details = details
        super().__init__(self.message)


class BadRequestError(AppError):
    status_code = 400
    default_code = "bad_request"
    default_message = "The request could not be processed."


class UnauthorizedError(AppError):
    status_code = 401
    default_code = "unauthorized"
    default_message = "Authentication required."


class ForbiddenError(AppError):
    status_code = 403
    default_code = "forbidden"
    default_message = "You do not have permission to perform this action."


class NotFoundError(AppError):
    status_code = 404
    default_code = "not_found"
    default_message = "The requested resource was not found."


class ConflictError(AppError):
    status_code = 409
    default_code = "conflict"
    default_message = "The resource already exists."


class PayloadTooLargeError(AppError):
    status_code = 413
    default_code = "payload_too_large"
    default_message = "The request body is too large."


class TooManyRequestsError(AppError):
    status_code = 429
    default_code = "rate_limited"
    default_message = "Too many requests. Please try again later."

    def __init__(self, message: str | None = None, *, retry_after: int = 60, code: str | None = None) -> None:
        super().__init__(message, code=code, details={"retry_after": retry_after})
        self.headers = {"Retry-After": str(retry_after)}


class ServiceUnavailableError(AppError):
    status_code = 503
    default_code = "service_unavailable"
    default_message = "The service is temporarily unavailable."


_HTTP_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    429: "rate_limited",
}


def error_response(
    status_code: int,
    code: str,
    message: str,
    details: Any = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {"code": code, "message": message, "details": details},
            "request_id": request_id_var.get(),
        },
        headers=headers,
    )


def app_error_response(exc: AppError) -> JSONResponse:
    headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else getattr(exc, "headers", None)
    return error_response(exc.status_code, exc.code, exc.message, exc.details, headers)


async def _app_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    if exc.status_code >= 500:
        logger.error("Application error: %s", exc.message)
    return app_error_response(exc)


def humanize_validation_error(err: Mapping[str, Any]) -> str:
    """Turn Pydantic's developer-facing messages into text fit for end users."""
    kind = str(err.get("type", ""))
    ctx = err.get("ctx") or {}
    message = str(err.get("msg", "Invalid value"))
    if kind == "missing":
        return "This field is required."
    if kind == "string_too_short":
        minimum = ctx.get("min_length", 1)
        return "This field is required." if minimum == 1 else f"Must be at least {minimum} characters."
    if kind == "string_too_long":
        return f"Must be at most {ctx.get('max_length')} characters."
    if kind == "string_pattern_mismatch":
        return "Contains characters that are not allowed."
    if message.startswith("value is not a valid email address"):
        return "Enter a valid email address."
    if kind in ("date_from_datetime_parsing", "date_parsing"):
        return "Enter a valid date."
    message = message.removeprefix("Value error, ")
    if message.startswith("Input should be"):
        message = "Must be" + message.removeprefix("Input should be")
    return message[:1].upper() + message[1:]


async def _validation_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    details = []
    for err in exc.errors():
        location = [str(part) for part in err.get("loc", ()) if part not in ("body", "query", "path")]
        details.append(
            {
                "field": ".".join(location) or None,
                "message": humanize_validation_error(err),
                "type": err.get("type"),
            }
        )
    return error_response(422, "validation_error", "Request validation failed.", details)


async def _http_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    code = _HTTP_CODES.get(exc.status_code, "http_error")
    message = exc.detail if isinstance(exc.detail, str) else "Request failed."
    return error_response(exc.status_code, code, message, headers=getattr(exc, "headers", None))


async def _database_unavailable_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.warning("Database unavailable: %s", type(exc).__name__)
    return error_response(
        503,
        "database_unavailable",
        "WorkPulse can't reach its database right now. Please try again in a moment.",
        headers={"Retry-After": "5"},
    )


async def _realtime_unavailable_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.warning("Realtime service (Redis) unavailable: %s", type(exc).__name__)
    return error_response(
        503,
        "realtime_unavailable",
        "Live features are temporarily unavailable. Please try again in a moment.",
        headers={"Retry-After": "5"},
    )


async def _unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception", exc_info=exc)
    return error_response(500, "internal_error", "An unexpected error occurred.")


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    # Infrastructure outages: a clear, retryable 503 instead of an "unexpected error".
    from pymongo.errors import ConnectionFailure
    from redis.exceptions import ConnectionError as RedisConnectionError
    from redis.exceptions import TimeoutError as RedisTimeoutError

    app.add_exception_handler(ConnectionFailure, _database_unavailable_handler)
    app.add_exception_handler(RedisConnectionError, _realtime_unavailable_handler)
    app.add_exception_handler(RedisTimeoutError, _realtime_unavailable_handler)
    app.add_exception_handler(Exception, _unhandled_exception_handler)
