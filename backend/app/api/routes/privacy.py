"""The monitoring policy, readable by every member of the workspace, and the public privacy facts."""

from __future__ import annotations

from fastapi import APIRouter

from app.auth.dependencies import CurrentPrincipal
from app.core.dependencies import DbDep, SettingsDep
from app.models.company import ScreenshotPolicy
from app.repositories.activity import SEGMENT_RETENTION_SECONDS
from app.repositories.agent import EVENT_RETENTION_SECONDS
from app.repositories.audit_log import AuditLogRepository
from app.repositories.company import CompanyRepository
from app.repositories.organization import EmployeeRepository
from app.repositories.user import UserRepository
from app.schemas.privacy import MonitoringPolicy, PublicPrivacyFacts
from app.services.privacy_policy import NEVER_COLLECTED, PrivacyPolicyService

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


@router.get(
    "/public",
    response_model=PublicPrivacyFacts,
    summary="General privacy facts for the public privacy policy page (no sign-in)",
)
async def public_privacy_facts(settings: SettingsDep) -> PublicPrivacyFacts:
    """The same "never collected" list and retention values the in-app policy uses — never any workspace data."""
    contact = settings.privacy_contact_email or settings.gmail_sender_email or None
    return PublicPrivacyFacts(
        never_collected=list(NEVER_COLLECTED),
        detailed_activity_days=SEGMENT_RETENTION_SECONDS // 86_400,
        raw_event_days=EVENT_RETENTION_SECONDS // 86_400,
        default_screenshot_days=ScreenshotPolicy().retention_days,
        report_file_days=max(1, round(settings.report_retention_hours / 24)),
        contact_email=contact,
    )
