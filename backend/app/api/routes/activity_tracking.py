"""Activity tracking: workspace policy and application-usage reports."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import ActivityServiceDep, RequestMetaDep
from app.auth.dependencies import CurrentPrincipal, require_permissions
from app.auth.permissions import Permission
from app.auth.principal import Principal
from app.schemas.activity_tracking import ActivityPolicyUpdate, ApplicationUsageReport, EmployeeActivityDay
from app.schemas.agent import ActivityPolicyOut
from app.schemas.common import ObjectIdStr

router = APIRouter(tags=["activity"])


@router.get(
    "/companies/current/activity-policy",
    response_model=ActivityPolicyOut,
    summary="What the desktop agent records (visible to every member)",
)
async def get_activity_policy(principal: CurrentPrincipal, service: ActivityServiceDep) -> ActivityPolicyOut:
    return await service.get_policy(principal)


@router.patch("/companies/current/activity-policy", response_model=ActivityPolicyOut)
async def update_activity_policy(
    payload: ActivityPolicyUpdate,
    principal: Annotated[Principal, Depends(require_permissions(Permission.POLICY_MANAGE))],
    service: ActivityServiceDep,
    meta: RequestMetaDep,
) -> ActivityPolicyOut:
    """Agents pick up the new policy on their next heartbeat (within about a minute)."""
    return await service.update_policy(principal, payload, meta)


@router.get(
    "/activity/applications",
    response_model=ApplicationUsageReport,
    summary="Application usage across employees in scope (from the daily rollup)",
)
async def application_usage(
    principal: Annotated[Principal, Depends(require_permissions(Permission.ACTIVITY_VIEW))],
    service: ActivityServiceDep,
    start: date,
    end: date,
    team_id: Annotated[ObjectIdStr | None, Query()] = None,
    employee_id: Annotated[ObjectIdStr | None, Query()] = None,
) -> ApplicationUsageReport:
    return await service.applications(principal, start, end, team_id, employee_id)


@router.get(
    "/employees/{employee_id}/activity",
    response_model=EmployeeActivityDay,
    summary="One employee's activity timeline for a day (self, or ACTIVITY_VIEW within scope)",
)
async def employee_activity(
    employee_id: str, principal: CurrentPrincipal, service: ActivityServiceDep, day: date
) -> EmployeeActivityDay:
    return await service.employee_day(principal, employee_id, day)
