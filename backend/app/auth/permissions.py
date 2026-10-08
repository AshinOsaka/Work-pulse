"""Role & permission catalogue — the single source of truth for authorization.

System roles are defined in code and mirrored into the `roles` and
`permissions` collections at startup so that future phases can add
company-defined custom roles without changing the authorization contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Permission(StrEnum):
    EMPLOYEE_VIEW = "EMPLOYEE_VIEW"
    EMPLOYEE_MANAGE = "EMPLOYEE_MANAGE"
    LIVE_STREAM_VIEW = "LIVE_STREAM_VIEW"
    SCREENSHOT_VIEW = "SCREENSHOT_VIEW"
    ACTIVITY_VIEW = "ACTIVITY_VIEW"
    REPORT_VIEW = "REPORT_VIEW"
    REPORT_EXPORT = "REPORT_EXPORT"
    TASK_MANAGE = "TASK_MANAGE"
    PROJECT_MANAGE = "PROJECT_MANAGE"
    POLICY_MANAGE = "POLICY_MANAGE"
    USER_MANAGE = "USER_MANAGE"
    AUDIT_LOG_VIEW = "AUDIT_LOG_VIEW"


class Role(StrEnum):
    SUPER_ADMIN = "SUPER_ADMIN"
    COMPANY_ADMIN = "COMPANY_ADMIN"
    MANAGER = "MANAGER"
    TEAM_LEAD = "TEAM_LEAD"
    EMPLOYEE = "EMPLOYEE"


@dataclass(frozen=True, slots=True)
class PermissionInfo:
    key: Permission
    name: str
    description: str
    category: str


@dataclass(frozen=True, slots=True)
class RoleInfo:
    key: Role
    name: str
    description: str
    level: int
    permissions: frozenset[Permission]


PERMISSION_CATALOG: dict[Permission, PermissionInfo] = {
    p.key: p
    for p in (
        PermissionInfo(
            Permission.EMPLOYEE_VIEW, "View employees", "View employee profiles and directory.", "People"
        ),
        PermissionInfo(
            Permission.EMPLOYEE_MANAGE, "Manage employees", "Create, update and offboard employees.", "People"
        ),
        PermissionInfo(
            Permission.LIVE_STREAM_VIEW,
            "View live screens",
            "Watch live screen streams of employees.",
            "Monitoring",
        ),
        PermissionInfo(
            Permission.SCREENSHOT_VIEW,
            "View screenshots",
            "View captured employee screenshots.",
            "Monitoring",
        ),
        PermissionInfo(
            Permission.ACTIVITY_VIEW,
            "View activity",
            "View application, website and idle activity.",
            "Monitoring",
        ),
        PermissionInfo(
            Permission.REPORT_VIEW, "View reports", "Access workforce analytics and reports.", "Reporting"
        ),
        PermissionInfo(
            Permission.REPORT_EXPORT, "Export reports", "Export reports to CSV, XLSX and PDF.", "Reporting"
        ),
        PermissionInfo(Permission.TASK_MANAGE, "Manage tasks", "Create, assign and update tasks.", "Work"),
        PermissionInfo(
            Permission.PROJECT_MANAGE, "Manage projects", "Create and configure projects.", "Work"
        ),
        PermissionInfo(
            Permission.POLICY_MANAGE,
            "Manage policies",
            "Configure monitoring, privacy and workspace policies.",
            "Administration",
        ),
        PermissionInfo(
            Permission.USER_MANAGE, "Manage users", "Invite users and assign roles.", "Administration"
        ),
        PermissionInfo(
            Permission.AUDIT_LOG_VIEW,
            "View audit log",
            "Review security and administrative events.",
            "Administration",
        ),
    )
}

_ALL = frozenset(Permission)

_MANAGER = frozenset(
    {
        Permission.EMPLOYEE_VIEW,
        Permission.LIVE_STREAM_VIEW,
        Permission.SCREENSHOT_VIEW,
        Permission.ACTIVITY_VIEW,
        Permission.REPORT_VIEW,
        Permission.REPORT_EXPORT,
        Permission.TASK_MANAGE,
        Permission.PROJECT_MANAGE,
    }
)

_TEAM_LEAD = frozenset(
    {
        Permission.EMPLOYEE_VIEW,
        Permission.SCREENSHOT_VIEW,
        Permission.ACTIVITY_VIEW,
        Permission.REPORT_VIEW,
        Permission.TASK_MANAGE,
    }
)

# Employees implicitly access their own data; no tenant-wide permissions.
_EMPLOYEE: frozenset[Permission] = frozenset()

ROLE_CATALOG: dict[Role, RoleInfo] = {
    r.key: r
    for r in (
        RoleInfo(Role.SUPER_ADMIN, "Super Admin", "Platform operator with unrestricted access.", 100, _ALL),
        RoleInfo(
            Role.COMPANY_ADMIN, "Company Admin", "Full administrative control of a workspace.", 80, _ALL
        ),
        RoleInfo(Role.MANAGER, "Manager", "Oversees departments, projects and reporting.", 60, _MANAGER),
        RoleInfo(Role.TEAM_LEAD, "Team Lead", "Leads a team and manages its tasks.", 40, _TEAM_LEAD),
        RoleInfo(Role.EMPLOYEE, "Employee", "Standard member with access to their own data.", 20, _EMPLOYEE),
    )
}


def _role_info(role: Role | str) -> RoleInfo | None:
    try:
        return ROLE_CATALOG.get(Role(role))
    except ValueError:
        return None


def permissions_for_role(role: Role | str) -> frozenset[Permission]:
    info = _role_info(role)
    return info.permissions if info else frozenset()


def role_level(role: Role | str) -> int:
    info = _role_info(role)
    return info.level if info else 0


def can_assign_role(actor: Role | str, target: Role | str) -> bool:
    """Whether `actor` may grant `target` (or manage a user who holds it).

    Actors may assign roles up to and including their own level, so a workspace
    can have several Company Admins. Super Admin is reserved for platform staff.
    """
    if actor == Role.SUPER_ADMIN:
        return True
    if target == Role.SUPER_ADMIN:
        return False
    return role_level(actor) >= role_level(target) > 0
