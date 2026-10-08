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
            "The person being viewed, and administrators",
            Severity.INFO,
            None,
        ),
        TypeInfo(
            T.LIVE_SESSION_ENDED,
            "Live session ended",
            "A live screen view ended.",
            "The person who was viewed, and administrators",
            Severity.INFO,
            None,
        ),
        TypeInfo(
            T.SCREENSHOT_POLICY,
            "Screenshot policy changed",
            "Screenshot monitoring was turned on or off, or its settings changed.",
            "Everyone it affects, and administrators",
            Severity.INFO,
            None,
        ),
    )
}
