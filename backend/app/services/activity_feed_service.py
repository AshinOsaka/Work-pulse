"""Organisation activity feed, derived from the audit trail.

Only workforce-relevant events are exposed (never sign-in attempts or security
events), and they are filtered by the caller's employee access scope: a
manager sees events about people in their reporting line, nothing else.
Structural events (departments, teams) are visible to company-wide viewers.
"""

from __future__ import annotations

from typing import Any

from bson import ObjectId

from app.auth.principal import Principal
from app.models.audit_log import AuditLog
from app.repositories.audit_log import AuditLogRepository
from app.repositories.organization import EmployeeRepository
from app.repositories.user import UserRepository
from app.schemas.activity import ActivityActor, ActivityItem, ActivitySubject
from app.services.access_scope import AccessScopeService
from app.services.helpers import parse_ref

EMPLOYEE_EVENTS = (
    "employee.created",
    "employee.updated",
    "employee.status_changed",
    "employee.invited",
    "invitation.accepted",
    "device.registered",
    "device.revoked",
    "user.role_changed",
    "device.enrolled",
    "work.session_started",
    "work.session_stopped",
)
STRUCTURE_EVENTS = ("department.created", "department.deleted", "team.created", "team.deleted")

# Metadata keys that are safe and useful to show in a feed.
_PUBLIC_METADATA = {"from", "to", "role", "fields", "name", "os", "invited", "method", "duration_minutes"}


class ActivityFeedService:
    def __init__(
        self,
        *,
        audit: AuditLogRepository,
        employees: EmployeeRepository,
        users: UserRepository,
        scopes: AccessScopeService,
    ) -> None:
        self._audit = audit
        self._employees = employees
        self._users = users
        self._scopes = scopes

    async def recent(self, principal: Principal, *, limit: int, team_id: str | None) -> list[ActivityItem]:
        company_id = principal.company_id
        scope = await self._scopes.employee_scope(principal)
        team = parse_ref(team_id, "team_id")

        if scope.unrestricted and team is None:
            events = await self._audit.recent(company_id, EMPLOYEE_EVENTS + STRUCTURE_EVENTS, limit=limit)
        else:
            filters: list[dict[str, Any]] = [
                f for f in (scope.filter, {"team_id": team} if team else None) if f
            ]
            query = {"$and": filters} if len(filters) > 1 else (filters[0] if filters else None)
            visible = await self._employees.ids_matching(company_id, query)
            events = await self._audit.recent(
                company_id, EMPLOYEE_EVENTS, subject_employee_ids=visible, limit=limit
            )

        return await self._present(company_id, events)

    async def _present(self, company_id: ObjectId, events: list[AuditLog]) -> list[ActivityItem]:
        actors = await self._users.find_by_ids(
            company_id, [e.actor_user_id for e in events if e.actor_user_id]
        )
        subjects = await self._employees.find_by_ids(
            company_id, [e.subject_employee_id for e in events if e.subject_employee_id]
        )
        items: list[ActivityItem] = []
        for event in events:
            actor = actors.get(event.actor_user_id) if event.actor_user_id else None
            subject = subjects.get(event.subject_employee_id) if event.subject_employee_id else None
            items.append(
                ActivityItem(
                    id=str(event.id),
                    action=event.action,
                    occurred_at=event.created_at,
                    actor=ActivityActor(
                        id=str(actor.id),
                        name=actor.full_name,
                        employee_id=str(actor.employee_id) if actor.employee_id else None,
                    )
                    if actor
                    else None,
                    subject=ActivitySubject(employee_id=str(subject.id), name=subject.full_name)
                    if subject
                    else None,
                    metadata={k: v for k, v in event.metadata.items() if k in _PUBLIC_METADATA},
                )
            )
        return items
