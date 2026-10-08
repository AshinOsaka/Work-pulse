from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import (
    AuthServiceDep,
    BumpAnalytics,
    EmployeeRepoDep,
    MfaServiceDep,
    RequestMetaDep,
    UserAdminServiceDep,
    UserRepoDep,
)
from app.auth.dependencies import CurrentPrincipal, require_permissions
from app.auth.permissions import Permission, Role, can_assign_role
from app.auth.principal import Principal
from app.core.exceptions import BadRequestError, ForbiddenError, NotFoundError
from app.schemas.auth import SessionsRevokedResponse
from app.schemas.common import Page
from app.schemas.user import RoleUpdateRequest, UpdateProfileRequest, UserAdminOut, UserOut
from app.services.helpers import parse_id

router = APIRouter(prefix="/users", tags=["users"])

CanManageUsers = Annotated[Principal, Depends(require_permissions(Permission.USER_MANAGE))]


@router.patch("/me", response_model=UserOut, summary="Update the current user's profile")
async def update_me(
    payload: UpdateProfileRequest, principal: CurrentPrincipal, users: UserRepoDep, employees: EmployeeRepoDep
) -> UserOut:
    user = await users.update_by_id(principal.company_id, principal.user_id, {"full_name": payload.full_name})
    if user is None:
        raise NotFoundError("User not found.")
    if user.employee_id:
        await employees.update_by_id(principal.company_id, user.employee_id, {"full_name": payload.full_name})
    return UserOut.from_model(user)


@router.get("", response_model=Page[UserAdminOut], summary="Workspace members and their roles")
async def list_users(
    principal: CanManageUsers,
    service: UserAdminServiceDep,
    search: Annotated[str | None, Query(max_length=100)] = None,
    role: Role | None = None,
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> Page[UserAdminOut]:
    return await service.list_users(principal, search=search, role=role, page=page, page_size=page_size)


@router.patch("/{user_id}/role", response_model=UserAdminOut, dependencies=[BumpAnalytics])
async def change_user_role(
    user_id: str,
    payload: RoleUpdateRequest,
    principal: CanManageUsers,
    service: UserAdminServiceDep,
    meta: RequestMetaDep,
) -> UserAdminOut:
    """Assign a role. You cannot change your own role, grant a role above your own,
    or demote the last active Company Admin."""
    return await service.change_role(principal, user_id, payload.role, meta)


@router.post("/{user_id}/sessions/revoke", response_model=SessionsRevokedResponse)
async def revoke_user_sessions(
    user_id: str, principal: CanManageUsers, users: UserRepoDep, service: AuthServiceDep, meta: RequestMetaDep
) -> SessionsRevokedResponse:
    """Sign someone out everywhere (lost device, departure, suspected compromise). Audited."""
    target = await users.get_by_id(
        principal.company_id, parse_id(user_id, not_found="User not found.", code="user_not_found")
    )
    if target is None:
        raise NotFoundError("User not found.", code="user_not_found")
    if target.id == principal.user_id:
        raise BadRequestError(
            "Use your own security settings to sign yourself out.", code="cannot_revoke_own_sessions"
        )
    if not can_assign_role(principal.role, target.role):
        raise ForbiddenError("You cannot manage this account.", code="role_not_assignable")
    return SessionsRevokedResponse(revoked=await service.revoke_user_sessions(principal.user, target, meta))


@router.post("/{user_id}/mfa/reset", response_model=UserAdminOut)
async def reset_user_mfa(
    user_id: str, principal: CanManageUsers, mfa: MfaServiceDep, meta: RequestMetaDep
) -> UserAdminOut:
    """Turn off two-step verification for someone who lost their phone and recovery codes. Audited."""
    return UserAdminOut.from_user(await mfa.reset_for(principal, user_id, meta))
