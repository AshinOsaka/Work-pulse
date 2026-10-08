"""Password hashing, JWT access tokens and opaque token helpers."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache
from typing import TYPE_CHECKING
from uuid import uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.exceptions import UnauthorizedError
from app.utils.time import utcnow

if TYPE_CHECKING:
    from app.core.config import Settings

ACCESS_TOKEN_TYPE = "access"  # noqa: S105 - token kind, not a secret

_password_hasher = PasswordHasher()

# Placeholder hash for accounts that have not set a password yet (invited users).
# It is not a valid Argon2 hash, so no password can ever verify against it.
UNUSABLE_PASSWORD = "!unusable"  # noqa: S105

_ENROLLMENT_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    return _password_hasher.check_needs_rehash(password_hash)


@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    return _password_hasher.hash(secrets.token_urlsafe(16))


def burn_password_check(password: str) -> None:
    """Spend the same time as a real verification to avoid user enumeration."""
    verify_password(_dummy_hash(), password)


def generate_opaque_token() -> str:
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    """Opaque tokens are stored only as SHA-256 digests."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class AccessTokenClaims:
    subject: str
    company_id: str
    role: str
    jti: str
    expires_at: datetime
    #: The sign-in session this token belongs to (checked on every request, so revocation is immediate).
    session_id: str = ""


def create_access_token(
    *, user_id: str, company_id: str, role: str, settings: Settings, session_id: str
) -> tuple[str, datetime]:
    now = utcnow()
    expires_at = now + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": user_id,
        "cid": company_id,
        "role": role,
        "sid": session_id,
        "type": ACCESS_TOKEN_TYPE,
        "iat": now,
        "nbf": now,
        "exp": expires_at,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "jti": uuid4().hex,
    }
    token = jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm=settings.jwt_algorithm)
    return token, expires_at


def decode_access_token(token: str, settings: Settings) -> AccessTokenClaims:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={"require": ["exp", "iat", "sub", "aud", "iss", "type"]},
            leeway=10,
        )
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("Access token has expired.", code="token_expired") from exc
    except jwt.InvalidTokenError as exc:
        raise UnauthorizedError("Invalid access token.", code="invalid_token") from exc

    if payload.get("type") != ACCESS_TOKEN_TYPE or not payload.get("cid") or not payload.get("sid"):
        raise UnauthorizedError("Invalid access token.", code="invalid_token")

    return AccessTokenClaims(
        subject=str(payload["sub"]),
        company_id=str(payload["cid"]),
        role=str(payload.get("role", "")),
        jti=str(payload.get("jti", "")),
        expires_at=datetime.fromtimestamp(payload["exp"], tz=utcnow().tzinfo),
        session_id=str(payload["sid"]),
    )


MFA_CHALLENGE_TYPE = "mfa_challenge"
MFA_CHALLENGE_MINUTES = 5


def _mfa_audience(settings: Settings) -> str:
    return f"{settings.jwt_audience}:mfa"


def create_mfa_challenge(*, user_id: str, company_id: str, settings: Settings) -> str:
    """Proof that the password step passed. Useless on its own: it is only accepted, with a valid code, by the
    second-step endpoint (own audience and type, so it can never be used as an access token)."""
    now = utcnow()
    payload = {
        "sub": user_id,
        "cid": company_id,
        "type": MFA_CHALLENGE_TYPE,
        "iat": now,
        "nbf": now,
        "exp": now + timedelta(minutes=MFA_CHALLENGE_MINUTES),
        "iss": settings.jwt_issuer,
        "aud": _mfa_audience(settings),
        "jti": uuid4().hex,
    }
    return jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm=settings.jwt_algorithm)


def decode_mfa_challenge(token: str, settings: Settings) -> tuple[str, str]:
    """Returns (user_id, company_id)."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            audience=_mfa_audience(settings),
            issuer=settings.jwt_issuer,
            options={"require": ["exp", "iat", "sub", "aud", "iss", "type"]},
            leeway=10,
        )
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError(
            "This sign-in attempt has expired. Please sign in again.", code="mfa_expired"
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise UnauthorizedError("Please sign in again.", code="invalid_mfa_challenge") from exc
    if payload.get("type") != MFA_CHALLENGE_TYPE or not payload.get("cid"):
        raise UnauthorizedError("Please sign in again.", code="invalid_mfa_challenge")
    return str(payload["sub"]), str(payload["cid"])


def generate_enrollment_code() -> str:
    """Human-typeable one-time code, e.g. WP-7KQ2-M9XD-4TRA (~60 bits)."""
    groups = ["".join(secrets.choice(_ENROLLMENT_ALPHABET) for _ in range(4)) for _ in range(3)]
    return "WP-" + "-".join(groups)


def normalise_enrollment_code(code: str) -> str:
    return code.strip().upper().replace(" ", "")


DEVICE_TOKEN_TYPE = "device"  # noqa: S105 - token kind, not a secret


@dataclass(frozen=True, slots=True)
class DeviceTokenClaims:
    device_id: str
    company_id: str
    employee_id: str
    expires_at: datetime


def device_audience(settings: Settings) -> str:
    """Agent tokens use their own audience, so they are never accepted as user tokens (and vice versa)."""
    return f"{settings.jwt_audience}:agent"


def generate_device_secret() -> str:
    return secrets.token_urlsafe(32)


def verify_token_hash(raw: str, expected_hash: str | None) -> bool:
    return expected_hash is not None and hmac.compare_digest(hash_token(raw), expected_hash)


def create_device_token(
    *, device_id: str, company_id: str, employee_id: str, settings: Settings
) -> tuple[str, datetime]:
    now = utcnow()
    expires_at = now + timedelta(minutes=settings.agent_token_expire_minutes)
    payload = {
        "sub": device_id,
        "cid": company_id,
        "eid": employee_id,
        "type": DEVICE_TOKEN_TYPE,
        "iat": now,
        "nbf": now,
        "exp": expires_at,
        "iss": settings.jwt_issuer,
        "aud": device_audience(settings),
        "jti": uuid4().hex,
    }
    token = jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm=settings.jwt_algorithm)
    return token, expires_at


def decode_device_token(token: str, settings: Settings) -> DeviceTokenClaims:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
            audience=device_audience(settings),
            issuer=settings.jwt_issuer,
            options={"require": ["exp", "iat", "sub", "aud", "iss", "type"]},
            leeway=10,
        )
    except jwt.ExpiredSignatureError as exc:
        raise UnauthorizedError("Device token has expired.", code="token_expired") from exc
    except jwt.InvalidTokenError as exc:
        raise UnauthorizedError("Invalid device token.", code="invalid_token") from exc
    if payload.get("type") != DEVICE_TOKEN_TYPE or not payload.get("cid") or not payload.get("eid"):
        raise UnauthorizedError("Invalid device token.", code="invalid_token")
    return DeviceTokenClaims(
        device_id=str(payload["sub"]),
        company_id=str(payload["cid"]),
        employee_id=str(payload["eid"]),
        expires_at=datetime.fromtimestamp(payload["exp"], tz=utcnow().tzinfo),
    )
