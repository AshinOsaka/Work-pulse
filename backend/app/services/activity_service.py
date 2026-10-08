"""Activity tracking: workspace policy and usage reports (read side)."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.auth.permissions import Permission
from app.auth.principal import Principal
from app.core.exceptions import BadRequestError, NotFoundError
from app.models.company import Company
from app.repositories.activity import ActivityDailyRepository, ActivitySegmentRepository
from app.repositories.company import CompanyRepository
from app.repositories.organization import EmployeeRepository
from app.schemas.activity_tracking import (
    ActivityPolicyUpdate,
    ApplicationUsageReport,
    AppUsage,
    EmployeeActivityDay,
    SegmentOut,
)
from app.schemas.agent import ActivityPolicyOut
from app.services.access_scope import AccessScopeService
from app.services.audit_service import AuditService
from app.services.context import RequestMeta
from app.services.helpers import parse_id, parse_ref

MAX_REPORT_DAYS = 92
MAX_SEGMENTS_PER_DAY = 2000


def policy_out(company: Company) -> ActivityPolicyOut:
    policy = company.activity_policy
    return ActivityPolicyOut(
        track_applications=policy.track_applications,
        capture_window_titles=policy.capture_window_titles,
        track_websites=policy.track_websites,
        excluded_apps=policy.excluded_apps,
    )


class ActivityService:
    def __init__(
        self,
        *,
        companies: CompanyRepository,
        employees: EmployeeRepository,
        segments: ActivitySegmentRepository,
        daily: ActivityDailyRepository,
        scopes: AccessScopeService,
        audit: AuditService,
    ) -> None:
        self._companies = companies
        self._employees = employees
        self._segments = segments
        self._daily = daily
        self._scopes = scopes
        self._audit = audit

    async def _company(self, principal: Principal) -> Company:
        company = await self._companies.get_by_id(principal.company_id)
        if company is None:
            raise NotFoundError("Workspace not found.")
        return company

    # ------------------------------------------------------------------ policy
    async def get_policy(self, principal: Principal) -> ActivityPolicyOut:
        """Visible to every member: employees can always see what is recorded about them."""
        return policy_out(await self._company(principal))

    async def update_policy(
        self, principal: Principal, data: ActivityPolicyUpdate, meta: RequestMeta
    ) -> ActivityPolicyOut:
        company = await self._company(principal)
        changes = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}
        if not changes:
            return policy_out(company)
        merged = company.activity_policy.model_copy(update=changes)
        updated = await self._companies.update_by_id(company.id, {"activity_policy": merged.model_dump()})
        await self._audit.record(
            "policy.activity_updated",
            company_id=company.id,
            actor_user_id=principal.user_id,
            target_type="company",
            target_id=str(company.id),
            meta=meta,
            metadata={"fields": sorted(changes)},
        )
        return policy_out(updated or company)

    # ------------------------------------------------------------------ reports
    async def applications(
        self,
        principal: Principal,
        start: date,
        end: date,
        team_id: str | None,
        employee_id: str | None,
    ) -> ApplicationUsageReport:
        if end < start:
            raise BadRequestError("The end date must not be before the start date.", code="invalid_range")
        if (end - start).days >= MAX_REPORT_DAYS:
            raise BadRequestError(f"Reports cover at most {MAX_REPORT_DAYS} days.", code="range_too_long")
        company = await self._company(principal)
        scope = await self._scopes.employee_scope(principal)
        clauses: list[dict[str, Any]] = [c for c in (scope.filter,) if c]
        if team := parse_ref(team_id, "team_id"):
            clauses.append({"team_id": team})
        if employee := parse_ref(employee_id, "employee_id"):
            clauses.append({"_id": employee})
        query = {"$and": clauses} if len(clauses) > 1 else (clauses[0] if clauses else None)
        ids = await self._employees.ids_matching(principal.company_id, query)
        rows = await self._daily.totals_by_app(principal.company_id, ids, start, end) if ids else []
        apps = [
            AppUsage(
                app_id=str(r["_id"]),
                app_name=r["app_name"],
                seconds=round(r["seconds"], 1),
                active_seconds=round(r["active_seconds"], 1),
                employees=r["employees"],
            )
            for r in rows
        ]
        return ApplicationUsageReport(
            start=start,
            end=end,
            timezone=company.timezone,
            total_seconds=round(sum(a.seconds for a in apps), 1),
            active_seconds=round(sum(a.active_seconds for a in apps), 1),
            applications=apps,
        )

    async def employee_day(self, principal: Principal, employee_id: str, day: date) -> EmployeeActivityDay:
        """An employee's activity timeline for one local day (theirs, or within the viewer's scope)."""
        oid = parse_id(employee_id, not_found="Employee not found.", code="employee_not_found")
        is_self = principal.user.employee_id == oid
        if not is_self and Permission.ACTIVITY_VIEW not in principal.permissions:
            raise NotFoundError("Employee not found.", code="employee_not_found")
        scope = await self._scopes.employee_scope(principal)
        if await self._employees.get_in_scope(principal.company_id, oid, scope.filter) is None:
            raise NotFoundError("Employee not found.", code="employee_not_found")

        company = await self._company(principal)
        tz = ZoneInfo(company.timezone)
        start = datetime.combine(day, time.min, tzinfo=tz)
        end = start + timedelta(days=1)
        segments = await self._segments.for_employee(
            principal.company_id, oid, start, end, MAX_SEGMENTS_PER_DAY + 1
        )
        truncated = len(segments) > MAX_SEGMENTS_PER_DAY
        segments = segments[:MAX_SEGMENTS_PER_DAY]
        totals = await self._daily.totals_by_app(principal.company_id, [oid], day, day)
        apps = [
            AppUsage(
                app_id=str(r["_id"]),
                app_name=r["app_name"],
                seconds=round(r["seconds"], 1),
                active_seconds=round(r["active_seconds"], 1),
                employees=1,
            )
            for r in totals
        ]
        return EmployeeActivityDay(
            employee_id=str(oid),
            day=day,
            timezone=company.timezone,
            tracked_seconds=round(sum(a.seconds for a in apps), 1),
            active_seconds=round(sum(a.active_seconds for a in apps), 1),
            applications=apps,
            segments=[
                SegmentOut(
                    app_id=s.app_id,
                    app_name=s.app_name,
                    window_title=s.window_title,
                    started_at=s.started_at,
                    ended_at=s.ended_at,
                    duration_seconds=s.duration_seconds,
                    active_seconds=s.active_seconds,
                    activity_level=s.activity_level,
                )
                for s in segments
            ],
            truncated=truncated,
        )
