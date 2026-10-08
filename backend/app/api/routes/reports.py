"""Reports: catalogue, preview, asynchronous generation, history and signed downloads."""

from __future__ import annotations

from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Query, Response, status

from app.api.deps import ReportServiceDep, RequestMetaDep
from app.auth.dependencies import CurrentPrincipal
from app.auth.permissions import Permission
from app.core.exceptions import ForbiddenError
from app.schemas.reports import ReportJobOut, ReportPreview, ReportRequest, ReportTypeOut

router = APIRouter(tags=["reports"])


def _viewer(principal: CurrentPrincipal) -> CurrentPrincipal:
    if not principal.has(Permission.REPORT_VIEW):
        raise ForbiddenError("You need the View reports permission.", code="insufficient_permissions")
    return principal


@router.get("/reports/types", response_model=list[ReportTypeOut])
async def report_types(principal: CurrentPrincipal, service: ReportServiceDep) -> list[ReportTypeOut]:
    return service.types(_viewer(principal))


@router.post("/reports/preview", response_model=ReportPreview, summary="The first rows, up to 31 days")
async def preview(
    payload: ReportRequest, principal: CurrentPrincipal, service: ReportServiceDep
) -> ReportPreview:
    return await service.preview(_viewer(principal), payload)


@router.post("/reports", response_model=ReportJobOut, status_code=status.HTTP_202_ACCEPTED)
async def request_report(
    payload: ReportRequest, principal: CurrentPrincipal, service: ReportServiceDep, meta: RequestMetaDep
) -> ReportJobOut:
    """Queue a report; poll GET /reports/{id} (or the list) until it is ready, then use its download URL."""
    return await service.request(_viewer(principal), payload, meta)


@router.get("/reports", response_model=list[ReportJobOut])
async def list_reports(principal: CurrentPrincipal, service: ReportServiceDep) -> list[ReportJobOut]:
    return await service.list(principal)


@router.get("/reports/{report_id}", response_model=ReportJobOut)
async def get_report(report_id: str, principal: CurrentPrincipal, service: ReportServiceDep) -> ReportJobOut:
    return await service.get(principal, report_id)


@router.delete("/reports/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_report(
    report_id: str, principal: CurrentPrincipal, service: ReportServiceDep, meta: RequestMetaDep
) -> Response:
    await service.delete(principal, report_id, meta)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/report-files/{report_id}", include_in_schema=False)
async def report_file(
    report_id: str,
    service: ReportServiceDep,
    meta: RequestMetaDep,
    c: Annotated[str, Query(max_length=128)],
    u: Annotated[str, Query(max_length=128)],
    e: Annotated[int, Query()],
    s: Annotated[str, Query(max_length=128)],
) -> Response:
    """The file for a signed, requester-bound URL from the report list. Always a download; never cached."""
    data, content_type, filename = await service.read_file(report_id, c, u, e, s, meta)
    return Response(
        content=data,
        media_type=content_type,
        headers={
            "Content-Disposition": f"attachment; filename=\"{filename}\"; filename*=UTF-8''{quote(filename)}",
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )
