"""Authentication & authorization dependencies.

Usage::

    @router.get("/reports", dependencies=[Depends(require_permissions(Permission.REPORT_VIEW))])
    async def reports(principal: CurrentPrincipal): ...
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pymongo.asynchronous.database import AsyncDatabase

from app.auth.permissions import Permission, Role, permissions_for_role
from app.auth.principal import Principal
from app.core.config import Settings
from app.core.dependencies import DbDep, SettingsDep
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import decode_access_token
from app.models.user import UserStatus
from app.repositories.security import AuthSessionRepository
from app.repositories.user import UserRepository

_bearer = HTTPBearer(auto_error=False, description="JWT access token")


async def resolve_principal(token: str, settings: Settings, db: AsyncDatabase[dict[str, Any]]) -> Principal:
    """Validate an access token and load the current user (shared by HTTP and WebSocket)."""
    claims = decode_access_token(token, settings)
    try:
        user_id, company_id = ObjectId(claims.subject), ObjectId(claims.company_id)
        session_id = ObjectId(claims.session_id)
    except (InvalidId, TypeError) as exc:
        raise UnauthorizedError("Invalid access token.", code="invalid_token") from exc

    # The session is checked on each request, so signing out (here or remotely) takes effect immediately.
    session = await AuthSessionRepository(db).find_active(session_id)
    if session is None or session.user_id != user_id or session.company_id != company_id:
        raise UnauthorizedError("Your session has ended. Please sign in again.", code="session_revoked")
    # Loading the user on each request means suspensions and role changes apply immediately.
    user = await UserRepository(db).get_by_id(company_id, user_id)
    if user is None or user.status != UserStatus.ACTIVE:
        raise UnauthorizedError("Your account is not active.", code="inactive_account")
    return Principal(user=user, permissions=permissions_for_role(user.role), session_id=session_id)


async def get_current_principal(
    settings: SettingsDep,
    db: DbDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Principal:
    if credentials is None:
        raise UnauthorizedError("Authentication required.", code="not_authenticated")
    return await resolve_principal(credentials.credentials, settings, db)


CurrentPrincipal = Annotated[Principal, Depends(get_current_principal)]


def require_permissions(*required: Permission) -> Callable[..., Awaitable[Principal]]:
    async def dependency(principal: CurrentPrincipal) -> Principal:
        missing = [p.value for p in required if p not in principal.permissions]
        if missing:
            raise ForbiddenError(
                "You do not have permission to perform this action.",
                code="insufficient_permissions",
                details={"missing": missing},
            )
        return principal

    return dependency


def require_roles(*roles: Role) -> Callable[..., Awaitable[Principal]]:
    async def dependency(principal: CurrentPrincipal) -> Principal:
        if principal.role not in roles:
            raise ForbiddenError("Your role does not allow this action.", code="insufficient_role")
        return principal

    return dependency
