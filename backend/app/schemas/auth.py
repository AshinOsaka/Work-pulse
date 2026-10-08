from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import EmailStr, Field, field_validator

from app.auth.permissions import Permission
from app.schemas.common import APIModel, Timezone
from app.schemas.company import CompanyOut, CompanySize
from app.schemas.user import UserOut

PASSWORD_MIN_LENGTH = 10
PASSWORD_MAX_LENGTH = 128


def validate_password_strength(value: str) -> str:
    if len(value) < PASSWORD_MIN_LENGTH:
        raise ValueError(f"Password must be at least {PASSWORD_MIN_LENGTH} characters.")
    if not re.search(r"[A-Za-z]", value) or not re.search(r"\d", value):
        raise ValueError("Password must contain at least one letter and one number.")
    return value


class RegisterRequest(APIModel):
    company_name: str = Field(min_length=2, max_length=120)
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(max_length=PASSWORD_MAX_LENGTH)
    company_size: CompanySize | None = None
    industry: str | None = Field(default=None, max_length=80)
    timezone: Timezone = "UTC"

    @field_validator("password")
    @classmethod
    def _password_strength(cls, value: str) -> str:
        return validate_password_strength(value)


class LoginRequest(APIModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)


class ForgotPasswordRequest(APIModel):
    email: EmailStr


class ResetPasswordRequest(APIModel):
    token: str = Field(min_length=16, max_length=256)
    password: str = Field(max_length=PASSWORD_MAX_LENGTH)

    @field_validator("password")
    @classmethod
    def _password_strength(cls, value: str) -> str:
        return validate_password_strength(value)


class VerifyEmailRequest(APIModel):
    token: str = Field(min_length=16, max_length=256)


class ChangePasswordRequest(APIModel):
    current_password: str = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)
    new_password: str = Field(max_length=PASSWORD_MAX_LENGTH)

    @field_validator("new_password")
    @classmethod
    def _password_strength(cls, value: str) -> str:
        return validate_password_strength(value)


class SessionResponse(APIModel):
    user: UserOut
    company: CompanyOut
    permissions: list[Permission]


class AuthResponse(SessionResponse):
    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105
    expires_in: int = Field(description="Access token lifetime in seconds.")


class InvitationPreview(APIModel):
    email: str
    full_name: str
    company_name: str
    expires_at: datetime


class AcceptInvitationRequest(APIModel):
    token: str = Field(min_length=16, max_length=256)
    password: str = Field(max_length=PASSWORD_MAX_LENGTH)
    full_name: str | None = Field(default=None, min_length=2, max_length=120)

    @field_validator("password")
    @classmethod
    def _password_strength(cls, value: str) -> str:
        return validate_password_strength(value)


# --------------------------------------------------------------------------- two-step verification
class MfaChallengeResponse(APIModel):
    """Returned by sign-in instead of a session when the account uses two-step verification."""

    mfa_required: Literal[True] = True
    challenge: str
    expires_in: int = Field(description="Seconds left to enter the code.")


class MfaVerifyRequest(APIModel):
    challenge: str = Field(min_length=1, max_length=2048)
    #: A 6-digit authenticator code or a recovery code.
    code: str = Field(min_length=6, max_length=20)


class PasswordConfirmRequest(APIModel):
    password: str = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)


class MfaSetupResponse(APIModel):
    #: For manual entry when the QR code can't be scanned.
    secret: str
    uri: str
    qr_svg: str = Field(description="data: URI of an SVG QR code for the provisioning URI.")


class MfaCodeRequest(APIModel):
    code: str = Field(min_length=6, max_length=20)


class MfaManageRequest(APIModel):
    password: str = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)
    code: str = Field(min_length=6, max_length=20)


class RecoveryCodesResponse(APIModel):
    #: Shown once; each works a single time.
    codes: list[str]


# --------------------------------------------------------------------------- sessions
class SessionOut(APIModel):
    id: str
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    device: str = Field(description="Browser and system, from the user agent.")
    ip_address: str | None
    mfa: bool
    current: bool


def describe_user_agent(agent: str | None) -> str:
    """'Edge on Windows' style labels; enough to recognise a session, not a fingerprint."""
    if not agent:
        return "Unknown device"
    browsers = (
        ("Edg/", "Edge"),
        ("OPR/", "Opera"),
        ("Firefox/", "Firefox"),
        ("Chrome/", "Chrome"),
        ("Safari/", "Safari"),
        ("python-httpx", "Script (httpx)"),
        ("WorkPulseAgent", "WorkPulse desktop agent"),
    )
    systems = (
        ("Windows", "Windows"),
        ("Android", "Android"),
        ("iPhone", "iOS"),
        ("iPad", "iPadOS"),
        ("Mac OS X", "macOS"),
        ("CrOS", "ChromeOS"),
        ("Linux", "Linux"),
    )
    product = agent.split("/")[0].split(" ")[0][:30] or "Unknown app"
    browser = next(
        (name for marker, name in browsers if marker in agent), "Browser" if "Mozilla" in agent else product
    )
    system = next((name for marker, name in systems if marker in agent), None)
    return f"{browser} on {system}" if system else browser


class SessionsRevokedResponse(APIModel):
    revoked: int
