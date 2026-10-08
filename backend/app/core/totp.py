"""Time-based one-time passwords (RFC 6238, the scheme every authenticator app speaks) and recovery codes.

Secrets are encrypted at rest (AES-GCM under a purpose-specific key); recovery codes are stored only as hashes.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import struct
from urllib.parse import quote, urlencode

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

PERIOD = 30
DIGITS = 6
#: Accept the previous and next 30-second step too (clock drift between phone and server).
DRIFT_STEPS = 1
RECOVERY_CODE_COUNT = 10
_RECOVERY_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"


def new_secret() -> str:
    """160 random bits, base32 without padding (what authenticator apps expect)."""
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _key(secret: str) -> bytes:
    return base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)


def code_at(secret: str, step: int, digits: int = DIGITS, digest: str = "sha1") -> str:
    mac = hmac.new(_key(secret), struct.pack(">Q", step), digest).digest()
    offset = mac[-1] & 0x0F
    value = struct.unpack(">I", mac[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10**digits).zfill(digits)


def current_step(now: float) -> int:
    return int(now // PERIOD)


def matching_step(secret: str, code: str, now: float, last_used_step: int | None = None) -> int | None:
    """The time step the code belongs to, or None. A step at or before `last_used_step` is refused (no replay)."""
    code = code.strip().replace(" ", "")
    if len(code) != DIGITS or not code.isdigit():
        return None
    step = current_step(now)
    for candidate in range(step - DRIFT_STEPS, step + DRIFT_STEPS + 1):
        if last_used_step is not None and candidate <= last_used_step:
            continue
        if hmac.compare_digest(code_at(secret, candidate), code):
            return candidate
    return None


def provisioning_uri(secret: str, account: str, issuer: str) -> str:
    label = quote(f"{issuer}:{account}")
    query = urlencode(
        {"secret": secret, "issuer": issuer, "algorithm": "SHA1", "digits": DIGITS, "period": PERIOD}
    )
    return f"otpauth://totp/{label}?{query}"


def new_recovery_codes() -> list[str]:
    """Ten single-use codes like `k7mq-2xpd`, shown once."""
    return [
        "-".join("".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(4)) for _ in range(2))
        for _ in range(RECOVERY_CODE_COUNT)
    ]


def normalise_recovery_code(code: str) -> str:
    raw = code.strip().lower().replace(" ", "").replace("-", "")
    return f"{raw[:4]}-{raw[4:]}" if len(raw) == 8 else raw


def hash_recovery_code(code: str) -> str:
    return hashlib.sha256(normalise_recovery_code(code).encode()).hexdigest()


def encrypt_secret(key: bytes, secret: str, user_id: str) -> str:
    """AES-GCM, bound to the user (the id is the associated data), so a secret can't be copied to another account."""
    nonce = os.urandom(12)
    sealed = AESGCM(key).encrypt(nonce, secret.encode(), user_id.encode())
    return base64.b64encode(nonce + sealed).decode()


def decrypt_secret(key: bytes, sealed: str, user_id: str) -> str:
    raw = base64.b64decode(sealed)
    return AESGCM(key).decrypt(raw[:12], raw[12:], user_id.encode()).decode()
