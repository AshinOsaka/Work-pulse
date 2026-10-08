"""Which ICE (STUN/TURN) servers live-viewing peers get.

WorkPulse only relays signalling; video goes peer to peer. STUN lets each side learn its public address, which is
enough on the same network and through most home and office NATs. TURN relays media when a direct path is
impossible (strict corporate firewalls, symmetric NAT). It is optional: with `LIVE_TURN_URLS` and `LIVE_TURN_SECRET`
empty, peers get STUN only and everything else keeps working.

TURN credentials follow the TURN REST API used by coturn and most hosted TURN services: a short-lived username
(`<expiry>:<identity>`) and an HMAC-SHA1 of it with the shared secret, so the TURN server needs no user database.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time

from app.core.config import Settings
from app.schemas.live import IceServer


def _split(urls: str) -> list[str]:
    return [u.strip() for u in urls.split(",") if u.strip()]


class IceServerProvider:
    def __init__(self, settings: Settings) -> None:
        self._stun = _split(settings.live_stun_urls)
        self._turn = _split(settings.live_turn_urls)
        self._secret = (
            settings.live_turn_secret.get_secret_value().encode() if settings.live_turn_secret else None
        )
        self._ttl = settings.live_turn_ttl_seconds

    @property
    def turn_enabled(self) -> bool:
        return bool(self._turn) and self._secret is not None

    def servers(self, identity: str) -> list[IceServer]:
        """STUN as configured, plus TURN with fresh credentials for `identity` when TURN is configured."""
        servers: list[IceServer] = []
        if self._stun:
            servers.append(IceServer(urls=self._stun))
        if self.turn_enabled and self._secret is not None:
            username = f"{int(time.time()) + self._ttl}:{identity}"
            digest = hmac.new(self._secret, username.encode(), hashlib.sha1).digest()
            servers.append(
                IceServer(urls=self._turn, username=username, credential=base64.b64encode(digest).decode())
            )
        return servers
