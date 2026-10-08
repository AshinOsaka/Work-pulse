"""Row-level access scope for employee data.

Permissions say *what* a role may do; the scope says *which employees* it may
do it to. Every employee read goes through an `EmployeeScope`:

| Role                         | Visible employees                                              |
|------------------------------|----------------------------------------------------------------|
| SUPER_ADMIN, COMPANY_ADMIN   | everyone in the company                                        |
| MANAGER                      | self, reporting tree, members of led teams, headed departments |
| TEAM_LEAD                    | self, reporting tree, members of led teams                     |
| EMPLOYEE                     | self only                                                      |

Out-of-scope records are reported as *not found*, never *forbidden*, so their
existence is not disclosed. Tenant isolation is enforced underneath this by
`TenantRepository` (every query carries `company_id`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bson import ObjectId

from app.auth.permissions import Role
from app.auth.principal import Principal
from app.repositories.organization import DepartmentRepository, EmployeeRepository, TeamRepository

_UNRESTRICTED_ROLES = frozenset({Role.SUPER_ADMIN, Role.COMPANY_ADMIN})
_NOTHING: dict[str, Any] = {"_id": {"$in": []}}


@dataclass(frozen=True, slots=True)
class EmployeeScope:
    company_id: ObjectId
    unrestricted: bool
    restriction: dict[str, Any] | None = None

    @property
    def filter(self) -> dict[str, Any] | None:
        """Extra Mongo filter to AND with any employee query (None = no restriction)."""
        return None if self.unrestricted else (self.restriction or _NOTHING)


class AccessScopeService:
    def __init__(
        self,
        employees: EmployeeRepository,
        teams: TeamRepository,
        departments: DepartmentRepository,
    ) -> None:
        self._employees = employees
        self._teams = teams
        self._departments = departments

    async def employee_scope(self, principal: Principal) -> EmployeeScope:
        company_id = principal.company_id
        if principal.role in _UNRESTRICTED_ROLES:
            return EmployeeScope(company_id, unrestricted=True)

        own_id = principal.user.employee_id
        if own_id is None:
            return EmployeeScope(company_id, unrestricted=False, restriction=_NOTHING)

        if principal.role not in (Role.MANAGER, Role.TEAM_LEAD):
            return EmployeeScope(company_id, unrestricted=False, restriction={"_id": own_id})

        visible = {own_id} | await self._employees.descendant_ids(company_id, own_id)
        clauses: list[dict[str, Any]] = [{"_id": {"$in": sorted(visible)}}]
        led_teams = await self._teams.ids_led_by(company_id, own_id)
        if led_teams:
            clauses.append({"team_id": {"$in": led_teams}})
        if principal.role == Role.MANAGER:
            headed = await self._departments.ids_headed_by(company_id, own_id)
            if headed:
                clauses.append({"department_id": {"$in": headed}})
        restriction = clauses[0] if len(clauses) == 1 else {"$or": clauses}
        return EmployeeScope(company_id, unrestricted=False, restriction=restriction)

    async def can_access(self, principal: Principal, employee_id: ObjectId) -> bool:
        scope = await self.employee_scope(principal)
        return await self._employees.exists(
            principal.company_id,
            {"$and": [{"_id": employee_id}, scope.filter]} if scope.filter else {"_id": employee_id},
        )
