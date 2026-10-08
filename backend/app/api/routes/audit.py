"""Audit trail for administrators. Read-only by design: entries can't be edited or deleted through the API."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.auth.dependencies import CurrentPrincipal
from app.core.dependencies import DbDep, on_event_loop
from app.repositories.audit_log import AuditLogRepository
from app.repositories.company import CompanyRepository
from app.repositories.organization import EmployeeRepository
from app.repositories.user import UserRepository
from app.schemas.audit import AuditCategoryOut, AuditPage
from app.services.audit_viewer import AuditViewer
from app.services.helpers import parse_id

router = APIRouter(prefix="/audit-logs", tags=["audit"])


def get_audit_viewer(db: DbDep) -> AuditViewer:
    return AuditViewer(
        AuditLogRepository(db), UserRepository(db), EmployeeRepository(db), CompanyRepository(db)
    )


AuditViewerDep = Annotated[AuditViewer, Depends(on_event_loop(get_audit_viewer))]


@router.get("/categories", response_model=list[AuditCategoryOut])
async def audit_categories(principal: CurrentPrincipal, viewer: AuditViewerDep) -> list[AuditCategoryOut]:
    return viewer.categories(principal)


@router.get("", response_model=AuditPage, summary="Search the audit trail (newest first)")
async def audit_logs(
    principal: CurrentPrincipal,
    viewer: AuditViewerDep,
    category: Annotated[str | None, Query(max_length=40)] = None,
    actor_user_id: Annotated[str | None, Query(max_length=24)] = None,
    employee_id: Annotated[str | None, Query(max_length=24)] = None,
    start: date | None = None,
    end: date | None = None,
    page: Annotated[int, Query(ge=1, le=10_000)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> AuditPage:
    return await viewer.search(
        principal,
        category=category,
        actor_user_id=parse_id(actor_user_id, not_found="User not found.") if actor_user_id else None,
        employee_id=parse_id(employee_id, not_found="Employee not found.") if employee_id else None,
        start=start,
        end=end,
        page=page,
        page_size=page_size,
    )
