from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import (
    CompanyRepoDep,
    OrganizationServiceDep,
    PermissionRepoDep,
    RequestMetaDep,
    RoleRepoDep,
    RoleServiceDep,
)
from app.auth.dependencies import CurrentPrincipal, require_permissions
from app.auth.permissions import Permission
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
    return RoleOut(
        key=r.key,
        name=r.name,
        description=r.description,
        level=r.level,
        base_level=r.base_level,
        is_system=r.is_system,
        permissions=r.permissions,
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


@router.patch("/roles/{key}", response_model=RoleOut, summary="Rename a custom role or change its base level")
async def update_role(
    key: str, payload: RoleUpdate, principal: CanManageRoles, service: RoleServiceDep, meta: RequestMetaDep
) -> RoleOut:
    return _role_out(await service.update(principal, key, payload, meta))


@router.delete("/roles/{key}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a custom role")
async def delete_role(
    key: str, principal: CanManageRoles, service: RoleServiceDep, meta: RequestMetaDep
) -> None:
    await service.delete(principal, key, meta)
