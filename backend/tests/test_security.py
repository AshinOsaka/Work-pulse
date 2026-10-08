from __future__ import annotations

from datetime import timedelta

import jwt
import pytest

from app.core.config import Settings
from app.core.exceptions import UnauthorizedError
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.utils.time import utcnow


@pytest.fixture
def unit_settings() -> Settings:
    return Settings(jwt_secret="unit-test-secret-key-0123456789-abcdef")  # type: ignore[arg-type]


def test_password_hash_roundtrip() -> None:
    hashed = hash_password("CorrectHorse42")
    assert hashed != "CorrectHorse42"
    assert verify_password(hashed, "CorrectHorse42")
    assert not verify_password(hashed, "wrong-password1")
    assert not verify_password("not-a-hash", "CorrectHorse42")


def test_access_token_roundtrip(unit_settings: Settings) -> None:
    token, expires_at = create_access_token(
        user_id="u1", company_id="c1", role="EMPLOYEE", settings=unit_settings, session_id="s1"
    )
    claims = decode_access_token(token, unit_settings)
    assert claims.subject == "u1"
    assert claims.company_id == "c1"
    assert claims.role == "EMPLOYEE"
    assert expires_at > utcnow()


def test_expired_token_is_rejected(unit_settings: Settings) -> None:
    past = utcnow() - timedelta(hours=1)
    token = jwt.encode(
        {
            "sub": "u1",
            "cid": "c1",
            "type": "access",
            "iat": past,
            "exp": past + timedelta(minutes=1),
            "iss": unit_settings.jwt_issuer,
            "aud": unit_settings.jwt_audience,
        },
        unit_settings.jwt_secret.get_secret_value(),
        algorithm="HS256",
    )
    with pytest.raises(UnauthorizedError) as exc:
        decode_access_token(token, unit_settings)
    assert exc.value.code == "token_expired"


def test_tampered_or_foreign_token_is_rejected(unit_settings: Settings) -> None:
    token, _ = create_access_token(
        user_id="u1", company_id="c1", role="EMPLOYEE", settings=unit_settings, session_id="s1"
    )
    with pytest.raises(UnauthorizedError):
        decode_access_token(token[:-2] + "xx", unit_settings)

    other = Settings(jwt_secret="another-secret-key-0123456789-abcdefgh")  # type: ignore[arg-type]
    with pytest.raises(UnauthorizedError):
        decode_access_token(token, other)


def test_weak_secret_is_refused() -> None:
    with pytest.raises(ValueError):
        Settings(jwt_secret="short")  # type: ignore[arg-type]


def test_token_hash_is_deterministic() -> None:
    assert hash_token("abc") == hash_token("abc")
    assert hash_token("abc") != hash_token("abd")
