"""Builds the monitoring policy every member can read, from the workspace's live settings.

Nothing here is boilerplate that could drift from reality: each statement is derived from the current policies, the
person's own effective screenshot setting, the role catalogue, the access-scope rules and the retention values the
system actually enforces.
"""

from __future__ import annotations

from pymongo import DESCENDING

from app.auth.permissions import ROLE_CATALOG, Permission, Role
from app.auth.principal import Principal
from app.core.config import Settings
from app.core.exceptions import NotFoundError
from app.models.company import Company
from app.models.organization import Employee, ScreenshotMode
from app.models.user import UserStatus
from app.repositories.activity import SEGMENT_RETENTION_SECONDS
from app.repositories.agent import EVENT_RETENTION_SECONDS
from app.repositories.audit_log import AuditLogRepository
from app.repositories.company import CompanyRepository
from app.repositories.notification import RETENTION as NOTIFICATION_RETENTION
from app.repositories.organization import EmployeeRepository
from app.repositories.user import UserRepository
from app.schemas.privacy import MonitoringPolicy, PolicyAccess, PolicyContact, PolicySection
from app.services.screenshot_policy import effective_policy

_POLICY_ACTIONS = (
    "policy.activity_updated",
    "policy.screenshots_updated",
    "policy.live_view_updated",
    "employee.screenshot_policy_updated",
)
_DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_KEPT = (
    "Kept while your workspace exists (removed when an administrator deletes the record or the workspace)."
)

#: Everything WorkPulse is built never to collect. The agent has no code to capture these, and the API rejects
#: unknown fields in what the agent sends.
NEVER_COLLECTED = [
    "Keystrokes or anything you type (idle detection only reads the time of your last keyboard or mouse input)",
    "Passwords or other credentials",
    "Clipboard contents",
    "Microphone, camera or audio",
    "The content of e-mails, chats, documents or files",
    "Window titles of password managers, sign-in prompts, messaging, e-mail and private/incognito browser windows",
    "Full web addresses (at most the site's domain, and only when website tracking is switched on)",
    "Screenshots or activity while you're signed out of the desktop agent or idle",
]


def _scope_text(role: Role) -> str:
    if role in (Role.SUPER_ADMIN, Role.COMPANY_ADMIN):
        return "Everyone in the workspace"
    if role == Role.MANAGER:
        return "People who report to them (directly or indirectly), their teams and the departments they head"
    if role == Role.TEAM_LEAD:
        return "People who report to them and members of teams they lead"
    return "Only themselves"


def _access(permission: Permission | None) -> list[PolicyAccess]:
    rows = [PolicyAccess(role="You", scope="Your own data")]
    for info in sorted(ROLE_CATALOG.values(), key=lambda r: -r.level):
        if info.key in (Role.SUPER_ADMIN, Role.EMPLOYEE):
            continue
        if permission is None or permission in info.permissions:
            rows.append(PolicyAccess(role=info.name, scope=_scope_text(info.key)))
    return rows


def _days(seconds: int) -> str:
    return f"{seconds // 86_400} days"


def _hours(hours: int) -> str:
    return f"{hours // 24} days" if hours % 24 == 0 else f"{hours} hours"


def _work_days(days: list[int]) -> str:
    ordered = sorted(set(days))
    if ordered == [1, 2, 3, 4, 5]:
        return "on weekdays"
    if ordered == [1, 2, 3, 4, 5, 6, 7]:
        return "every day"
    return "on " + ", ".join(_DAY_NAMES[d - 1] for d in ordered if 1 <= d <= 7)


class PrivacyPolicyService:
    def __init__(
        self,
        settings: Settings,
        companies: CompanyRepository,
        employees: EmployeeRepository,
        users: UserRepository,
        audit: AuditLogRepository,
    ) -> None:
        self._settings = settings
        self._companies = companies
        self._employees = employees
        self._users = users
        self._audit = audit

    async def policy(self, principal: Principal) -> MonitoringPolicy:
        company = await self._companies.get_by_id(principal.company_id)
        if company is None:
            raise NotFoundError("Workspace not found.")
        employee = (
            await self._employees.get_by_id(principal.company_id, principal.user.employee_id)
            if principal.user.employee_id
            else None
        )
        changes = await self._audit.find_many(
            principal.company_id,
            {"action": {"$in": list(_POLICY_ACTIONS)}},
            sort=[("created_at", DESCENDING)],
            limit=1,
        )
        admins = await self._users.find_many(
            principal.company_id,
            {"role": Role.COMPANY_ADMIN.value, "status": UserStatus.ACTIVE.value},
            sort=[("full_name", 1)],
            limit=5,
        )
        personal = bool(employee and employee.screenshot_override.mode != ScreenshotMode.INHERIT)
        return MonitoringPolicy(
            workspace=company.name,
            timezone=company.timezone,
            last_changed_at=changes[0].created_at if changes else None,
            personal_screenshot_setting=personal,
            sections=[
                self._presence(),
                self._activity(company),
                self._screenshots(company, employee),
                self._live(company),
                self._work(),
                self._audit_trail(),
                self._derived(),
            ],
            never_collected=NEVER_COLLECTED,
            contacts=[PolicyContact(name=a.full_name, email=a.email) for a in admins],
        )

    def _presence(self) -> PolicySection:
        return PolicySection(
            key="presence",
            title="Work sessions & presence",
            status="on",
            summary="While you're signed in to the desktop agent",
            what=[
                "When you start and end work sessions in the desktop agent",
                "Whether you're active, idle or away (from the time of your last keyboard or mouse input)",
                "The computer's name and operating system, and the agent version",
            ],
            when="Only while the WorkPulse desktop agent is running and you're signed in to it.",
            why="Work hours, attendance and the live 'who is working' view.",
            retention=f"Work sessions: {_KEPT.lower()} Raw agent events: {_days(EVENT_RETENTION_SECONDS)}.",
            access=_access(Permission.ACTIVITY_VIEW),
            safeguards=["The agent shows its status in the system tray at all times"],
        )

    def _activity(self, company: Company) -> PolicySection:
        p = company.activity_policy
        if not p.track_applications:
            return PolicySection(
                key="activity",
                title="Applications & websites",
                status="off",
                summary="Not collected in this workspace",
                what=[],
                when="Not collected.",
                why="An administrator has switched application tracking off.",
                retention="Nothing is stored.",
                access=_access(Permission.ACTIVITY_VIEW),
                safeguards=[],
            )
        what = ["The name of the application in the foreground and how long it was active"]
        what.append(
            "Window titles, with links, e-mail addresses and long numbers removed"
            if p.capture_window_titles
            else "Not window titles (switched off)"
        )
        what.append(
            "The domain of websites you visit in supported browsers (e.g. example.com), never full addresses"
            if p.track_websites
            else "Not websites (switched off)"
        )
        safeguards = [
            "Window titles of password managers, sign-in prompts, messaging, e-mail and private browser windows "
            "are never recorded",
            "The server re-applies these rules, so an outdated agent can't store more than the policy allows",
        ]
        if p.excluded_apps:
            safeguards.append("Not tracked at all: " + ", ".join(sorted(p.excluded_apps)[:20]))
        parts = ["applications"]
        if p.capture_window_titles:
            parts.append("window titles")
        if p.track_websites:
            parts.append("website domains")
        return PolicySection(
            key="activity",
            title="Applications & websites",
            status="on",
            summary="Collected: " + ", ".join(parts),
            what=what,
            when="During work sessions, while you're active (nothing while you're idle).",
            why="Time per application and project, and productivity summaries based on your workspace's rules.",
            retention=f"Detailed activity: {_days(SEGMENT_RETENTION_SECONDS)}. Daily totals: {_KEPT.lower()}",
            access=_access(Permission.ACTIVITY_VIEW),
            safeguards=safeguards,
        )

    def _screenshots(self, company: Company, employee: Employee | None) -> PolicySection:
        base = company.screenshot_policy
        enabled = effective_policy(company, employee).enabled if employee else base.enabled
        if not enabled:
            return PolicySection(
                key="screenshots",
                title="Screenshots",
                status="off",
                summary="Not taken of your screen" if employee else "Not taken",
                what=[],
                when="Not taken.",
                why="Screenshots are switched off.",
                retention="Nothing is stored.",
                access=_access(Permission.SCREENSHOT_VIEW),
                safeguards=[],
            )
        hours = (
            f"{base.work_start}–{base.work_end} {_work_days(base.work_days)} ({company.timezone})"  # noqa: RUF001
            if base.work_hours_only
            else "at any time of day"
        )
        return PolicySection(
            key="screenshots",
            title="Screenshots",
            status="on",
            summary=f"About every {base.interval_minutes} minutes, {hours}",
            what=["An image of your screen(s), with a smaller preview"],
            when=(
                f"About every {base.interval_minutes} minutes during work sessions while you're active, {hours}. "
                "Never while you're idle or signed out of the agent."
            ),
            why="Verifying work on tasks and projects, and supporting billing or compliance where your company needs it.",
            retention=f"Deleted automatically after {base.retention_days} days.",
            access=_access(Permission.SCREENSHOT_VIEW),
            safeguards=[
                "Encrypted when stored; opened only through short-lived links tied to the person viewing",
                "Every view is recorded in the audit trail",
                "The tray icon shows when screenshots are being taken",
            ],
        )

    def _live(self, company: Company) -> PolicySection:
        p = company.live_policy
        if not p.enabled:
            return PolicySection(
                key="live",
                title="Live screen viewing",
                status="off",
                summary="Switched off",
                what=[],
                when="Not available.",
                why="An administrator has switched live viewing off.",
                retention="Nothing is stored.",
                access=_access(Permission.LIVE_STREAM_VIEW),
                safeguards=[],
            )
        return PolicySection(
            key="live",
            title="Live screen viewing",
            status="on_request",
            summary=f"Only on request, up to {p.max_session_minutes} minutes at a time",
            what=[
                "A live view of your screen, streamed directly to the person who asked. It is not recorded."
            ],
            when="Only when someone who is allowed to starts a session while you're online in the desktop agent.",
            why="Real-time support and supervision where your company needs it.",
            retention="The stream isn't stored. Who viewed whom and when is kept in the session log: "
            + _KEPT.lower(),
            access=_access(Permission.LIVE_STREAM_VIEW),
            safeguards=[
                "You're notified on your computer when a live view starts, and the tray icon shows it",
                f"Sessions end automatically after {p.max_session_minutes} minutes",
                "Every session (start, end, who) is recorded in the audit trail",
            ],
        )

    def _work(self) -> PolicySection:
        return PolicySection(
            key="work",
            title="Projects, tasks & time",
            status="on",
            summary="What you and your team enter",
            what=["Tasks, comments and attachments", "Time you log or track with the task timer"],
            when="When you or a colleague add them.",
            why="Planning, progress and time spent per project.",
            retention=_KEPT,
            access=[
                PolicyAccess(role="Project members", scope="The projects they belong to"),
                *_access(Permission.PROJECT_MANAGE)[1:],
            ],
            safeguards=["Attachments are encrypted when stored"],
        )

    def _audit_trail(self) -> PolicySection:
        return PolicySection(
            key="audit",
            title="Security audit trail",
            status="on",
            summary="Sign-ins and access to monitoring data",
            what=[
                "Sign-ins, sign-outs and failed attempts, with the IP address and browser",
                "Who viewed screenshots or live screens, exported reports, or changed policies, roles and people",
            ],
            when="When these events happen.",
            why="Security, and accountability for everyone who can see monitoring data.",
            retention=_KEPT,
            access=[
                PolicyAccess(role=ROLE_CATALOG[Role.COMPANY_ADMIN].name, scope="Everyone in the workspace")
            ],
            safeguards=["The trail can't be edited or deleted through WorkPulse"],
        )

    def _derived(self) -> PolicySection:
        return PolicySection(
            key="derived",
            title="Reports, alerts & summaries",
            status="on",
            summary="Built from the data above",
            what=[
                "Reports and productivity summaries, which show their inputs and formulas",
                "Alerts such as 'offline during a work session' or 'task overdue'",
                "Answers from the AI assistant, if your workspace has switched it on",
            ],
            when="When someone with access asks for them, or when an alert condition occurs.",
            why="Summaries for managers and you. They describe recorded work signals, not your character or worth.",
            retention=(
                f"Report files: {_hours(self._settings.report_retention_hours)}. "
                f"Alerts: {NOTIFICATION_RETENTION.days} days. AI assistant conversations: 90 days."
            ),
            access=_access(Permission.REPORT_VIEW),
            safeguards=[
                "Report files are encrypted and can only be downloaded by the person who requested them",
                "Exports are recorded in the audit trail",
            ],
        )
