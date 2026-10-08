"""Server-side records for refresh tokens and one-time tokens.

Raw token values are never stored — only SHA-256 digests.
"""

from __future__ import annotations

from datetime import datetime

from app.models.base import PyObjectId, TenantModel


class RefreshToken(TenantModel):
    user_id: PyObjectId
    token_hash: str
    family_id: str
    expires_at: datetime
    revoked_at: datetime | None = None
    revoked_reason: str | None = None
    last_used_at: datetime | None = None
    user_agent: str | None = None
    ip_address: str | None = None


class OneTimeToken(TenantModel):
    user_id: PyObjectId
    token_hash: str
    expires_at: datetime
    used_at: datetime | None = None


class PasswordResetToken(OneTimeToken):
    pass


class EmailVerificationToken(OneTimeToken):
    email: str


class InvitationToken(OneTimeToken):
    email: str
    invited_by_user_id: PyObjectId | None = None
