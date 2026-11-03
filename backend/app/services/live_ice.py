"""Which ICE (STUN/TURN) servers live-viewing peers get.

WorkPulse only relays signalling; video goes peer to peer. STUN lets each side learn its public address, which is
enough on the same network and through most home and office NATs. TURN relays media when a direct path is
impossible (strict corporate firewalls, symmetric NAT). It is optional: with no TURN configured, peers get STUN
only and everything else keeps working.

Two TURN providers are supported, picked by configuration:

* **Cloudflare Realtime TURN** (``CLOUDFLARE_TURN_KEY_ID`` + ``CLOUDFLARE_TURN_API_TOKEN``): WorkPulse asks
  Cloudflare's API for short-lived ICE servers and caches them for all sessions until shortly before they expire.
* **coturn / TURN REST API** (``LIVE_TURN_URLS`` + ``LIVE_TURN_SECRET``): a short-lived username
  (``<expiry>:<identity>``) and an HMAC-SHA1 of it with the shared secret, minted locally per session.

If both are set, Cloudflare wins.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import logging
import time

import httpx

from app.core.config import Settings
from app.schemas.live import IceServer

logger = logging.getLogger(__name__)

_CLOUDFLARE_URL = "https://rtc.live.cloudflare.com/v1/turn/keys/{key_id}/credentials/generate-ice-servers"


def _split(urls: str) -> list[str]:
    return [u.strip() for u in urls.split(",") if u.strip()]


def _as_list(urls: object) -> list[str]:
    if isinstance(urls, str):
        return [urls]
    if isinstance(urls, list):
        return [str(u) for u in urls]
    return []


class IceServerProvider:
    def __init__(self, settings: Settings) -> None:
        self._stun = _split(settings.live_stun_urls)
        self._turn = _split(settings.live_turn_urls)
        self._secret = (
            settings.live_turn_secret.get_secret_value().encode() if settings.live_turn_secret else None
        )
        self._ttl = settings.live_turn_ttl_seconds
        self._cf_key = settings.cloudflare_turn_key_id.strip()
        self._cf_token = (
            settings.cloudflare_turn_api_token.get_secret_value()
            if settings.cloudflare_turn_api_token
            else None
        )
        # Cloudflare credentials are reusable by any peer until they expire, so one fetch serves every session.
        self._cf_cache: list[IceServer] = []
        self._cf_expiry = 0.0
        self._cf_lock = asyncio.Lock()

    @property
    def turn_enabled(self) -> bool:
        return bool(self._turn) and self._secret is not None

    @property
    def cloudflare_enabled(self) -> bool:
        return bool(self._cf_key) and self._cf_token is not None

    async def servers(self, identity: str) -> list[IceServer]:
        """STUN as configured, plus TURN (Cloudflare or coturn) when configured."""
        servers: list[IceServer] = []
        if self._stun:
            servers.append(IceServer(urls=self._stun))
        if self.cloudflare_enabled:
            servers.extend(await self._cloudflare_servers())
        elif self.turn_enabled and self._secret is not None:
            username = f"{int(time.time()) + self._ttl}:{identity}"
            digest = hmac.new(self._secret, username.encode(), hashlib.sha1).digest()
            servers.append(
                IceServer(urls=self._turn, username=username, credential=base64.b64encode(digest).decode())
            )
        return servers

    async def _cloudflare_servers(self) -> list[IceServer]:
        now = time.time()
        if self._cf_cache and now < self._cf_expiry:
            return self._cf_cache
        async with self._cf_lock:
            if self._cf_cache and time.time() < self._cf_expiry:
                return self._cf_cache
            ttl = min(self._ttl, 86_400)
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(
                        _CLOUDFLARE_URL.format(key_id=self._cf_key),
                        headers={
                            "Authorization": f"Bearer {self._cf_token}",
                            "Content-Type": "application/json",
                        },
                        json={"ttl": ttl},
                    )
                resp.raise_for_status()
                raw = resp.json().get("iceServers")
                items = raw if isinstance(raw, list) else [raw] if raw else []
                parsed = [
                    IceServer(
                        urls=_as_list(item.get("urls")),
                        username=item.get("username"),
                        credential=item.get("credential"),
                    )
                    for item in items
                    if isinstance(item, dict) and item.get("urls")
                ]
                if parsed:
                    self._cf_cache = parsed
                    # Refresh well before expiry so sessions never get stale credentials.
                    self._cf_expiry = time.time() + ttl * 0.75
                return parsed or self._cf_cache
            except Exception:
                logger.warning("Cloudflare TURN credential fetch failed; using STUN only this time", exc_info=True)
                return self._cf_cache
