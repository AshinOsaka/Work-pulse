from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Any, Generic, TypeVar
from zoneinfo import available_timezones

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

T = TypeVar("T")


class APIModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)


class MessageResponse(APIModel):
    message: str


class ErrorDetail(APIModel):
    code: str
    message: str
    details: Any = None


class ErrorResponse(APIModel):
    error: ErrorDetail
    request_id: str | None = None


class Page(APIModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int

    @classmethod
    def build(cls, items: list[T], total: int, page: int, page_size: int) -> Page[T]:
        return cls(
            items=items, total=total, page=page, page_size=page_size, pages=max(1, -(-total // page_size))
        )


@lru_cache(maxsize=1)
def known_timezones() -> frozenset[str]:
    return frozenset(available_timezones()) | {"UTC"}


def _validate_timezone(value: str) -> str:
    if value not in known_timezones():
        raise ValueError("Unknown timezone.")
    return value


ObjectIdStr = Annotated[str, Field(pattern=r"^[0-9a-fA-F]{24}$", examples=["665f1c2e8b3e4a0012345678"])]
Timezone = Annotated[str, AfterValidator(_validate_timezone)]
