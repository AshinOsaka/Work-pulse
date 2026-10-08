from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import (
    CompanyRepoDep,
    OrganizationServiceDep,
    PermissionRepoDep,
    RequestMetaDep,
    RoleRepoDep,
)
from app.auth.dependencies import CurrentPrincipal, require_permissions
from app.auth.permissions import Permission
from app.auth.principal import Principal
from app.core.exceptions import NotFoundError
from app.schemas.company import CompanyOut, CompanyUpdate
from app.schemas.role import PermissionOut, RoleOut, RolesResponse

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


@router.get("/roles", response_model=RolesResponse, summary="Roles and the permission catalogue")
async def list_roles(
    principal: Annotated[Principal, Depends(require_permissions(Permission.USER_MANAGE))],
    roles: RoleRepoDep,
    permissions: PermissionRepoDep,
) -> RolesResponse:
    role_docs = await roles.list_for_company(principal.company_id)
    permission_docs = await permissions.list_all()
    return RolesResponse(
        roles=[
            RoleOut(
                key=r.key,
                name=r.name,
                description=r.description,
                level=r.level,
                is_system=r.is_system,
                permissions=r.permissions,
            )
            for r in role_docs
        ],
        permissions=[
            PermissionOut(key=p.key, name=p.name, description=p.description, category=p.category)
            for p in permission_docs
        ],
    )
