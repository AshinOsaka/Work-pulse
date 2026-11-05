from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from app.api.deps import PresenceServiceDep
from app.auth.dependencies import CurrentPrincipal, require_permissions
from app.auth.permissions import Permission
from app.auth.principal import Principal
from app.schemas.common import ObjectIdStr
from app.schemas.presence import AttendanceReport, AttendanceSummary, PresenceOverview, WorkHoursSummary

router = APIRouter(prefix="/presence", tags=["presence"])

CanViewActivity = Annotated[Principal, Depends(require_permissions(Permission.ACTIVITY_VIEW))]


@router.get("", response_model=PresenceOverview, summary="Live presence of employees in scope")
async def presence(
    principal: CanViewActivity,
    service: PresenceServiceDep,
    team_id: Annotated[ObjectIdStr | None, Query()] = None,
) -> PresenceOverview:
    return await service.overview(principal, team_id)


@router.get(
    "/work-hours", response_model=WorkHoursSummary, summary="Hours worked per period (company timezone)"
)
async def work_hours(
    principal: CanViewActivity,
    service: PresenceServiceDep,
    period: Literal["daily", "weekly", "monthly"] = "daily",
    team_id: Annotated[ObjectIdStr | None, Query()] = None,
) -> WorkHoursSummary:
    return await service.work_hours(principal, period, team_id)


@router.get(
    "/attendance",
    response_model=AttendanceSummary,
    summary="Present vs away per day (company timezone, working days only)",
)
async def attendance(
    principal: CanViewActivity,
    service: PresenceServiceDep,
    start: date,
    end: date,
    team_id: Annotated[ObjectIdStr | None, Query()] = None,
) -> AttendanceSummary:
    return await service.attendance(principal, start, end, team_id)


@router.get(
    "/attendance/report",
    response_model=AttendanceReport,
    summary="Per-person attendance against the required hours, with daily sign-in and sign-out",
)
async def attendance_report(
    principal: CurrentPrincipal,
    service: PresenceServiceDep,
    start: date,
    end: date,
    team_id: Annotated[ObjectIdStr | None, Query()] = None,
    department_id: Annotated[ObjectIdStr | None, Query()] = None,
    employee_id: Annotated[ObjectIdStr | None, Query()] = None,
    details: bool = True,
) -> AttendanceReport:
    # Any member may ask: the employee scope limits a standard employee to their own record.
    return await service.attendance_report(
        principal,
        start,
        end,
        team_id=team_id,
        department_id=department_id,
        employee_id=employee_id,
        details=details,
    )
