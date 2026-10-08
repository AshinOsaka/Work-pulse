"""Screenshot monitoring: policy, the manager gallery, private image delivery and agent uploads."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status

from app.api.deps import CompanyRepoDep, RequestMetaDep, ScreenshotServiceDep
from app.auth.dependencies import CurrentPrincipal, require_permissions
from app.auth.device_auth import CurrentDevice
from app.auth.permissions import Permission
from app.auth.principal import Principal
from app.core.dependencies import SettingsDep
from app.core.exceptions import BadRequestError, ForbiddenError, PayloadTooLargeError, UnauthorizedError
from app.models.company import CompanyStatus
from app.schemas.common import ObjectIdStr
from app.schemas.screenshots import (
    EmployeeScreenshotSettings,
    EmployeeScreenshotSettingsUpdate,
    MonitoringStatus,
    ScreenshotDetail,
    ScreenshotPage,
    ScreenshotPolicyOut,
    ScreenshotPolicyUpdate,
    ScreenshotTimeline,
    ScreenshotUploadResult,
)

router = APIRouter(tags=["screenshots"])

ScreenshotViewer = Annotated[Principal, Depends(require_permissions(Permission.SCREENSHOT_VIEW))]
PolicyManager = Annotated[Principal, Depends(require_permissions(Permission.POLICY_MANAGE))]
UPLOAD_TYPES = frozenset({"image/webp", "image/jpeg", "image/png"})


# --------------------------------------------------------------------------- policy
@router.get(
    "/companies/current/screenshot-policy",
    response_model=ScreenshotPolicyOut,
    summary="Workspace screenshot policy (visible to every member)",
)
async def get_screenshot_policy(
    principal: CurrentPrincipal, service: ScreenshotServiceDep
) -> ScreenshotPolicyOut:
    return await service.get_policy(principal)


@router.patch("/companies/current/screenshot-policy", response_model=ScreenshotPolicyOut)
async def update_screenshot_policy(
    payload: ScreenshotPolicyUpdate,
    principal: PolicyManager,
    service: ScreenshotServiceDep,
    meta: RequestMetaDep,
) -> ScreenshotPolicyOut:
    """Agents pick up the change on their next heartbeat. A new retention period applies to stored images too."""
    return await service.update_policy(principal, payload, meta)


@router.get("/employees/{employee_id}/screenshot-settings", response_model=EmployeeScreenshotSettings)
async def get_employee_screenshot_settings(
    employee_id: str, principal: CurrentPrincipal, service: ScreenshotServiceDep
) -> EmployeeScreenshotSettings:
    return await service.employee_settings(principal, employee_id)


@router.put("/employees/{employee_id}/screenshot-settings", response_model=EmployeeScreenshotSettings)
async def update_employee_screenshot_settings(
    employee_id: str,
    payload: EmployeeScreenshotSettingsUpdate,
    principal: PolicyManager,
    service: ScreenshotServiceDep,
    meta: RequestMetaDep,
) -> EmployeeScreenshotSettings:
    return await service.update_employee_settings(principal, employee_id, payload, meta)


@router.get(
    "/me/monitoring",
    response_model=MonitoringStatus,
    summary="What is being recorded about me right now (transparency)",
)
async def my_monitoring(principal: CurrentPrincipal, service: ScreenshotServiceDep) -> MonitoringStatus:
    return await service.my_monitoring(principal)


# --------------------------------------------------------------------------- gallery
@router.get(
    "/screenshots", response_model=ScreenshotPage, summary="Screenshots for a day (newest first; audited)"
)
async def list_screenshots(
    principal: ScreenshotViewer,
    service: ScreenshotServiceDep,
    meta: RequestMetaDep,
    day: date,
    employee_id: Annotated[ObjectIdStr | None, Query()] = None,
    team_id: Annotated[ObjectIdStr | None, Query()] = None,
    hour: Annotated[int | None, Query(ge=0, le=23)] = None,
    before: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=60)] = 48,
) -> ScreenshotPage:
    return await service.list(
        principal,
        day=day,
        team_id=team_id,
        employee_id=employee_id,
        hour=hour,
        before=before,
        limit=limit,
        meta=meta,
    )


@router.get("/screenshots/timeline", response_model=ScreenshotTimeline)
async def screenshot_timeline(
    principal: ScreenshotViewer,
    service: ScreenshotServiceDep,
    day: date,
    employee_id: Annotated[ObjectIdStr | None, Query()] = None,
    team_id: Annotated[ObjectIdStr | None, Query()] = None,
) -> ScreenshotTimeline:
    return await service.timeline(principal, day=day, team_id=team_id, employee_id=employee_id)


@router.get(
    "/screenshots/{screenshot_id}", response_model=ScreenshotDetail, summary="Open one screenshot (audited)"
)
async def screenshot_detail(
    screenshot_id: str, principal: ScreenshotViewer, service: ScreenshotServiceDep, meta: RequestMetaDep
) -> ScreenshotDetail:
    return await service.detail(principal, screenshot_id, meta)


@router.delete("/screenshots/{screenshot_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_screenshot(
    screenshot_id: str,
    principal: Annotated[
        Principal, Depends(require_permissions(Permission.SCREENSHOT_VIEW, Permission.POLICY_MANAGE))
    ],
    service: ScreenshotServiceDep,
    meta: RequestMetaDep,
) -> Response:
    """For removing a capture that should not have been taken (audited)."""
    await service.delete(principal, screenshot_id, meta)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/screenshot-files/{screenshot_id}/{variant}", include_in_schema=False)
async def screenshot_file(
    screenshot_id: str,
    variant: str,
    service: ScreenshotServiceDep,
    settings: SettingsDep,
    c: Annotated[str, Query(max_length=128)],
    u: Annotated[str, Query(max_length=128)],
    e: Annotated[int, Query()],
    s: Annotated[str, Query(max_length=128)],
) -> Response:
    """Image bytes for a signed URL issued by the gallery. Never cached by shared caches."""
    data = await service.read_file(
        screenshot_id=screenshot_id, variant=variant, company_id=c, user_id=u, expires=e, signature=s
    )
    return Response(
        content=data,
        media_type="image/webp",
        headers={
            "Cache-Control": f"private, max-age={settings.screenshot_url_ttl_seconds}",
            "Content-Disposition": "inline",
            "Content-Security-Policy": "default-src 'none'; sandbox",
            "Cross-Origin-Resource-Policy": "same-origin",
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
        },
    )


# --------------------------------------------------------------------------- agent upload
async def _read_limited(request: Request, limit: int) -> bytes:
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        raise PayloadTooLargeError(f"Screenshots must be at most {limit // 1000} kB.")
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > limit:
            raise PayloadTooLargeError(f"Screenshots must be at most {limit // 1000} kB.")
        chunks.append(chunk)
    return b"".join(chunks)


@router.post(
    "/agent/screenshots",
    response_model=ScreenshotUploadResult,
    tags=["agent"],
    summary="Upload one screenshot (raw image body; idempotent per id)",
)
async def upload_screenshot(
    request: Request,
    device: CurrentDevice,
    service: ScreenshotServiceDep,
    companies: CompanyRepoDep,
    settings: SettingsDep,
    id: Annotated[str, Query(min_length=36, max_length=36)],
    captured_at: datetime,
    session_id: Annotated[str, Query(min_length=1, max_length=64)],
) -> ScreenshotUploadResult:
    content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if content_type not in UPLOAD_TYPES:
        raise BadRequestError("Upload a WebP, JPEG or PNG image.", code="unsupported_media_type")
    if captured_at.tzinfo is None:
        raise BadRequestError("captured_at must include a timezone.", code="invalid_timestamp")
    company = await companies.get_by_id(device.company_id)
    if company is None:
        raise UnauthorizedError("Workspace no longer exists.", code="company_not_found")
    if company.status == CompanyStatus.SUSPENDED:
        raise ForbiddenError("This workspace has been suspended.", code="company_suspended")
    data = await _read_limited(request, settings.screenshot_max_upload_bytes)
    return await service.upload(
        company=company,
        employee=device.employee,
        device_id=device.device.id,
        client_id=id,
        session_id=session_id,
        captured_at=captured_at,
        data=data,
    )
