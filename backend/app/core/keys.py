"""Purpose-specific keys.

Each subsystem gets its own key, derived with HKDF under a distinct label, so a
key leaked from one purpose (say, signing image URLs) can't forge tokens or
decrypt stored objects. An explicit `STORAGE_ENCRYPTION_KEY` takes precedence for
object encryption, so it can be rotated independently of `JWT_SECRET`.
"""

from __future__ import annotations

import base64
import binascii

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.core.config import Settings


def derive_key(settings: Settings, purpose: str) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=b"workpulse.v1", info=purpose.encode()).derive(
        settings.jwt_secret.get_secret_value().encode()
    )


def storage_key(settings: Settings) -> bytes:
    if settings.storage_encryption_key is not None:
        raw = settings.storage_encryption_key.get_secret_value()
        try:
            key = base64.b64decode(raw, validate=True)
        except binascii.Error as exc:
            raise ValueError("STORAGE_ENCRYPTION_KEY must be base64 of 32 random bytes.") from exc
        if len(key) != 32:
            raise ValueError("STORAGE_ENCRYPTION_KEY must be base64 of 32 random bytes.")
        return key
    return derive_key(settings, "object-storage")


def url_signing_key(settings: Settings) -> bytes:
    return derive_key(settings, "screenshot-urls")


def mfa_key(settings: Settings) -> bytes:
    """Encrypts two-step verification secrets. Derived from the storage key: with `STORAGE_ENCRYPTION_KEY` set, rotating
    `JWT_SECRET` (e.g. to invalidate every session) doesn't lock everyone out of their authenticator app."""
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=b"workpulse.v1", info=b"mfa-secrets").derive(
        storage_key(settings)
    )
