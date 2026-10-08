"""Productivity intelligence: rules (by company, role, department, team and work profile), profiles and reports."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response, status

from app.api.deps import AnalyticsCacheDep, BumpAnalytics, ProductivityServiceDep, RequestMetaDep
from app.auth.dependencies import CurrentPrincipal, require_permissions
from app.auth.permissions import Permission
from app.auth.principal import Principal
from app.core.exceptions import ForbiddenError
from app.schemas.common import ObjectIdStr
from app.schemas.productivity import (
    EmployeeProductivity,
    GroupBreakdown,
    ProductivityTrend,
    ProfileMembers,
    ProfileTemplateOut,
    RecommendedResult,
    RuleCreate,
    RuleOut,
    RuleUpdate,
    TeamProductivity,
    UnclassifiedItem,
    WorkProfileCreate,
    WorkProfileOut,
    WorkProfileUpdate,
)

router = APIRouter(prefix="/productivity", tags=["productivity"])

PolicyManager = Annotated[Principal, Depends(require_permissions(Permission.POLICY_MANAGE))]
ActivityViewer = Annotated[Principal, Depends(require_permissions(Permission.ACTIVITY_VIEW))]


def _can_read_rules(principal: Principal) -> Principal:
    if not (principal.has(Permission.ACTIVITY_VIEW) or principal.has(Permission.POLICY_MANAGE)):
        raise ForbiddenError(
            "You do not have permission to view productivity rules.", code="insufficient_permissions"
        )
    return principal


@router.get("/rules", response_model=list[RuleOut])
async def list_rules(principal: CurrentPrincipal, service: ProductivityServiceDep) -> list[RuleOut]:
    return await service.list_rules(_can_read_rules(principal))


@router.post(
    "/rules", response_model=RuleOut, status_code=status.HTTP_201_CREATED, dependencies=[BumpAnalytics]
)
async def create_rule(
    payload: RuleCreate, principal: PolicyManager, service: ProductivityServiceDep, meta: RequestMetaDep
) -> RuleOut:
    return await service.create_rule(principal, payload, meta)


@router.patch("/rules/{rule_id}", response_model=RuleOut, dependencies=[BumpAnalytics])
async def update_rule(
    rule_id: str,
    payload: RuleUpdate,
    principal: PolicyManager,
    service: ProductivityServiceDep,
    meta: RequestMetaDep,
) -> RuleOut:
    return await service.update_rule(principal, rule_id, payload, meta)


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[BumpAnalytics])
async def delete_rule(
    rule_id: str, principal: PolicyManager, service: ProductivityServiceDep, meta: RequestMetaDep
) -> Response:
    await service.delete_rule(principal, rule_id, meta)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/rules/recommended",
    response_model=RecommendedResult,
    summary="Add a small set of starter rules",
    dependencies=[BumpAnalytics],
)
async def load_recommended(
    principal: PolicyManager, service: ProductivityServiceDep, meta: RequestMetaDep
) -> RecommendedResult:
    return await service.load_recommended(principal, meta)


@router.get("/unclassified", response_model=list[UnclassifiedItem], summary="Activity no rule covers yet")
async def unclassified(
    principal: ActivityViewer, service: ProductivityServiceDep, start: date, end: date
) -> list[UnclassifiedItem]:
    return await service.unclassified(principal, start, end)


@router.get(
    "/team", response_model=TeamProductivity, summary="Metrics, scores and insights for people in scope"
)
async def team_report(
    principal: ActivityViewer,
    service: ProductivityServiceDep,
    start: date,
    end: date,
    cache: AnalyticsCacheDep,
    team_id: Annotated[ObjectIdStr | None, Query()] = None,
    department_id: Annotated[ObjectIdStr | None, Query()] = None,
) -> TeamProductivity:
    return await cache.get_or_compute(
        principal,
        "team",
        {"start": start, "end": end, "team": team_id, "department": department_id},
        TeamProductivity,
        lambda: service.team_report(principal, start, end, team_id, department_id),
    )


@router.get(
    "/groups", response_model=GroupBreakdown, summary="Totals per department or team (sorted by name)"
)
async def groups(
    principal: ActivityViewer,
    service: ProductivityServiceDep,
    start: date,
    end: date,
    cache: AnalyticsCacheDep,
    by: Literal["department", "team"] = "department",
) -> GroupBreakdown:
    return await cache.get_or_compute(
        principal,
        "groups",
        {"start": start, "end": end, "by": by},
        GroupBreakdown,
        lambda: service.groups(principal, by, start, end),
    )


@router.get("/trend", response_model=ProductivityTrend, summary="Scores and time per day, week or month")
async def trend(
    principal: CurrentPrincipal,
    service: ProductivityServiceDep,
    cache: AnalyticsCacheDep,
    period: Literal["daily", "weekly", "monthly"] = "daily",
    team_id: Annotated[ObjectIdStr | None, Query()] = None,
    department_id: Annotated[ObjectIdStr | None, Query()] = None,
    employee_id: Annotated[ObjectIdStr | None, Query()] = None,
) -> ProductivityTrend:
    """People with View activity see anyone in scope; everyone else only their own trend (`employee_id`)."""
    if not principal.has(Permission.ACTIVITY_VIEW) and employee_id is None:
        raise ForbiddenError(
            "You do not have permission to view team trends.", code="insufficient_permissions"
        )
    return await cache.get_or_compute(
        principal,
        "trend",
        {"period": period, "team": team_id, "department": department_id, "employee": employee_id},
        ProductivityTrend,
        lambda: service.trend(principal, period, team_id, department_id, employee_id),
    )


# --------------------------------------------------------------------------- work profiles (job roles)
@router.get("/profile-templates", response_model=list[ProfileTemplateOut])
async def profile_templates(
    principal: CurrentPrincipal, service: ProductivityServiceDep
) -> list[ProfileTemplateOut]:
    _can_read_rules(principal)
    return service.templates()


@router.get("/profiles", response_model=list[WorkProfileOut])
async def list_profiles(principal: CurrentPrincipal, service: ProductivityServiceDep) -> list[WorkProfileOut]:
    _can_read_rules(principal)
    return await service.list_profiles(principal)


@router.post(
    "/profiles",
    response_model=WorkProfileOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[BumpAnalytics],
)
async def create_profile(
    payload: WorkProfileCreate,
    principal: PolicyManager,
    service: ProductivityServiceDep,
    meta: RequestMetaDep,
) -> WorkProfileOut:
    return await service.create_profile(principal, payload, meta)


@router.patch("/profiles/{profile_id}", response_model=WorkProfileOut, dependencies=[BumpAnalytics])
async def update_profile(
    profile_id: str,
    payload: WorkProfileUpdate,
    principal: PolicyManager,
    service: ProductivityServiceDep,
    meta: RequestMetaDep,
) -> WorkProfileOut:
    return await service.update_profile(principal, profile_id, payload, meta)


@router.put("/profiles/{profile_id}/members", response_model=WorkProfileOut, dependencies=[BumpAnalytics])
async def set_profile_members(
    profile_id: str,
    payload: ProfileMembers,
    principal: PolicyManager,
    service: ProductivityServiceDep,
    meta: RequestMetaDep,
) -> WorkProfileOut:
    return await service.set_profile_members(principal, profile_id, payload, meta)


@router.delete("/profiles/{profile_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[BumpAnalytics])
async def delete_profile(
    profile_id: str, principal: PolicyManager, service: ProductivityServiceDep, meta: RequestMetaDep
) -> Response:
    await service.delete_profile(principal, profile_id, meta)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/employees/{employee_id}", response_model=EmployeeProductivity)
async def employee_report(
    employee_id: str, principal: CurrentPrincipal, service: ProductivityServiceDep, start: date, end: date
) -> EmployeeProductivity:
    """Employees can always see their own figures; others need View activity within their scope."""
    return await service.employee_report(principal, employee_id, start, end)
