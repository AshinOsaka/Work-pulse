"""The monitoring policy, readable by every member of the workspace."""

from __future__ import annotations

from fastapi import APIRouter

from app.auth.dependencies import CurrentPrincipal
from app.core.dependencies import DbDep, SettingsDep
from app.repositories.audit_log import AuditLogRepository
from app.repositories.company import CompanyRepository
from app.repositories.organization import EmployeeRepository
from app.repositories.user import UserRepository
from app.schemas.privacy import MonitoringPolicy
from app.services.privacy_policy import PrivacyPolicyService

router = APIRouter(prefix="/privacy", tags=["privacy"])


@router.get(
    "/monitoring-policy",
    response_model=MonitoringPolicy,
    summary="What is collected, when, why, for how long and who can see it",
)
async def monitoring_policy(
    principal: CurrentPrincipal, db: DbDep, settings: SettingsDep
) -> MonitoringPolicy:
    """Built from the workspace's current settings and, for screenshots, the asking person's own setting."""
    service = PrivacyPolicyService(
        settings, CompanyRepository(db), EmployeeRepository(db), UserRepository(db), AuditLogRepository(db)
    )
    return await service.policy(principal)
