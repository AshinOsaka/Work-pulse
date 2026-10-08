"""Request throttling for credential and abuse-prone endpoints.

Fixed windows stored in MongoDB, so every API process shares the same counters. Keys combine the purpose with the
client address or the account being targeted, e.g. ``login-ip:203.0.113.9`` or ``login-account:ada@example.com``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import timedelta

from app.core.exceptions import TooManyRequestsError
from app.repositories.security import RateLimitRepository
from app.utils.time import utcnow


@dataclass(frozen=True, slots=True)
class Limit:
    name: str
    limit: int
    window_seconds: int
    message: str = "Too many attempts. Please wait a little and try again."


# Generous for people, tight for scripts.
LOGIN_PER_IP = Limit("login-ip", 100, 15 * 60)  # a whole office can share one address
LOGIN_FAILURES_PER_ACCOUNT = Limit(
    "login-account",
    10,
    15 * 60,
    "Too many failed sign-in attempts for this account. Try again in 15 minutes.",
)
MFA_FAILURES_PER_ACCOUNT = Limit(
    "mfa-account", 5, 15 * 60, "Too many incorrect codes. Try again in 15 minutes."
)
REGISTER_PER_IP = Limit("register-ip", 20, 60 * 60)
PASSWORD_RESET_PER_IP = Limit("reset-ip", 10, 60 * 60)
PASSWORD_RESET_PER_ACCOUNT = Limit("reset-account", 3, 60 * 60)
TOKEN_REDEEM_PER_IP = Limit("redeem-ip", 30, 15 * 60)
AGENT_SIGN_IN_PER_IP = Limit("agent-ip", 60, 15 * 60)
AGENT_FAILURES_PER_ACCOUNT = Limit(
    "agent-account",
    10,
    15 * 60,
    "Too many failed sign-in attempts for this account. Try again in 15 minutes.",
)


class Throttle:
    def __init__(self, buckets: RateLimitRepository, *, enabled: bool = True) -> None:
        self._buckets = buckets
        self._enabled = enabled

    @staticmethod
    def _window(limit: Limit, subject: str) -> tuple[str, int]:
        now = utcnow().timestamp()
        index = int(now // limit.window_seconds)
        retry_after = math.ceil((index + 1) * limit.window_seconds - now)
        return f"{limit.name}:{subject.lower()}:{index}", retry_after

    async def hit(self, limit: Limit, subject: str | None) -> None:
        """Count an attempt; refuse once the window's allowance is used up."""
        if not subject or not self._enabled:
            return
        key, retry_after = self._window(limit, subject)
        count = await self._buckets.increment(key, utcnow() + timedelta(seconds=retry_after))
        if count > limit.limit:
            raise TooManyRequestsError(limit.message, retry_after=retry_after)

    async def check(self, limit: Limit, subject: str | None) -> None:
        """Refuse if the allowance is already used up, without counting this attempt (failures are counted later)."""
        if not subject or not self._enabled:
            return
        key, retry_after = self._window(limit, subject)
        if await self._buckets.count(key) >= limit.limit:
            raise TooManyRequestsError(limit.message, retry_after=retry_after)

    async def fail(self, limit: Limit, subject: str | None) -> None:
        if subject and self._enabled:
            key, retry_after = self._window(limit, subject)
            await self._buckets.increment(key, utcnow() + timedelta(seconds=retry_after))

    async def clear(self, limit: Limit, subject: str | None) -> None:
        if subject:
            await self._buckets.clear(self._window(limit, subject)[0])
