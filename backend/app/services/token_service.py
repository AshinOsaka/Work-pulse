"""Access/refresh token issuance with sessions, refresh-token rotation and reuse detection.

* Sessions: each sign-in creates an `AuthSession`. Access tokens name it (`sid`) and every request checks it is still
  active, so signing out, revoking a session, changing the password or detected token theft take effect at once.
* Access tokens: short-lived JWTs, kept in memory by the browser.
* Refresh tokens: opaque random strings delivered as an httpOnly cookie, stored as SHA-256 digests. Each use rotates
  the token; presenting an already-rotated token (outside a short grace window for concurrent tabs) is treated as
  theft and revokes the whole session.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from bson import ObjectId

from app.core.config import Settings
from app.core.exceptions import UnauthorizedError
from app.core.security import create_access_token, generate_opaque_token, hash_token
from app.models.auth_tokens import RefreshToken
from app.models.security import AuthSession
from app.models.user import User
from app.repositories.auth_tokens import RefreshTokenRepository
from app.repositories.security import AuthSessionRepository
from app.services.context import RequestMeta
from app.utils.time import utcnow

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class IssuedTokens:
    access_token: str
    access_expires_at: datetime
    refresh_token: str
    refresh_expires_at: datetime
    session_id: ObjectId

    @property
    def expires_in(self) -> int:
        return max(0, int((self.access_expires_at - utcnow()).total_seconds()))


def session_of(record: RefreshToken) -> ObjectId | None:
    """Refresh-token families are named after their session (older families predate sessions)."""
    return ObjectId(record.family_id) if ObjectId.is_valid(record.family_id) else None


class TokenService:
    def __init__(
        self, settings: Settings, refresh_tokens: RefreshTokenRepository, sessions: AuthSessionRepository
    ) -> None:
        self._settings = settings
        self._refresh_tokens = refresh_tokens
        self._sessions = sessions

    @property
    def sessions(self) -> AuthSessionRepository:
        return self._sessions

    async def issue(
        self, user: User, meta: RequestMeta, *, session_id: ObjectId | None = None, mfa: bool = False
    ) -> IssuedTokens:
        refresh_expires_at = utcnow() + timedelta(days=self._settings.refresh_token_expire_days)
        agent = (meta.user_agent or "")[:512] or None
        if session_id is None:
            session = AuthSession(
                company_id=user.company_id,
                user_id=user.id,
                expires_at=refresh_expires_at,
                last_seen_at=utcnow(),
                user_agent=agent,
                ip_address=meta.ip_address,
                mfa=mfa,
            )
            await self._sessions.create(user.company_id, session)
            session_id = session.id
        else:
            await self._sessions.touch(
                session_id, expires_at=refresh_expires_at, ip=meta.ip_address, agent=agent
            )

        access_token, access_expires_at = create_access_token(
            user_id=str(user.id),
            company_id=str(user.company_id),
            role=user.role.value,
            settings=self._settings,
            session_id=str(session_id),
        )
        raw_refresh = generate_opaque_token()
        await self._refresh_tokens.create(
            user.company_id,
            RefreshToken(
                company_id=user.company_id,
                user_id=user.id,
                token_hash=hash_token(raw_refresh),
                family_id=str(session_id),
                expires_at=refresh_expires_at,
                user_agent=agent,
                ip_address=meta.ip_address,
            ),
        )
        return IssuedTokens(access_token, access_expires_at, raw_refresh, refresh_expires_at, session_id)

    async def consume(self, raw_refresh: str) -> tuple[RefreshToken, ObjectId | None]:
        """Validate and atomically rotate a refresh token. Returns its record and its still-active session (None for a
        family that predates sessions: the caller starts a new session)."""
        record = await self._refresh_tokens.find_by_hash(hash_token(raw_refresh))
        if record is None:
            raise UnauthorizedError("Your session is invalid or has expired.", code="invalid_refresh_token")

        now = utcnow()
        session_id = session_of(record)
        if record.revoked_at is not None:
            grace = timedelta(seconds=self._settings.refresh_reuse_grace_seconds)
            if record.revoked_reason == "rotated" and now - record.revoked_at <= grace:
                # Benign race, e.g. two tabs refreshing simultaneously.
                raise UnauthorizedError("Session was already refreshed.", code="refresh_token_rotated")
            if record.revoked_reason == "rotated":
                revoked = await self._refresh_tokens.revoke_family(record.family_id, "reuse_detected")
                if session_id is not None:
                    await self._sessions.revoke_unscoped(session_id, "reuse_detected")
                logger.warning(
                    "Refresh token reuse detected for user %s; revoked %d session token(s)",
                    record.user_id,
                    revoked,
                )
                raise UnauthorizedError("Your session is no longer valid.", code="refresh_token_reused")
            raise UnauthorizedError("Your session has ended. Please sign in again.", code="session_revoked")

        if record.expires_at <= now:
            raise UnauthorizedError("Your session has expired.", code="refresh_token_expired")
        if session_id is not None and await self._sessions.find_active(session_id) is None:
            await self._refresh_tokens.revoke_family(record.family_id, "session_revoked")
            raise UnauthorizedError("Your session has ended. Please sign in again.", code="session_revoked")

        if not await self._refresh_tokens.consume(record.id):
            raise UnauthorizedError("Session was already refreshed.", code="refresh_token_rotated")
        return record, session_id

    async def revoke(self, raw_refresh: str, reason: str = "logout") -> RefreshToken | None:
        """Sign out the session the refresh token belongs to."""
        record = await self._refresh_tokens.find_by_hash(hash_token(raw_refresh))
        if record is None:
            return None
        await self._refresh_tokens.revoke_family(record.family_id, reason)
        session_id = session_of(record)
        if session_id is not None:
            await self._sessions.revoke(record.company_id, session_id, reason)
        return record

    async def revoke_session(self, user: User, session_id: ObjectId, reason: str) -> bool:
        if not await self._sessions.revoke(user.company_id, session_id, reason, user_id=user.id):
            return False
        await self._refresh_tokens.revoke_family(str(session_id), reason)
        return True

    async def revoke_all(self, user: User, reason: str, keep: ObjectId | None = None) -> list[ObjectId]:
        """End every session of the user (except `keep`). Returns the ended session ids."""
        ended = await self._sessions.revoke_all(user.company_id, user.id, reason, keep=keep)
        await self._refresh_tokens.revoke_all_for_user(
            user.company_id, user.id, reason, keep_family=str(keep) if keep else None
        )
        return ended
