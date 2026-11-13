"""The notification types: what each means, who receives it, and its defaults."""

from __future__ import annotations

from dataclasses import dataclass

from app.auth.permissions import Permission
from app.models.notification import NotificationType, Severity

T = NotificationType


@dataclass(frozen=True, slots=True)
class TypeInfo:
    key: NotificationType
    label: str
    description: str
    #: Who receives it, in plain words (shown in preferences).
    audience: str
    severity: Severity
    #: Users without this permission never receive the type (None: anyone it concerns).
    permission: Permission | None
    #: Default channels for new users. E-mail is opt-in everywhere.
    in_app: bool = True


CATALOG: dict[NotificationType, TypeInfo] = {
    t.key: t
    for t in (
        TypeInfo(
            T.EMPLOYEE_OFFLINE,
            "Employee offline",
            "Someone's desktop agent stopped reporting while their work session was still open.",
            "People who can view that employee's activity",
            Severity.WARNING,
            Permission.ACTIVITY_VIEW,
        ),
        TypeInfo(
            T.DEVICE_OFFLINE,
            "Device offline",
            "A registered computer hasn't been seen for a day (agent removed, computer unused or broken).",
            "People who can view that employee's activity",
            Severity.WARNING,
            Permission.ACTIVITY_VIEW,
        ),
        TypeInfo(
            T.EXTENDED_IDLE,
            "Extended idle",
            "No keyboard or mouse input for 30+ minutes during a work session — often a meeting or a break.",
            "People who can view that employee's activity",
            Severity.INFO,
            Permission.ACTIVITY_VIEW,
            in_app=False,  # common and usually innocent: off unless someone opts in
        ),
        TypeInfo(
            T.SHIFT_STARTED,
            "Shift started",
            "The first work session of the day started (from the desktop agent).",
            "People who can view that employee's activity",
            Severity.INFO,
            Permission.ACTIVITY_VIEW,
            in_app=False,
        ),
        TypeInfo(
            T.SHIFT_ENDED,
            "Shift ended",
            "A work session ended (from the desktop agent).",
            "People who can view that employee's activity",
            Severity.INFO,
            Permission.ACTIVITY_VIEW,
            in_app=False,
        ),
        TypeInfo(
            T.TASK_OVERDUE,
            "Task overdue",
            "A task passed its due date without being completed.",
            "Its assignees and the project owner",
            Severity.WARNING,
            None,
        ),
        TypeInfo(
            T.PROJECT_DEADLINE,
            "Project deadline",
            "A project is due within two days, or its due date passed with work still open.",
            "The project owner and project managers",
            Severity.WARNING,
            None,
        ),
        TypeInfo(
            T.LIVE_SESSION_STARTED,
            "Live session started",
            "Someone started viewing a screen live.",
            "Administrators",
            Severity.INFO,
            Permission.POLICY_MANAGE,
        ),
        TypeInfo(
            T.LIVE_SESSION_ENDED,
            "Live session ended",
            "A live screen view ended.",
            "Administrators",
            Severity.INFO,
            Permission.POLICY_MANAGE,
        ),
        TypeInfo(
            T.SCREENSHOT_POLICY,
            "Screenshot policy changed",
            "Screenshot monitoring was turned on or off, or its settings changed.",
            "Everyone it affects, and administrators",
            Severity.INFO,
            None,
        ),
        TypeInfo(
            T.TIME_CLAIM_LOGGED,
            "Meeting time logged",
            "Someone logged time away from the computer (a meeting, client visit or call), or asked for approval "
            "of time over the daily limit.",
            "People who manage that employee's time claims",
            Severity.INFO,
            Permission.TIME_CLAIM_MANAGE,
        ),
        TypeInfo(
            T.TIME_CLAIM_REVIEWED,
            "Meeting time approved, changed or added",
            "A manager approved, rejected, changed, deleted or added time away from the computer for you.",
            "The person who logged the time",
            Severity.INFO,
            None,
        ),
        TypeInfo(
            T.AGENT_CLOSED,
            "WorkPulse closed",
            "Someone's desktop agent was closed — with End Task, Quit in the tray, or a crash. It starts again "
            "by itself within about a minute.",
            "People who can view that employee's activity",
            Severity.WARNING,
            Permission.ACTIVITY_VIEW,
        ),
        TypeInfo(
            T.AGENT_PROTECTION,
            "WorkPulse start-up turned off",
            "On someone's computer, WorkPulse's Start with Windows setting was switched off, or its restart task "
            "was deleted or disabled.",
            "People who can view that employee's activity",
            Severity.WARNING,
            Permission.ACTIVITY_VIEW,
        ),
    )
}
