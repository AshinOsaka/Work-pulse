"""Dependency-injection wiring for repositories and services."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import Depends, Request

from app.auth.dependencies import CurrentPrincipal
from app.core.config import Settings
from app.core.dependencies import DbDep, ObjectStorageDep, SettingsDep, UrlSignerDep, on_event_loop
from app.core.keys import mfa_key
from app.core.object_storage import ObjectStorage
from app.core.signed_urls import UrlSigner
from app.repositories.activity import ActivityDailyRepository, ActivitySegmentRepository
from app.repositories.agent import AgentEventRepository, WorkSessionRepository
from app.repositories.assistant import ConversationRepository
from app.repositories.audit_log import AuditLogRepository
from app.repositories.auth_tokens import (
    EmailVerificationTokenRepository,
    InvitationTokenRepository,
    PasswordResetTokenRepository,
    RefreshTokenRepository,
)
from app.repositories.company import CompanyRepository
from app.repositories.live import LiveSessionEventRepository, LiveSessionRepository
from app.repositories.notification import NotificationPreferencesRepository, NotificationRepository
from app.repositories.organization import (
    DepartmentRepository,
    DeviceRepository,
    EmployeeRepository,
    TeamRepository,
)
from app.repositories.productivity import (
    ProductivityRuleRepository,
    WebsiteDailyRepository,
    WorkProfileRepository,
)
from app.repositories.report import ReportJobRepository
from app.repositories.role import PermissionRepository, RoleRepository
from app.repositories.screenshot import ScreenshotRepository
from app.repositories.security import AuthSessionRepository, RateLimitRepository
from app.repositories.user import UserRepository
from app.repositories.work import (
    MilestoneRepository,
    ProjectRepository,
    TaskActivityRepository,
    TaskAttachmentRepository,
    TaskCommentRepository,
    TaskRepository,
    TimeEntryRepository,
)
from app.services.access_scope import AccessScopeService
from app.services.activity_feed_service import ActivityFeedService
from app.services.activity_service import ActivityService
from app.services.agent_service import AgentService
from app.services.assistant.service import AssistantClient, AssistantService, RateLimiter, build_client
from app.services.assistant.tools import AssistantServices
from app.services.audit_service import AuditService
from app.services.auth_service import AuthService
from app.services.context import RequestMeta
from app.services.device_service import DeviceService
from app.services.email_service import EmailSender, EmailService
from app.services.employee_service import EmployeeService
from app.services.live_hub import LiveHub
from app.services.live_service import LiveService
from app.services.mfa_service import MfaService
from app.services.notifications.notifier import Notifier, NullNotifier
from app.services.notifications.service import NotificationService
from app.services.organization_service import OrganizationService
from app.services.presence_service import PresenceService
from app.services.productivity.response_cache import AnalyticsCache
from app.services.productivity.service import ProductivityService
from app.services.reports.builders import ReportRepos
from app.services.reports.service import ReportEngine, ReportService
from app.services.screenshot_service import ScreenshotService
from app.services.throttle import Throttle
from app.services.token_service import TokenService
from app.services.user_admin_service import UserAdminService
from app.services.work.service import WorkService


def get_request_meta(request: Request) -> RequestMeta:
    return RequestMeta(
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


def get_user_repository(db: DbDep) -> UserRepository:
    return UserRepository(db)


def get_company_repository(db: DbDep) -> CompanyRepository:
    return CompanyRepository(db)


def get_role_repository(db: DbDep) -> RoleRepository:
    return RoleRepository(db)


def get_permission_repository(db: DbDep) -> PermissionRepository:
    return PermissionRepository(db)


def get_email_service(request: Request, settings: SettingsDep) -> EmailService:
    sender: EmailSender = request.app.state.email_sender
    return EmailService(sender, settings)


def get_throttle(db: DbDep, settings: SettingsDep) -> Throttle:
    return Throttle(RateLimitRepository(db), enabled=settings.rate_limits_enabled)


def get_mfa_service(db: DbDep, settings: SettingsDep) -> MfaService:
    return MfaService(UserRepository(db), AuditService(AuditLogRepository(db)), mfa_key(settings))


def get_auth_service(
    db: DbDep,
    settings: SettingsDep,
    email: Annotated[EmailService, Depends(on_event_loop(get_email_service))],
) -> AuthService:
    return AuthService(
        settings=settings,
        users=UserRepository(db),
        companies=CompanyRepository(db),
        tokens=TokenService(settings, RefreshTokenRepository(db), AuthSessionRepository(db)),
        throttle=get_throttle(db, settings),
        mfa=get_mfa_service(db, settings),
        reset_tokens=PasswordResetTokenRepository(db),
        verification_tokens=EmailVerificationTokenRepository(db),
        invitations=InvitationTokenRepository(db),
        employees=EmployeeRepository(db),
        email=email,
        audit=AuditService(AuditLogRepository(db)),
    )


RequestMetaDep = Annotated[RequestMeta, Depends(on_event_loop(get_request_meta))]
UserRepoDep = Annotated[UserRepository, Depends(on_event_loop(get_user_repository))]
CompanyRepoDep = Annotated[CompanyRepository, Depends(on_event_loop(get_company_repository))]
RoleRepoDep = Annotated[RoleRepository, Depends(on_event_loop(get_role_repository))]
PermissionRepoDep = Annotated[PermissionRepository, Depends(on_event_loop(get_permission_repository))]
AuthServiceDep = Annotated[AuthService, Depends(on_event_loop(get_auth_service))]
MfaServiceDep = Annotated[MfaService, Depends(on_event_loop(get_mfa_service))]


def get_employee_repository(db: DbDep) -> EmployeeRepository:
    return EmployeeRepository(db)


def get_scope_service(db: DbDep) -> AccessScopeService:
    return AccessScopeService(EmployeeRepository(db), TeamRepository(db), DepartmentRepository(db))


ScopeServiceDep = Annotated[AccessScopeService, Depends(on_event_loop(get_scope_service))]


def get_employee_service(
    db: DbDep,
    settings: SettingsDep,
    scopes: ScopeServiceDep,
    email: Annotated[EmailService, Depends(on_event_loop(get_email_service))],
) -> EmployeeService:
    return EmployeeService(
        settings=settings,
        employees=EmployeeRepository(db),
        departments=DepartmentRepository(db),
        teams=TeamRepository(db),
        users=UserRepository(db),
        companies=CompanyRepository(db),
        devices=DeviceRepository(db),
        invitations=InvitationTokenRepository(db),
        refresh_tokens=RefreshTokenRepository(db),
        scopes=scopes,
        email=email,
        audit=AuditService(AuditLogRepository(db)),
    )


def get_organization_service(db: DbDep) -> OrganizationService:
    return OrganizationService(
        companies=CompanyRepository(db),
        departments=DepartmentRepository(db),
        teams=TeamRepository(db),
        employees=EmployeeRepository(db),
        audit=AuditService(AuditLogRepository(db)),
    )


def get_device_service(db: DbDep, settings: SettingsDep, scopes: ScopeServiceDep) -> DeviceService:
    return DeviceService(
        settings=settings,
        devices=DeviceRepository(db),
        employees=EmployeeRepository(db),
        scopes=scopes,
        audit=AuditService(AuditLogRepository(db)),
    )


def get_user_admin_service(db: DbDep) -> UserAdminService:
    return UserAdminService(users=UserRepository(db), audit=AuditService(AuditLogRepository(db)))


EmployeeRepoDep = Annotated[EmployeeRepository, Depends(on_event_loop(get_employee_repository))]
EmployeeServiceDep = Annotated[EmployeeService, Depends(on_event_loop(get_employee_service))]
OrganizationServiceDep = Annotated[OrganizationService, Depends(on_event_loop(get_organization_service))]
DeviceServiceDep = Annotated[DeviceService, Depends(on_event_loop(get_device_service))]
UserAdminServiceDep = Annotated[UserAdminService, Depends(on_event_loop(get_user_admin_service))]


def get_activity_feed_service(db: DbDep, scopes: ScopeServiceDep) -> ActivityFeedService:
    return ActivityFeedService(
        audit=AuditLogRepository(db),
        employees=EmployeeRepository(db),
        users=UserRepository(db),
        scopes=scopes,
    )


ActivityFeedServiceDep = Annotated[ActivityFeedService, Depends(on_event_loop(get_activity_feed_service))]


def get_agent_service(db: DbDep, settings: SettingsDep, request: Request) -> AgentService:
    return AgentService(
        settings=settings,
        notifier=get_notifier(request),
        users=UserRepository(db),
        companies=CompanyRepository(db),
        employees=EmployeeRepository(db),
        devices=DeviceRepository(db),
        sessions=WorkSessionRepository(db),
        events=AgentEventRepository(db),
        segments=ActivitySegmentRepository(db),
        daily=ActivityDailyRepository(db),
        websites=WebsiteDailyRepository(db),
        audit=AuditService(AuditLogRepository(db)),
        throttle=get_throttle(db, settings),
    )


def get_presence_service(db: DbDep, settings: SettingsDep, scopes: ScopeServiceDep) -> PresenceService:
    return PresenceService(
        settings=settings,
        companies=CompanyRepository(db),
        employees=EmployeeRepository(db),
        teams=TeamRepository(db),
        devices=DeviceRepository(db),
        sessions=WorkSessionRepository(db),
        segments=ActivitySegmentRepository(db),
        scopes=scopes,
    )


AgentServiceDep = Annotated[AgentService, Depends(on_event_loop(get_agent_service))]
PresenceServiceDep = Annotated[PresenceService, Depends(on_event_loop(get_presence_service))]


def get_activity_service(db: DbDep, scopes: ScopeServiceDep) -> ActivityService:
    return ActivityService(
        companies=CompanyRepository(db),
        employees=EmployeeRepository(db),
        segments=ActivitySegmentRepository(db),
        daily=ActivityDailyRepository(db),
        scopes=scopes,
        audit=AuditService(AuditLogRepository(db)),
    )


ActivityServiceDep = Annotated[ActivityService, Depends(on_event_loop(get_activity_service))]


def get_screenshot_service(
    db: DbDep,
    settings: SettingsDep,
    scopes: ScopeServiceDep,
    storage: ObjectStorageDep,
    signer: UrlSignerDep,
    request: Request,
) -> ScreenshotService:
    return ScreenshotService(
        settings=settings,
        notifier=get_notifier(request),
        companies=CompanyRepository(db),
        employees=EmployeeRepository(db),
        devices=DeviceRepository(db),
        users=UserRepository(db),
        sessions=WorkSessionRepository(db),
        segments=ActivitySegmentRepository(db),
        screenshots=ScreenshotRepository(db),
        scopes=scopes,
        audit=AuditService(AuditLogRepository(db)),
        storage=storage,
        signer=signer,
        live_sessions=LiveSessionRepository(db),
    )


ScreenshotServiceDep = Annotated[ScreenshotService, Depends(on_event_loop(get_screenshot_service))]


def get_live_hub(request: Request) -> LiveHub:
    hub: LiveHub = request.app.state.live_hub
    return hub


def get_live_service(
    db: DbDep,
    settings: SettingsDep,
    scopes: ScopeServiceDep,
    hub: Annotated[LiveHub, Depends(on_event_loop(get_live_hub))],
) -> LiveService:
    return LiveService(
        settings=settings,
        companies=CompanyRepository(db),
        employees=EmployeeRepository(db),
        departments=DepartmentRepository(db),
        teams=TeamRepository(db),
        devices=DeviceRepository(db),
        sessions=LiveSessionRepository(db),
        events=LiveSessionEventRepository(db),
        scopes=scopes,
        audit=AuditService(AuditLogRepository(db)),
        hub=hub,
    )


LiveServiceDep = Annotated[LiveService, Depends(on_event_loop(get_live_service))]


def get_productivity_service(
    db: DbDep, settings: SettingsDep, scopes: ScopeServiceDep
) -> ProductivityService:
    return ProductivityService(
        companies=CompanyRepository(db),
        employees=EmployeeRepository(db),
        departments=DepartmentRepository(db),
        teams=TeamRepository(db),
        users=UserRepository(db),
        rules=ProductivityRuleRepository(db),
        sessions=WorkSessionRepository(db),
        daily=ActivityDailyRepository(db),
        websites=WebsiteDailyRepository(db),
        segments=ActivitySegmentRepository(db),
        tasks=TaskRepository(db),
        time_entries=TimeEntryRepository(db),
        projects=ProjectRepository(db),
        profiles=WorkProfileRepository(db),
        devices=DeviceRepository(db),
        settings=settings,
        scopes=scopes,
        audit=AuditService(AuditLogRepository(db)),
    )


ProductivityServiceDep = Annotated[ProductivityService, Depends(on_event_loop(get_productivity_service))]


def get_work_service(
    db: DbDep, settings: SettingsDep, scopes: ScopeServiceDep, storage: ObjectStorageDep, signer: UrlSignerDep
) -> WorkService:
    return WorkService(
        settings=settings,
        companies=CompanyRepository(db),
        employees=EmployeeRepository(db),
        users=UserRepository(db),
        projects=ProjectRepository(db),
        milestones=MilestoneRepository(db),
        tasks=TaskRepository(db),
        comments=TaskCommentRepository(db),
        activity=TaskActivityRepository(db),
        attachments=TaskAttachmentRepository(db),
        time_entries=TimeEntryRepository(db),
        scopes=scopes,
        audit=AuditService(AuditLogRepository(db)),
        storage=storage,
        signer=signer,
    )


WorkServiceDep = Annotated[WorkService, Depends(on_event_loop(get_work_service))]


def build_report_engine(
    db: Any, settings: Settings, storage: ObjectStorage, signer: UrlSigner
) -> ReportEngine:
    """Also used by the background worker, outside any request."""
    scopes = get_scope_service(db)
    return ReportEngine(
        companies=CompanyRepository(db),
        repos=ReportRepos(
            employees=EmployeeRepository(db),
            departments=DepartmentRepository(db),
            teams=TeamRepository(db),
            users=UserRepository(db),
            profiles=WorkProfileRepository(db),
            sessions=WorkSessionRepository(db),
            screenshots=ScreenshotRepository(db),
            devices=DeviceRepository(db),
            live=LiveSessionRepository(db),
            projects=ProjectRepository(db),
            tasks=TaskRepository(db),
            milestones=MilestoneRepository(db),
            time_entries=TimeEntryRepository(db),
            scopes=scopes,
        ),
        productivity=get_productivity_service(db, settings, scopes),
        work=get_work_service(db, settings, scopes, storage, signer),
    )


def get_report_service(
    request: Request, db: DbDep, settings: SettingsDep, storage: ObjectStorageDep, signer: UrlSignerDep
) -> ReportService:
    worker = getattr(request.app.state, "report_worker", None)
    return ReportService(
        settings=settings,
        jobs=ReportJobRepository(db),
        engine=build_report_engine(db, settings, storage, signer),
        storage=storage,
        signer=signer,
        audit=AuditService(AuditLogRepository(db)),
        wake=worker.wake if worker else (lambda: None),
    )


ReportServiceDep = Annotated[ReportService, Depends(on_event_loop(get_report_service))]


def get_notifier(request: Request) -> Notifier:
    notifier: Notifier | None = getattr(request.app.state, "notifier", None)
    return notifier or NullNotifier()


NotifierDep = Annotated[Notifier, Depends(on_event_loop(get_notifier))]


def get_notification_service(db: DbDep) -> NotificationService:
    return NotificationService(NotificationRepository(db), NotificationPreferencesRepository(db))


NotificationServiceDep = Annotated[NotificationService, Depends(on_event_loop(get_notification_service))]


def get_assistant_service(
    request: Request, db: DbDep, settings: SettingsDep, storage: ObjectStorageDep, signer: UrlSignerDep
) -> AssistantService:
    state = request.app.state
    if not hasattr(state, "assistant_client"):
        state.assistant_client = build_client(settings)
    if not hasattr(state, "assistant_limiter"):
        state.assistant_limiter = RateLimiter()
    scopes = get_scope_service(db)
    client: AssistantClient = state.assistant_client
    return AssistantService(
        settings=settings,
        conversations=ConversationRepository(db),
        services=AssistantServices(
            companies=CompanyRepository(db),
            employees=EmployeeRepository(db),
            departments=DepartmentRepository(db),
            teams=TeamRepository(db),
            scopes=scopes,
            presence=get_presence_service(db, settings, scopes),
            feed=get_activity_feed_service(db, scopes),
            productivity=get_productivity_service(db, settings, scopes),
            work=get_work_service(db, settings, scopes, storage, signer),
            reports=build_report_engine(db, settings, storage, signer),
            notifications=NotificationRepository(db),
        ),
        audit=AuditService(AuditLogRepository(db)),
        claude=client,
        limiter=state.assistant_limiter,
    )


AssistantServiceDep = Annotated[AssistantService, Depends(on_event_loop(get_assistant_service))]


def get_analytics_cache(request: Request) -> AnalyticsCache:
    return AnalyticsCache(request.app.state.broker)


AnalyticsCacheDep = Annotated[AnalyticsCache, Depends(on_event_loop(get_analytics_cache))]


async def bump_analytics(request: Request, principal: CurrentPrincipal) -> AsyncIterator[None]:
    """After a change that affects analytics (rules, profiles, people, roles), cached responses are dropped."""
    yield
    await AnalyticsCache(request.app.state.broker).bump(principal.company_id)


BumpAnalytics = Depends(bump_analytics)
