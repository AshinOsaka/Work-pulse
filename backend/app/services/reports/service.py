"""Reports: catalogue, preview, requests, history and secure downloads. Generation runs in `ReportWorker`.

Access:
* `REPORT_VIEW` to see the catalogue and preview; `REPORT_EXPORT` to generate and download files.
* Each type also needs the permission for its data (screenshots, activity, live viewing); see `REPORT_TYPES`.
* Rows only ever cover people in the requester's access scope (and projects they can see). The worker checks the
  requester's account and permissions again when it runs, so a revoked permission stops a queued report.
* Files are encrypted at rest, downloadable only by the requester through short-lived signed URLs, and deleted
  after the retention period. Requests, generation, downloads and deletions are audited.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.auth.permissions import Permission
from app.auth.principal import Principal
from app.core.config import Settings
from app.core.exceptions import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from app.core.object_storage import ObjectNotFoundError, ObjectStorage
from app.core.signed_urls import UrlSigner
from app.models.company import Company
from app.models.report import ACTIVE_REPORT_STATUSES, ReportFilters, ReportJob, ReportStatus, ReportType
from app.repositories.company import CompanyRepository
from app.repositories.report import ReportJobRepository
from app.schemas.reports import (
    ReportJobOut,
    ReportPreview,
    ReportRequest,
    ReportTypeOut,
)
from app.services.audit_service import AuditService
from app.services.context import RequestMeta
from app.services.helpers import parse_id, parse_ref
from app.services.productivity.service import ProductivityService
from app.services.reports.builders import (
    BUILDERS,
    REPORT_TYPES,
    ReportContext,
    ReportData,
    ReportRepos,
    resolve_employees,
)
from app.services.reports.writers import _display
from app.services.work.service import WorkService
from app.utils.time import utcnow

PREVIEW_ROWS = 50
PREVIEW_MAX_DAYS = 31
_NOT_FOUND = "Report not found."


def allowed(principal: Principal, report_type: ReportType) -> bool:
    need = REPORT_TYPES[report_type].requires
    return principal.has(Permission.REPORT_VIEW) and (need is None or principal.has(need))


def check_dates(start: date, end: date, max_days: int) -> None:
    if end < start:
        raise BadRequestError("The end date must not be before the start date.", code="invalid_range")
    if (end - start).days >= max_days:
        raise BadRequestError(f"Choose a period of at most {max_days} days.", code="range_too_long")


@dataclass
class ReportEngine:
    """The services a report needs. Built per request by the API and per job by the worker."""

    companies: CompanyRepository
    repos: ReportRepos
    productivity: ProductivityService
    work: WorkService

    async def build(
        self, principal: Principal, report_type: ReportType, start: date, end: date, filters: ReportFilters
    ) -> tuple[ReportData, ReportContext]:
        company = await self.companies.get_by_id(principal.company_id)
        if company is None:
            raise NotFoundError("Workspace not found.")
        ctx = await self.context(principal, company, start, end, filters)
        data = await BUILDERS[report_type](ctx)
        data.notes = [*data.notes, *ctx.notes]
        return data, ctx

    async def context(
        self, principal: Principal, company: Company, start: date, end: date, filters: ReportFilters
    ) -> ReportContext:
        employees = await resolve_employees(self.repos, principal, filters)
        cid = principal.company_id
        return ReportContext(
            principal=principal,
            company=company,
            tz=ZoneInfo(company.timezone),
            start=start,
            end=end,
            filters=filters,
            employees=employees,
            departments=await self.repos.departments.find_by_ids(
                cid, [e.department_id for e in employees if e.department_id]
            ),
            teams=await self.repos.teams.find_by_ids(cid, [e.team_id for e in employees if e.team_id]),
            profiles=await self.repos.profiles.find_by_ids(
                cid, [e.work_profile_id for e in employees if e.work_profile_id]
            ),
            repos=self.repos,
            productivity=self.productivity,
            work=self.work,
        )

    async def describe_filters(self, principal: Principal, filters: ReportFilters) -> list[str]:
        cid = principal.company_id
        parts: list[str] = []
        if filters.employee_ids:
            people = await self.repos.employees.find_by_ids(cid, filters.employee_ids)
            names = sorted(p.full_name for p in people.values())
            parts.append(
                "People: "
                + (", ".join(names[:5]) + (f" and {len(names) - 5} more" if len(names) > 5 else ""))
            )
        for label, repo, value in (
            ("Department", self.repos.departments, filters.department_id),
            ("Team", self.repos.teams, filters.team_id),
            ("Work profile", self.repos.profiles, filters.work_profile_id),
            ("Project", self.repos.projects, filters.project_id),
        ):
            if value:
                found = await repo.get_by_id(cid, value)
                parts.append(f"{label}: {found.name if found else 'removed'}")
        if filters.role:
            parts.append(f"Role: {filters.role.replace('_', ' ').title()}")
        return parts or ["Everyone in the requester's access scope"]


class ReportService:
    def __init__(
        self,
        *,
        settings: Settings,
        jobs: ReportJobRepository,
        engine: ReportEngine,
        storage: ObjectStorage,
        signer: UrlSigner,
        audit: AuditService,
        wake: Any,
    ) -> None:
        self._settings = settings
        self._jobs = jobs
        self._engine = engine
        self._storage = storage
        self._signer = signer
        self._audit = audit
        self._wake = wake

    # ------------------------------------------------------------------ catalogue & preview
    def types(self, principal: Principal) -> list[ReportTypeOut]:
        return [
            ReportTypeOut(
                key=t.key,
                label=t.label,
                description=t.description,
                filters=list(t.filters),
                allowed=allowed(principal, t.key),
                requires=t.requires.value if t.requires else None,
            )
            for t in REPORT_TYPES.values()
        ]

    @staticmethod
    def _filters(data: ReportRequest) -> ReportFilters:
        f = data.filters
        return ReportFilters(
            employee_ids=[i for i in (parse_ref(x, "employee_ids") for x in f.employee_ids) if i is not None],
            department_id=parse_ref(f.department_id, "department_id"),
            team_id=parse_ref(f.team_id, "team_id"),
            role=f.role,
            work_profile_id=parse_ref(f.work_profile_id, "work_profile_id"),
            project_id=parse_ref(f.project_id, "project_id"),
        )

    def _check_type(self, principal: Principal, report_type: ReportType) -> None:
        if not allowed(principal, report_type):
            need = REPORT_TYPES[report_type].requires
            raise ForbiddenError(
                f"You need the {need.value if need else 'REPORT_VIEW'} permission for this report.",
                code="insufficient_permissions",
            )

    async def preview(self, principal: Principal, data: ReportRequest) -> ReportPreview:
        self._check_type(principal, data.report_type)
        check_dates(data.start, data.end, PREVIEW_MAX_DAYS)
        report, ctx = await self._engine.build(
            principal, data.report_type, data.start, data.end, self._filters(data)
        )
        return ReportPreview(
            title=report.title,
            columns=[{"key": c.key, "label": c.label, "kind": c.kind} for c in report.columns],
            rows=[
                {c.key: _display(c, row.get(c.key)) for c in report.columns}
                for row in report.rows[:PREVIEW_ROWS]
            ],
            total_rows=len(report.rows),
            people=len(ctx.employees),
            notes=report.notes,
        )

    # ------------------------------------------------------------------ jobs
    async def request(self, principal: Principal, data: ReportRequest, meta: RequestMeta) -> ReportJobOut:
        if not principal.has(Permission.REPORT_EXPORT):
            raise ForbiddenError("You need the Export reports permission.", code="insufficient_permissions")
        self._check_type(principal, data.report_type)
        check_dates(data.start, data.end, self._settings.report_max_days)
        active = await self._jobs.active_for_requester(principal.company_id, principal.user_id)
        if active >= self._settings.report_max_active_per_user:
            raise ConflictError(
                "Wait for your reports in progress to finish before requesting another.",
                code="too_many_reports",
            )
        job = ReportJob(
            company_id=principal.company_id,
            requested_by=principal.user_id,
            requested_by_name=principal.user.full_name,
            report_type=data.report_type,
            format=data.format,
            period=data.period,
            start=data.start.isoformat(),
            end=data.end.isoformat(),
            filters=self._filters(data),
        )
        await self._jobs.create(principal.company_id, job)
        await self._audit.record(
            "report.requested",
            company_id=principal.company_id,
            actor_user_id=principal.user_id,
            target_type="report",
            target_id=str(job.id),
            meta=meta,
            metadata={
                "type": job.report_type.value,
                "format": job.format.value,
                "start": job.start,
                "end": job.end,
            },
        )
        self._wake()
        return self._out(job)

    async def list(self, principal: Principal) -> list[ReportJobOut]:
        self._require_view(principal)
        return [self._out(j) for j in await self._jobs.for_requester(principal.company_id, principal.user_id)]

    async def _own(self, principal: Principal, job_id: str) -> ReportJob:
        oid = parse_id(job_id, not_found=_NOT_FOUND, code="report_not_found")
        job = await self._jobs.get_by_id(principal.company_id, oid)
        if job is None or job.requested_by != principal.user_id:
            raise NotFoundError(_NOT_FOUND, code="report_not_found")
        return job

    async def get(self, principal: Principal, job_id: str) -> ReportJobOut:
        self._require_view(principal)
        return self._out(await self._own(principal, job_id))

    async def delete(self, principal: Principal, job_id: str, meta: RequestMeta) -> None:
        self._require_view(principal)
        job = await self._own(principal, job_id)
        if job.status in ACTIVE_REPORT_STATUSES:
            raise ConflictError("This report is still being generated.", code="report_in_progress")
        if job.object_key:
            await self._storage.delete(job.object_key)
        await self._jobs.delete_by_id(principal.company_id, job.id)
        await self._audit.record(
            "report.deleted",
            company_id=principal.company_id,
            actor_user_id=principal.user_id,
            target_type="report",
            target_id=str(job.id),
            meta=meta,
            metadata={"type": job.report_type.value},
        )

    @staticmethod
    def _require_view(principal: Principal) -> None:
        if not principal.has(Permission.REPORT_VIEW):
            raise ForbiddenError("You need the View reports permission.", code="insufficient_permissions")

    def _out(self, job: ReportJob) -> ReportJobOut:
        url = None
        if job.status == ReportStatus.READY and job.object_key:
            url = self._signer.sign(
                f"{self._settings.api_prefix}/report-files/{job.id}",
                company_id=str(job.company_id),
                user_id=str(job.requested_by),
                object_id=str(job.id),
                variant="report",
            )
        return ReportJobOut(
            id=str(job.id),
            report_type=job.report_type,
            label=REPORT_TYPES[job.report_type].label,
            format=job.format,
            period=job.period,
            start=date.fromisoformat(job.start),
            end=date.fromisoformat(job.end),
            status=job.status,
            progress=job.progress,
            row_count=job.row_count,
            filename=job.filename,
            size_bytes=job.size_bytes,
            error=job.error,
            notes=job.notes,
            created_at=job.created_at,
            finished_at=job.finished_at,
            expires_at=job.expires_at,
            download_url=url,
        )

    # ------------------------------------------------------------------ download
    async def read_file(
        self, job_id: str, company_id: str, user_id: str, expires: int, signature: str, meta: RequestMeta
    ) -> tuple[bytes, str, str]:
        if not self._signer.verify(
            company_id=company_id,
            user_id=user_id,
            object_id=job_id,
            variant="report",
            expires=expires,
            signature=signature,
        ):
            raise ForbiddenError(
                "This download link has expired. Open Reports and download again.", code="link_expired"
            )
        cid = parse_id(company_id, not_found=_NOT_FOUND, code="report_not_found")
        oid = parse_id(job_id, not_found=_NOT_FOUND, code="report_not_found")
        job = await self._jobs.get_by_id(cid, oid)
        if (
            job is None
            or str(job.requested_by) != user_id
            or job.status != ReportStatus.READY
            or not job.object_key
        ):
            raise NotFoundError(_NOT_FOUND, code="report_not_found")
        if job.expires_at and _aware(job.expires_at) <= utcnow():
            raise NotFoundError("This report has expired.", code="report_expired")
        try:
            data = await self._storage.get(job.object_key)
        except ObjectNotFoundError as exc:
            raise NotFoundError("This report file is no longer available.", code="report_expired") from exc
        await self._jobs.count_downloads(cid, oid)
        await self._audit.record(
            "report.downloaded",
            company_id=cid,
            actor_user_id=job.requested_by,
            target_type="report",
            target_id=str(job.id),
            meta=meta,
            metadata={"type": job.report_type.value, "format": job.format.value, "rows": job.row_count},
        )
        return data, job.content_type or "application/octet-stream", job.filename or f"report-{job.id}"


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def expires_from(now: datetime, settings: Settings) -> datetime:
    return now + timedelta(hours=settings.report_retention_hours)


__all__ = ["ReportEngine", "ReportService", "allowed", "check_dates", "expires_from"]
