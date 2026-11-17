"""Automatic report e-mails: status for the Settings page, and a test e-mail to the person asking."""

from __future__ import annotations

from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, Request

from app.api.deps import CompanyRepoDep
from app.auth.dependencies import require_permissions
from app.auth.permissions import Permission
from app.auth.principal import Principal
from app.core.dependencies import SettingsDep
from app.core.exceptions import NotFoundError, ServiceUnavailableError
from app.schemas.common import APIModel
from app.services.auto_reports.job import AutoReportJob
from app.utils.time import utcnow

router = APIRouter(prefix="/auto-reports", tags=["auto-reports"])

Manager = Annotated[Principal, Depends(require_permissions(Permission.POLICY_MANAGE))]


class AutoReportRun(APIModel):
    day: str
    slot: str
    status: str
    people: int | None = None
    sent: int | None = None
    failed: int | None = None
    ai: int | None = None


class AutoReportStatus(APIModel):
    #: The server has an AI key for report summaries (REPORT_AI_API_KEY).
    ai_available: bool
    ai_model: str
    #: E-mail is configured (not the development console).
    email_ready: bool
    runs: list[AutoReportRun]


class TestRequest(APIModel):
    slot: Literal["midday", "evening"] = "midday"


class TestResult(APIModel):
    sent_to: str
    people: int
    ai: bool


def _job(request: Request) -> AutoReportJob:
    jobs = getattr(request.app.state, "background", None)
    if jobs is None:
        raise ServiceUnavailableError("Automatic reports are not available on this server.")
    job: AutoReportJob = jobs.auto_reports
    return job


@router.get(
    "/status", response_model=AutoReportStatus, summary="Automatic reports: AI, e-mail and recent runs"
)
async def status(request: Request, principal: Manager, settings: SettingsDep) -> AutoReportStatus:
    job = _job(request)
    runs = await job.recent_runs(principal.company_id)
    return AutoReportStatus(
        ai_available=job.ai_available,
        ai_model=settings.report_ai_model,
        email_ready=settings.email_backend != "console",
        runs=[
            AutoReportRun(
                day=r["day"],
                slot=r["slot"],
                status=r.get("status", "done"),
                people=r.get("people"),
                sent=r.get("sent"),
                failed=r.get("failed"),
                ai=r.get("ai"),
            )
            for r in runs
        ],
    )


@router.post("/test", response_model=TestResult, summary="Send a test report now, only to yourself")
async def send_test(
    request: Request, payload: TestRequest, principal: Manager, companies: CompanyRepoDep
) -> TestResult:
    company = await companies.get_by_id(principal.company_id)
    if company is None:
        raise NotFoundError("Workspace not found.")
    now = utcnow()
    today = now.astimezone(ZoneInfo(company.timezone)).date()
    user = principal.user
    result = await _job(request).run_slot(
        company,
        payload.slot,
        today,
        now,
        only_to=(user.email, user.full_name.split(" ")[0] or user.full_name),
    )
    if result.failed:
        raise ServiceUnavailableError(
            "The test e-mail couldn't be sent. Check the e-mail settings and try again."
        )
    return TestResult(sent_to=user.email, people=result.people, ai=result.ai > 0)
