"""Time claims: work done away from the computer (meetings, client visits, calls) that the agent sees as idle.

An employee logs the time themselves. Claims up to the company's daily limit count straight away (managers are
told, and can still reject one); anything beyond the limit waits for a manager. Approved claims count in
**attendance only**: the productivity figures stay based on computer activity.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from app.models.base import PyObjectId, TenantModel


class TimeClaimKind(StrEnum):
    MEETING = "meeting"
    CLIENT_MEETING = "client_meeting"
    FIELD_VISIT = "field_visit"
    CALL = "call"
    OTHER = "other"


class TimeClaimStatus(StrEnum):
    APPROVED = "approved"
    PENDING = "pending"
    REJECTED = "rejected"


class TimeClaim(TenantModel):
    employee_id: PyObjectId
    employee_name: str
    #: The person who logged it (the employee's own user account).
    user_id: PyObjectId
    #: Local date (company time zone), as YYYY-MM-DD.
    day: str
    started_at: datetime
    ended_at: datetime
    kind: TimeClaimKind
    #: Who the meeting was with: colleagues or a client, in the employee's words.
    with_whom: str
    note: str | None = None
    status: TimeClaimStatus
    #: Counted without a review because it was within the daily limit.
    auto_approved: bool = False
    #: A manager who logged it for this person (a meeting several people attended); None when logged by them.
    added_by: PyObjectId | None = None
    added_by_name: str | None = None
    reviewed_by: PyObjectId | None = None
    reviewed_by_name: str | None = None
    reviewed_at: datetime | None = None
    review_note: str | None = None
