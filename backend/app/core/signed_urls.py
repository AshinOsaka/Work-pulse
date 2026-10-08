"""Short-lived, viewer-bound URLs for private files.

Browsers load images with plain GET requests that can't carry the bearer
token, so the API hands out URLs signed with HMAC-SHA256. A signature covers
the tenant, the viewer, the object, the variant and the expiry. It is useless
after a few minutes, for any other object, or once the viewer loses access
(re-checked on every fetch).
"""

from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass
from urllib.parse import urlencode


@dataclass(frozen=True, slots=True)
class SignedFileClaims:
    company_id: str
    user_id: str
    object_id: str
    variant: str
    expires: int


class UrlSigner:
    def __init__(self, key: bytes, ttl_seconds: int) -> None:
        self._key = key
        self._ttl = ttl_seconds

    def _signature(self, claims: SignedFileClaims) -> str:
        message = (
            f"v1|{claims.company_id}|{claims.user_id}|{claims.object_id}|{claims.variant}|{claims.expires}"
        )
        return hmac.new(self._key, message.encode(), hashlib.sha256).hexdigest()

    def sign(self, path: str, *, company_id: str, user_id: str, object_id: str, variant: str) -> str:
        expires = int(time.time()) + self._ttl
        claims = SignedFileClaims(company_id, user_id, object_id, variant, expires)
        query = urlencode({"c": company_id, "u": user_id, "e": expires, "s": self._signature(claims)})
        return f"{path}?{query}"

    def verify(
        self, *, company_id: str, user_id: str, object_id: str, variant: str, expires: int, signature: str
    ) -> bool:
        if expires < time.time():
            return False
        expected = self._signature(SignedFileClaims(company_id, user_id, object_id, variant, expires))
        return hmac.compare_digest(expected, signature)
