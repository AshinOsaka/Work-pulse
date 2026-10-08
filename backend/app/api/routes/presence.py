from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query

from app.api.deps import PresenceServiceDep
from app.auth.dependencies import require_permissions
from app.auth.permissions import Permission
from app.auth.principal import Principal
from app.schemas.common import ObjectIdStr
from app.schemas.presence import PresenceOverview, WorkHoursSummary

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
