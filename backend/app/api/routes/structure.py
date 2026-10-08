"""Departments and teams."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.deps import OrganizationServiceDep, RequestMetaDep
from app.auth.dependencies import require_permissions
from app.auth.permissions import Permission
from app.auth.principal import Principal
from app.schemas.common import ObjectIdStr
from app.schemas.organization import (
    DepartmentCreate,
    DepartmentOut,
    DepartmentUpdate,
    TeamCreate,
    TeamOut,
    TeamUpdate,
)

router = APIRouter(tags=["organization"])

CanView = Annotated[Principal, Depends(require_permissions(Permission.EMPLOYEE_VIEW))]
CanManage = Annotated[Principal, Depends(require_permissions(Permission.EMPLOYEE_MANAGE))]


# --------------------------------------------------------------------------- departments
@router.get("/departments", response_model=list[DepartmentOut])
async def list_departments(principal: CanView, service: OrganizationServiceDep) -> list[DepartmentOut]:
    return await service.list_departments(principal)


@router.post("/departments", response_model=DepartmentOut, status_code=status.HTTP_201_CREATED)
async def create_department(
    payload: DepartmentCreate, principal: CanManage, service: OrganizationServiceDep, meta: RequestMetaDep
) -> DepartmentOut:
    return await service.create_department(principal, payload, meta)


@router.get("/departments/{department_id}", response_model=DepartmentOut)
async def get_department(
    department_id: str, principal: CanView, service: OrganizationServiceDep
) -> DepartmentOut:
    return await service.get_department(principal, department_id)


@router.patch("/departments/{department_id}", response_model=DepartmentOut)
async def update_department(
    department_id: str,
    payload: DepartmentUpdate,
    principal: CanManage,
    service: OrganizationServiceDep,
    meta: RequestMetaDep,
) -> DepartmentOut:
    return await service.update_department(principal, department_id, payload, meta)


@router.delete("/departments/{department_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_department(
    department_id: str, principal: CanManage, service: OrganizationServiceDep, meta: RequestMetaDep
) -> Response:
    """Only empty departments (no employees, no teams) can be deleted."""
    await service.delete_department(principal, department_id, meta)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------- teams
@router.get("/teams", response_model=list[TeamOut])
async def list_teams(
    principal: CanView,
    service: OrganizationServiceDep,
    department_id: Annotated[ObjectIdStr | None, Query()] = None,
) -> list[TeamOut]:
    return await service.list_teams(principal, department_id)


@router.post("/teams", response_model=TeamOut, status_code=status.HTTP_201_CREATED)
async def create_team(
    payload: TeamCreate, principal: CanManage, service: OrganizationServiceDep, meta: RequestMetaDep
) -> TeamOut:
    return await service.create_team(principal, payload, meta)


@router.get("/teams/{team_id}", response_model=TeamOut)
async def get_team(team_id: str, principal: CanView, service: OrganizationServiceDep) -> TeamOut:
    return await service.get_team(principal, team_id)


@router.patch("/teams/{team_id}", response_model=TeamOut)
async def update_team(
    team_id: str,
    payload: TeamUpdate,
    principal: CanManage,
    service: OrganizationServiceDep,
    meta: RequestMetaDep,
) -> TeamOut:
    """Moving a team to another department moves its members with it."""
    return await service.update_team(principal, team_id, payload, meta)


@router.delete("/teams/{team_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_team(
    team_id: str, principal: CanManage, service: OrganizationServiceDep, meta: RequestMetaDep
) -> Response:
    """Only teams without members can be deleted."""
    await service.delete_team(principal, team_id, meta)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
