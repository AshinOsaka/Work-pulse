"""Small helpers shared by services."""

from __future__ import annotations

from datetime import UTC, date, datetime, time

from bson import ObjectId
from bson.errors import InvalidId
from pymongo.errors import DuplicateKeyError

from app.core.exceptions import BadRequestError, NotFoundError


def parse_id(value: str, *, not_found: str = "Resource not found.", code: str = "not_found") -> ObjectId:
    """Path identifiers: a malformed id is indistinguishable from a missing one."""
    try:
        return ObjectId(value)
    except (InvalidId, TypeError) as exc:
        raise NotFoundError(not_found, code=code) from exc


def parse_ref(value: str | None, field: str) -> ObjectId | None:
    """Body references (already pattern-validated by the schema)."""
    if value is None:
        return None
    try:
        return ObjectId(value)
    except (InvalidId, TypeError) as exc:
        raise BadRequestError(
            f"Invalid identifier for {field}.", code="invalid_reference", details={"field": field}
        ) from exc


def duplicate_key_fields(exc: DuplicateKeyError) -> set[str]:
    details = exc.details or {}
    pattern = details.get("keyPattern") or details.get("keyValue") or {}
    return set(pattern)


def date_to_datetime(value: date | None) -> datetime | None:
    return datetime.combine(value, time.min, tzinfo=UTC) if value else None


def datetime_to_date(value: datetime | None) -> date | None:
    return value.date() if value else None
