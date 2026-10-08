from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.auth.permissions import Role
from app.models.user import User, UserStatus
from app.schemas.common import APIModel


class UserOut(APIModel):
    id: str
    company_id: str
    email: str
    full_name: str
    role: Role
    status: UserStatus
    email_verified: bool
    last_login_at: datetime | None
    created_at: datetime
    employee_id: str | None = None
    mfa_enabled: bool = False

    @classmethod
    def from_model(cls, user: User) -> UserOut:
        return cls(
            id=str(user.id),
            company_id=str(user.company_id),
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            status=user.status,
            email_verified=user.email_verified,
            last_login_at=user.last_login_at,
            created_at=user.created_at,
            employee_id=str(user.employee_id) if user.employee_id else None,
            mfa_enabled=user.mfa_enabled,
        )


class UpdateProfileRequest(APIModel):
    full_name: str = Field(min_length=2, max_length=120)


class UserAdminOut(UserOut):
    """Admin view of a member (same fields; kept separate so it can diverge)."""

    @classmethod
    def from_user(cls, user: User) -> UserAdminOut:
        return cls(**UserOut.from_model(user).model_dump())


class RoleUpdateRequest(APIModel):
    role: Role
