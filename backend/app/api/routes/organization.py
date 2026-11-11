from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from app.api.deps import (
    CompanyRepoDep,
    OrganizationServiceDep,
    PermissionRepoDep,
    RequestMetaDep,
    RoleRepoDep,
    RoleServiceDep,
    UserRepoDep,
    tell_user_session_changed,
)
from app.auth.dependencies import CurrentPrincipal, require_permissions
from app.auth.effective import BUILT_IN_KEYS, EDITABLE_BUILT_IN
from app.auth.permissions import Permission, Role, permissions_for_role
from app.auth.principal import Principal
from app.core.exceptions import NotFoundError
from app.models.role import RoleDocument
from app.schemas.company import CompanyOut, CompanyUpdate
from app.schemas.role import PermissionOut, RoleCreate, RoleOut, RolesResponse, RoleUpdate

router = APIRouter(tags=["organization"])


@router.get("/companies/current", response_model=CompanyOut)
async def current_company(principal: CurrentPrincipal, companies: CompanyRepoDep) -> CompanyOut:
    company = await companies.get_by_id(principal.company_id)
    if company is None:
        raise NotFoundError("Workspace not found.")
    return CompanyOut.from_model(company)


@router.patch("/companies/current", response_model=CompanyOut, summary="Update the workspace profile")
async def update_company(
    payload: CompanyUpdate,
    principal: Annotated[Principal, Depends(require_permissions(Permission.POLICY_MANAGE))],
    service: OrganizationServiceDep,
    meta: RequestMetaDep,
) -> CompanyOut:
    return CompanyOut.from_model(await service.update_company(principal, payload, meta))


def _role_out(r: RoleDocument) -> RoleOut:
    base = Role(r.base_level) if r.base_level in BUILT_IN_KEYS else Role.EMPLOYEE
    return RoleOut(
        key=r.key,
        name=r.name,
        description=r.description,
        level=r.level,
        base_level=r.base_level,
        is_system=r.is_system,
        permissions=r.permissions,
        default_permissions=sorted(p.value for p in permissions_for_role(base)),
        customized=r.is_system and r.company_id is not None,
        editable=(not r.is_system) or r.key in EDITABLE_BUILT_IN,
    )


CanManageRoles = Annotated[Principal, Depends(require_permissions(Permission.USER_MANAGE))]


@router.get("/roles", response_model=RolesResponse, summary="Roles and the permission catalogue")
async def list_roles(
    principal: CanManageRoles,
    roles: RoleRepoDep,
    permissions: PermissionRepoDep,
) -> RolesResponse:
    role_docs = await roles.list_for_company(principal.company_id)
    permission_docs = await permissions.list_all()
    return RolesResponse(
        roles=[_role_out(r) for r in role_docs],
        permissions=[
            PermissionOut(key=p.key, name=p.name, description=p.description, category=p.category)
            for p in permission_docs
        ],
    )


@router.post("/roles", response_model=RoleOut, status_code=status.HTTP_201_CREATED, summary="Create a custom role")
async def create_role(
    payload: RoleCreate, principal: CanManageRoles, service: RoleServiceDep, meta: RequestMetaDep
) -> RoleOut:
    return _role_out(await service.create(principal, payload, meta))


@router.patch("/roles/{key}", response_model=RoleOut, summary="Rename a custom role, or change its level or permissions")
async def update_role(
    key: str,
    payload: RoleUpdate,
    principal: CanManageRoles,
    service: RoleServiceDep,
    users: UserRepoDep,
    meta: RequestMetaDep,
    request: Request,
) -> RoleOut:
    updated = await service.update(principal, key, payload, meta)
    # Everyone with this role sees their new menu and pages at once.
    members = {"$or": [{"role_key": key}, {"role_key": None, "role": key}]}
    for member in await users.find_many(principal.company_id, members, sort=None, limit=5000):
        await tell_user_session_changed(request, principal.company_id, str(member.id))
    return _role_out(updated)


@router.delete("/roles/{key}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a custom role")
async def delete_role(
    key: str, principal: CanManageRoles, service: RoleServiceDep, meta: RequestMetaDep
) -> None:
    await service.delete(principal, key, meta)
