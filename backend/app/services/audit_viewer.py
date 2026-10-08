"""Read-only view of the audit trail for administrators (`AUDIT_LOG_VIEW`).

The trail itself is append-only: there is no API to edit or delete entries.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from bson import ObjectId
from pymongo import DESCENDING

from app.auth.permissions import Permission
from app.auth.principal import Principal
from app.core.exceptions import BadRequestError, ForbiddenError
from app.repositories.audit_log import AuditLogRepository
from app.repositories.company import CompanyRepository
from app.repositories.organization import EmployeeRepository
from app.repositories.user import UserRepository
from app.schemas.audit import AuditCategoryOut, AuditEntryOut, AuditPage, AuditPerson
from app.schemas.auth import describe_user_agent


@dataclass(frozen=True, slots=True)
class Category:
    key: str
    label: str
    prefixes: tuple[str, ...]
    actions: tuple[str, ...] = ()


CATEGORIES: tuple[Category, ...] = (
    Category("sign_in", "Sign-in & sessions", ("auth.",), ("invitation.accepted",)),
    Category(
        "monitoring_access",
        "Screenshot & live access",
        ("screenshot.", "screenshots.", "live."),
    ),
    Category("reports", "Reports & exports", ("report.",)),
    Category("permissions", "Roles & account access", ("user.",)),
    Category(
        "policies",
        "Monitoring & productivity policies",
        ("policy.", "productivity."),
        ("employee.screenshot_policy_updated",),
    ),
    Category("people", "People & organisation", ("employee.", "department.", "team.", "company.")),
    Category("devices", "Devices & desktop agent", ("device.", "agent.")),
    Category("work", "Projects", ("project.",)),
    Category("assistant", "AI assistant", ("assistant.",)),
)

LABELS: dict[str, str] = {
    "auth.login": "Signed in",
    "auth.login_failed": "Failed sign-in (wrong password)",
    "auth.logout": "Signed out",
    "auth.mfa_failed": "Wrong two-step verification code",
    "auth.mfa_enabled": "Turned on two-step verification",
    "auth.mfa_disabled": "Turned off two-step verification",
    "auth.mfa_recovery_codes_regenerated": "Replaced two-step recovery codes",
    "auth.session_revoked": "Signed out a session",
    "auth.sessions_revoked": "Signed out other sessions",
    "auth.password_changed": "Changed password",
    "auth.password_reset_requested": "Requested a password reset",
    "auth.password_reset": "Reset password",
    "auth.email_verified": "Verified e-mail address",
    "invitation.accepted": "Accepted invitation",
    "company.registered": "Created the workspace",
    "company.updated": "Changed workspace settings",
    "user.role_changed": "Changed a role",
    "user.sessions_revoked": "Signed someone out everywhere",
    "user.mfa_reset": "Reset someone's two-step verification",
    "employee.created": "Added an employee",
    "employee.invited": "Invited an employee",
    "employee.updated": "Changed employee details",
    "employee.status_changed": "Changed employment status",
    "employee.screenshot_policy_updated": "Changed someone's screenshot setting",
    "department.created": "Created a department",
    "department.updated": "Changed a department",
    "department.deleted": "Deleted a department",
    "team.created": "Created a team",
    "team.updated": "Changed a team",
    "team.deleted": "Deleted a team",
    "policy.activity_updated": "Changed the activity policy",
    "policy.screenshots_updated": "Changed the screenshot policy",
    "policy.live_view_updated": "Changed the live view policy",
    "productivity.rule_created": "Added a productivity rule",
    "productivity.rule_updated": "Changed a productivity rule",
    "productivity.rule_deleted": "Deleted a productivity rule",
    "productivity.recommended_rules_loaded": "Loaded recommended productivity rules",
    "productivity.profile_created": "Created a work profile",
    "productivity.profile_updated": "Changed a work profile",
    "productivity.profile_deleted": "Deleted a work profile",
    "productivity.profile_members_changed": "Changed work profile members",
    "screenshot.viewed": "Viewed a screenshot",
    "screenshots.listed": "Browsed screenshots",
    "screenshot.deleted": "Deleted a screenshot",
    "live.session_requested": "Requested a live view",
    "live.session_connected": "Live view started",
    "live.session_denied": "Live view refused",
    "live.session_ended": "Live view ended",
    "report.requested": "Requested a report",
    "report.generated": "Report generated",
    "report.failed": "Report failed",
    "report.downloaded": "Downloaded (exported) a report",
    "report.deleted": "Deleted a report",
    "device.registered": "Registered a device",
    "device.enrolled": "Enrolled a device",
    "device.revoked": "Revoked a device",
    "agent.login_failed": "Failed desktop agent sign-in",
    "project.created": "Created a project",
    "project.updated": "Changed a project",
    "project.archived": "Archived a project",
    "project.members_changed": "Changed project members",
    "assistant.question_answered": "Asked the AI assistant",
}

#: Metadata is shown to administrators, but never anything credential-like.
_HIDDEN_METADATA = re.compile(r"token|secret|password|signature|code", re.IGNORECASE)
MAX_RANGE_DAYS = 366


def category_of(action: str) -> Category | None:
    for category in CATEGORIES:
        if action in category.actions or action.startswith(category.prefixes):
            return category
    return None


def label_of(action: str) -> str:
    return LABELS.get(action) or action.replace("_", " ").replace(".", ": ").capitalize()


def _category_query(category: Category) -> dict[str, Any]:
    clauses: list[dict[str, Any]] = [
        {"action": {"$regex": f"^{re.escape(prefix)}"}} for prefix in category.prefixes
    ]
    if category.actions:
        clauses.append({"action": {"$in": list(category.actions)}})
    return {"$or": clauses}


class AuditViewer:
    def __init__(
        self,
        logs: AuditLogRepository,
        users: UserRepository,
        employees: EmployeeRepository,
        companies: CompanyRepository,
    ) -> None:
        self._logs = logs
        self._users = users
        self._employees = employees
        self._companies = companies

    @staticmethod
    def require(principal: Principal) -> None:
        if Permission.AUDIT_LOG_VIEW not in principal.permissions:
            raise ForbiddenError(
                "You do not have permission to view the audit log.",
                code="insufficient_permissions",
                details={"missing": [Permission.AUDIT_LOG_VIEW.value]},
            )

    def categories(self, principal: Principal) -> list[AuditCategoryOut]:
        self.require(principal)
        return [AuditCategoryOut(key=c.key, label=c.label) for c in CATEGORIES]

    async def search(
        self,
        principal: Principal,
        *,
        category: str | None,
        actor_user_id: ObjectId | None,
        employee_id: ObjectId | None,
        start: date | None,
        end: date | None,
        page: int,
        page_size: int,
    ) -> AuditPage:
        self.require(principal)
        query: dict[str, Any] = {}
        if category:
            found = next((c for c in CATEGORIES if c.key == category), None)
            if found is None:
                raise BadRequestError(
                    "Unknown category.", code="invalid_category", details={"field": "category"}
                )
            query.update(_category_query(found))
        if actor_user_id:
            query["actor_user_id"] = actor_user_id
        if employee_id:
            query["subject_employee_id"] = employee_id
        if start or end:
            if start and end and end < start:
                raise BadRequestError("The end date is before the start date.", code="invalid_range")
            if start and end and (end - start).days > MAX_RANGE_DAYS:
                raise BadRequestError("Choose at most a year.", code="range_too_long")
            company = await self._companies.get_by_id(principal.company_id)
            zone = ZoneInfo(company.timezone if company else "UTC")
            bounds: dict[str, datetime] = {}
            if start:
                bounds["$gte"] = datetime.combine(start, time.min, zone)
            if end:
                bounds["$lt"] = datetime.combine(end + timedelta(days=1), time.min, zone)
            query["created_at"] = bounds

        total = await self._logs.count(principal.company_id, query)
        entries = await self._logs.find_many(
            principal.company_id,
            query,
            sort=[("created_at", DESCENDING), ("_id", DESCENDING)],
            skip=(page - 1) * page_size,
            limit=page_size,
        )
        users = await self._users.find_by_ids(
            principal.company_id, [e.actor_user_id for e in entries if e.actor_user_id]
        )
        people = await self._employees.find_by_ids(
            principal.company_id, [e.subject_employee_id for e in entries if e.subject_employee_id]
        )
        items = []
        for e in entries:
            actor = users.get(e.actor_user_id) if e.actor_user_id else None
            subject = people.get(e.subject_employee_id) if e.subject_employee_id else None
            category_found = category_of(e.action)
            items.append(
                AuditEntryOut(
                    id=str(e.id),
                    at=e.created_at,
                    action=e.action,
                    label=label_of(e.action),
                    category=category_found.key if category_found else None,
                    actor=AuditPerson(id=str(actor.id), name=actor.full_name, email=actor.email)
                    if actor
                    else None,
                    subject=AuditPerson(id=str(subject.id), name=subject.full_name, email=subject.email)
                    if subject
                    else None,
                    target_type=e.target_type,
                    target_id=e.target_id,
                    ip_address=e.ip_address,
                    device=describe_user_agent(e.user_agent) if e.user_agent else None,
                    details={
                        k: v
                        for k, v in e.metadata.items()
                        if not _HIDDEN_METADATA.search(k)
                        and isinstance(v, str | int | float | bool | list | None)
                    },
                )
            )
        return AuditPage.build(items, total, page, page_size)
