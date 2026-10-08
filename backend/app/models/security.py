"""Sign-in sessions and request-throttling buckets."""

from __future__ import annotations

from datetime import datetime

from app.models.base import MongoModel, PyObjectId, TenantModel


class AuthSession(TenantModel):
    """One signed-in browser session (a refresh-token family).

    Access tokens carry the session id (`sid`), and every request checks that the session is still active, so
    signing out, "sign out everywhere", a password change or detected token theft take effect immediately rather
    than when the short-lived access token would have expired.
    """

    user_id: PyObjectId
    expires_at: datetime
    last_seen_at: datetime
    user_agent: str | None = None
    ip_address: str | None = None
    #: Whether this session passed a second factor at sign-in.
    mfa: bool = False
    revoked_at: datetime | None = None
    revoked_reason: str | None = None


class RateLimitBucket(MongoModel):
    """A fixed-window counter shared by every API process."""

    key: str
    count: int = 0
    expires_at: datetime
