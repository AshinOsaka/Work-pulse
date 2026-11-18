"""Devices plugged into employees' computers, USB file copies, and possible automated input (read side)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import CompanyRepoDep, DeviceWatchDep
from app.auth.dependencies import require_permissions
from app.auth.permissions import Permission
from app.auth.principal import Principal
from app.core.exceptions import NotFoundError
from app.models.company import Company
from app.repositories.company import CompanyRepository
from app.schemas.common import APIModel, ObjectIdStr

router = APIRouter(tags=["devices"])

Viewer = Annotated[Principal, Depends(require_permissions(Permission.ACTIVITY_VIEW))]


class ConnectionRow(APIModel):
    id: str
    employee_id: str
    employee: str
    department: str
    team: str
    laptop: str
    device_key: str
    kind: str
    name: str
    title: str
    hardware_id: str | None = None
    size_bytes: int | None = None
    connected_at: datetime
    disconnected_at: datetime | None = None
    at_start: bool
    allowed: bool
    file_counts: dict[str, int]
    bytes_to_usb: int
    bytes_from_usb: int


class FileRow(APIModel):
    action: str
    path: str
    size: int | None = None
    at: datetime
    previous: str | None = None


class CheckRow(APIModel):
    id: str
    employee_id: str
    employee: str
    department: str
    team: str
    laptop: str
    kind: str
    #: answered | unanswered | stopped | asking | software
    status: str
    started_at: datetime
    asked_at: datetime | None = None
    ended_at: datetime | None = None
    minutes: int
    max_span_px: int
    apps: list[str]


async def _company(companies: CompanyRepository, principal: Principal) -> Company:
    company = await companies.get_by_id(principal.company_id)
    if company is None:
        raise NotFoundError("Workspace not found.")
    return company


@router.get(
    "/devices/connections", response_model=list[ConnectionRow], summary="Devices plugged in, by day range"
)
async def connections(
    principal: Viewer,
    companies: CompanyRepoDep,
    service: DeviceWatchDep,
    start: date,
    end: date,
    employee_id: Annotated[ObjectIdStr | None, Query()] = None,
) -> list[ConnectionRow]:
    company = await _company(companies, principal)
    rows = await service.connections(principal, company, start, end, employee_id)
    return [ConnectionRow.model_validate(r) for r in rows]


@router.get(
    "/devices/connections/{connection_id}/files",
    response_model=list[FileRow],
    summary="Files copied to, from or deleted on a USB drive during one connection (names and sizes only)",
)
async def connection_files(
    connection_id: str, principal: Viewer, companies: CompanyRepoDep, service: DeviceWatchDep
) -> list[FileRow]:
    company = await _company(companies, principal)
    return [
        FileRow.model_validate(f) for f in await service.connection_files(principal, company, connection_id)
    ]


@router.get(
    "/automation/checks", response_model=list[CheckRow], summary="Possible automated input, by day range"
)
async def checks(
    principal: Viewer,
    companies: CompanyRepoDep,
    service: DeviceWatchDep,
    start: date,
    end: date,
    employee_id: Annotated[ObjectIdStr | None, Query()] = None,
) -> list[CheckRow]:
    company = await _company(companies, principal)
    return [
        CheckRow.model_validate(r) for r in await service.checks(principal, company, start, end, employee_id)
    ]
