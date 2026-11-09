from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import Field, field_validator

from app.models.time_claim import TimeClaimKind, TimeClaimStatus
from app.schemas.common import APIModel
from app.schemas.organization import Ref


class TimeClaimCreate(APIModel):
    #: Local date (company time zone).
    day: date
    #: Local wall-clock times on that day, "HH:MM" (24-hour).
    start_time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    end_time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    kind: TimeClaimKind
    with_whom: str = Field(min_length=1, max_length=120)
    note: str | None = Field(default=None, max_length=500)

    @field_validator("with_whom")
    @classmethod
    def _strip(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Say who the meeting was with.")
        return value

    @field_validator("note")
    @classmethod
    def _strip_note(cls, value: str | None) -> str | None:
        return (value or "").strip() or None


class TimeClaimReview(APIModel):
    decision: Literal["approve", "reject"]
    note: str | None = Field(default=None, max_length=300)


class TimeClaimOut(APIModel):
    id: str
    employee: Ref
    day: date
    started_at: datetime
    ended_at: datetime
    minutes: int
    kind: TimeClaimKind
    with_whom: str
    note: str | None
    status: TimeClaimStatus
    auto_approved: bool
    reviewed_by: str | None
    reviewed_at: datetime | None
    review_note: str | None
    created_at: datetime
    #: The viewer may approve or reject it (a manager of that person; never their own, unless an admin).
    can_review: bool
    #: The viewer may delete it (their own claim that nobody has reviewed yet).
    can_delete: bool


class TimeClaimPage(APIModel):
    items: list[TimeClaimOut]
    total: int
    #: Claims waiting for a decision that the viewer can review.
    pending_for_me: int
    #: The company's daily limit without approval, in minutes (0 = every claim needs approval).
    auto_minutes: int
    timezone: str
