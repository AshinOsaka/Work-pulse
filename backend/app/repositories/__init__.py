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
from app.repositories.base import BaseRepository, GlobalRepository, TenantRepository
from app.repositories.company import CompanyRepository
from app.repositories.live import LiveSessionEventRepository, LiveSessionRepository
from app.repositories.notification import (
    AlertEventRepository,
    NotificationPreferencesRepository,
    NotificationRepository,
)
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
from app.services.productivity.day_cache import ProductivityDayRepository

# Every repository registered here gets its indexes created at startup.
ALL_REPOSITORIES: tuple[type[BaseRepository], ...] = (  # type: ignore[type-arg]
    CompanyRepository,
    UserRepository,
    RoleRepository,
    PermissionRepository,
    DepartmentRepository,
    TeamRepository,
    EmployeeRepository,
    DeviceRepository,
    RefreshTokenRepository,
    PasswordResetTokenRepository,
    EmailVerificationTokenRepository,
    InvitationTokenRepository,
    AuditLogRepository,
    WorkSessionRepository,
    AgentEventRepository,
    ActivitySegmentRepository,
    ActivityDailyRepository,
    ScreenshotRepository,
    LiveSessionRepository,
    LiveSessionEventRepository,
    ProductivityRuleRepository,
    WorkProfileRepository,
    WebsiteDailyRepository,
    ProjectRepository,
    MilestoneRepository,
    TaskRepository,
    TaskCommentRepository,
    TaskActivityRepository,
    TaskAttachmentRepository,
    TimeEntryRepository,
    ReportJobRepository,
    ConversationRepository,
    NotificationRepository,
    NotificationPreferencesRepository,
    AlertEventRepository,
    AuthSessionRepository,
    RateLimitRepository,
    ProductivityDayRepository,
)

__all__ = [
    "ALL_REPOSITORIES",
    "AgentEventRepository",
    "AuditLogRepository",
    "BaseRepository",
    "CompanyRepository",
    "DepartmentRepository",
    "DeviceRepository",
    "EmailVerificationTokenRepository",
    "EmployeeRepository",
    "GlobalRepository",
    "InvitationTokenRepository",
    "LiveSessionEventRepository",
    "LiveSessionRepository",
    "PasswordResetTokenRepository",
    "PermissionRepository",
    "RefreshTokenRepository",
    "RoleRepository",
    "ScreenshotRepository",
    "TeamRepository",
    "TenantRepository",
    "UserRepository",
    "WorkSessionRepository",
]
