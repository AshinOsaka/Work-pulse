from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import BumpAnalytics, DeviceServiceDep, EmployeeServiceDep, RequestMetaDep
from app.auth.dependencies import CurrentPrincipal, require_permissions
from app.auth.permissions import Permission
from app.auth.principal import Principal
from app.schemas.common import Page
from app.schemas.organization import (
    DeviceCreate,
    DeviceOut,
    DeviceRegistered,
    EmployeeCreate,
    EmployeeDetailOut,
    EmployeeListParams,
    EmployeeOut,
    EmployeeRef,
    EmployeeStatusUpdate,
    EmployeeUpdate,
    InviteRequest,
    PeopleSummary,
)

router = APIRouter(tags=["people"])

CanView = Annotated[Principal, Depends(require_permissions(Permission.EMPLOYEE_VIEW))]
CanManage = Annotated[Principal, Depends(require_permissions(Permission.EMPLOYEE_MANAGE))]


@router.get(
    "/people/summary", response_model=PeopleSummary, summary="Head-count overview within the caller's scope"
)
async def people_summary(principal: CanView, service: EmployeeServiceDep) -> PeopleSummary:
    return await service.summary(principal)


@router.get("/employees", response_model=Page[EmployeeOut])
async def list_employees(
    principal: CanView, service: EmployeeServiceDep, params: Annotated[EmployeeListParams, Query()]
) -> Page[EmployeeOut]:
    """Search, filter, sort and paginate employees visible to the caller."""
    return await service.list_employees(principal, params)


@router.get("/employees/options", response_model=list[EmployeeRef], summary="Employees for pickers")
async def employee_options(
    principal: CanView,
    service: EmployeeServiceDep,
    search: Annotated[str | None, Query(max_length=100)] = None,
) -> list[EmployeeRef]:
    return await service.options(principal, search)


@router.get("/employees/managers", response_model=list[EmployeeRef], summary="Managers of visible employees")
async def employee_managers(principal: CanView, service: EmployeeServiceDep) -> list[EmployeeRef]:
    return await service.managers(principal)


@router.post("/employees", response_model=EmployeeDetailOut, status_code=status.HTTP_201_CREATED)
async def create_employee(
    payload: EmployeeCreate, principal: CanManage, service: EmployeeServiceDep, meta: RequestMetaDep
) -> EmployeeDetailOut:
    """Create an employee; with `invite=true` also create an account and send an invitation (needs USER_MANAGE)."""
    return await service.create(principal, payload, meta)


@router.get("/employees/{employee_id}", response_model=EmployeeDetailOut)
async def get_employee(
    employee_id: str, principal: CurrentPrincipal, service: EmployeeServiceDep
) -> EmployeeDetailOut:
    """Any member may read their own profile; others require scope over the employee."""
    return await service.get(principal, employee_id)


@router.patch("/employees/{employee_id}", response_model=EmployeeDetailOut, dependencies=[BumpAnalytics])
async def update_employee(
    employee_id: str,
    payload: EmployeeUpdate,
    principal: CanManage,
    service: EmployeeServiceDep,
    meta: RequestMetaDep,
) -> EmployeeDetailOut:
    return await service.update(principal, employee_id, payload, meta)


@router.post(
    "/employees/{employee_id}/status", response_model=EmployeeDetailOut, dependencies=[BumpAnalytics]
)
async def change_employee_status(
    employee_id: str,
    payload: EmployeeStatusUpdate,
    principal: CanManage,
    service: EmployeeServiceDep,
    meta: RequestMetaDep,
) -> EmployeeDetailOut:
    """Terminating an employee deactivates their account and revokes all sessions."""
    return await service.change_status(principal, employee_id, payload.status, meta)


@router.post("/employees/{employee_id}/invite", response_model=EmployeeDetailOut)
async def invite_employee(
    employee_id: str,
    payload: InviteRequest,
    principal: Annotated[
        Principal, Depends(require_permissions(Permission.EMPLOYEE_MANAGE, Permission.USER_MANAGE))
    ],
    service: EmployeeServiceDep,
    meta: RequestMetaDep,
) -> EmployeeDetailOut:
    """Send (or re-send) an invitation to create the employee's WorkPulse account."""
    return await service.invite(principal, employee_id, payload.role, meta)


@router.get("/employees/{employee_id}/devices", response_model=list[DeviceOut])
async def list_employee_devices(
    employee_id: str, principal: CurrentPrincipal, service: DeviceServiceDep
) -> list[DeviceOut]:
    return await service.list_for_employee(principal, employee_id)


@router.post(
    "/employees/{employee_id}/devices", response_model=DeviceRegistered, status_code=status.HTTP_201_CREATED
)
async def register_device(
    employee_id: str,
    payload: DeviceCreate,
    principal: CanManage,
    service: DeviceServiceDep,
    meta: RequestMetaDep,
) -> DeviceRegistered:
    """Register a device and issue a one-time enrolment code for the desktop agent (Phase 4)."""
    return await service.register(principal, employee_id, payload, meta)


@router.post("/devices/{device_id}/revoke", response_model=DeviceOut)
async def revoke_device(
    device_id: str, principal: CanManage, service: DeviceServiceDep, meta: RequestMetaDep
) -> DeviceOut:
    return await service.revoke(principal, device_id, meta)
