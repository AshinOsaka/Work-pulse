from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from app.auth.permissions import Role
from app.models.base import PyObjectId, TenantModel


class UserStatus(StrEnum):
    ACTIVE = "active"
    INVITED = "invited"
    SUSPENDED = "suspended"
    DEACTIVATED = "deactivated"


class User(TenantModel):
    email: str
    full_name: str
    password_hash: str
    role: Role = Role.EMPLOYEE
    #: The assigned role's key — a built-in Role value or a custom company role. None means the built-in
    #: role named by ``role``. ``role`` always holds the access level that governs permissions.
    role_key: str | None = None
    status: UserStatus = UserStatus.ACTIVE
    email_verified: bool = False
    email_verified_at: datetime | None = None
    last_login_at: datetime | None = None
    password_changed_at: datetime | None = None
    employee_id: PyObjectId | None = None
    #: Dashboard sections an admin has hidden from this specific person (see app.auth.sections). A visibility
    #: control over what appears on their dashboard, nav and profile; role and scope still govern API access.
    hidden_sections: list[str] = Field(default_factory=list)
    #: When the person acknowledged that this (company) device is monitored. Set once, at onboarding.
    monitoring_acknowledged_at: datetime | None = None
    # --- Two-step verification (TOTP). Secrets are AES-GCM encrypted; recovery codes are SHA-256 hashes. ---------
    mfa_enabled: bool = False
    mfa_enabled_at: datetime | None = None
    mfa_secret: str | None = None
    #: Set during setup until the first code is confirmed.
    mfa_pending_secret: str | None = None
    #: The last accepted time step (a code is never accepted twice).
    mfa_last_step: int | None = None
    mfa_recovery_codes: list[str] = Field(default_factory=list)
