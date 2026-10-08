from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import ActivityFeedServiceDep
from app.auth.dependencies import require_permissions
from app.auth.permissions import Permission
from app.auth.principal import Principal
from app.schemas.activity import ActivityItem
from app.schemas.common import ObjectIdStr

router = APIRouter(prefix="/activity", tags=["activity"])


@router.get("/feed", response_model=list[ActivityItem], summary="Recent organisation activity (scoped)")
async def activity_feed(
    principal: Annotated[Principal, Depends(require_permissions(Permission.EMPLOYEE_VIEW))],
    service: ActivityFeedServiceDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    team_id: Annotated[ObjectIdStr | None, Query()] = None,
) -> list[ActivityItem]:
    """Workforce events (people, invitations, devices, roles) visible to the caller, newest first."""
    return await service.recent(principal, limit=limit, team_id=team_id)
