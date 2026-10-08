"""Organisation structure use-cases: company profile, departments and teams."""

from __future__ import annotations

from collections import Counter
from typing import Any

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.auth.principal import Principal
from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.models.company import Company
from app.models.organization import Department, Employee, EmployeeStatus, Team
from app.repositories.company import CompanyRepository
from app.repositories.organization import DepartmentRepository, EmployeeRepository, TeamRepository
from app.schemas.company import CompanyUpdate
from app.schemas.organization import (
    DepartmentCreate,
    DepartmentOut,
    DepartmentUpdate,
    Ref,
    TeamCreate,
    TeamOut,
    TeamUpdate,
)
from app.services.audit_service import AuditService
from app.services.context import RequestMeta
from app.services.employee_service import employee_ref
from app.services.helpers import parse_id, parse_ref


class OrganizationService:
    def __init__(
        self,
        *,
        companies: CompanyRepository,
        departments: DepartmentRepository,
        teams: TeamRepository,
        employees: EmployeeRepository,
        audit: AuditService,
    ) -> None:
        self._companies = companies
        self._departments = departments
        self._teams = teams
        self._employees = employees
        self._audit = audit

    # ------------------------------------------------------------------ company
    async def update_company(self, principal: Principal, data: CompanyUpdate, meta: RequestMeta) -> Company:
        changes = {k: v for k, v in data.model_dump(exclude_unset=True).items()}
        if "name" in changes and not changes["name"]:
            raise BadRequestError(
                "Company name cannot be empty.", code="invalid_field", details={"field": "name"}
            )
        if "timezone" in changes and changes["timezone"] is None:
            raise BadRequestError(
                "Timezone cannot be empty.", code="invalid_field", details={"field": "timezone"}
            )
        company = await self._companies.update_by_id(principal.company_id, changes) if changes else None
        company = company or await self._companies.get_by_id(principal.company_id)
        if company is None:
            raise NotFoundError("Workspace not found.")
        if changes:
            await self._record(
                principal, "company.updated", "company", company.id, meta, {"fields": sorted(changes)}
            )
        return company

    # ------------------------------------------------------------------ departments
    async def list_departments(self, principal: Principal) -> list[DepartmentOut]:
        company_id = principal.company_id
        departments = await self._departments.list_all(company_id)
        employee_counts = await self._employees.counts_by(company_id, "department_id")
        team_counts = Counter(
            t.department_id for t in await self._teams.list_all(company_id) if t.department_id
        )
        heads = await self._employees.find_by_ids(
            company_id, [d.head_employee_id for d in departments if d.head_employee_id]
        )
        return [
            self._department_out(d, heads, employee_counts.get(d.id, 0), team_counts.get(d.id, 0))
            for d in departments
        ]

    async def get_department(self, principal: Principal, department_id: str) -> DepartmentOut:
        department = await self._load_department(principal.company_id, department_id)
        return await self._department_detail(department)

    async def create_department(
        self, principal: Principal, data: DepartmentCreate, meta: RequestMeta
    ) -> DepartmentOut:
        company_id = principal.company_id
        head_id = await self._validate_employee_ref(company_id, data.head_employee_id, "head_employee_id")
        department = Department(
            company_id=company_id,
            name=data.name,
            description=data.description or None,
            head_employee_id=head_id,
        )
        try:
            await self._departments.create(company_id, department)
        except DuplicateKeyError as exc:
            raise self._name_taken("department") from exc
        await self._record(
            principal, "department.created", "department", department.id, meta, {"name": department.name}
        )
        return await self._department_detail(department)

    async def update_department(
        self, principal: Principal, department_id: str, data: DepartmentUpdate, meta: RequestMeta
    ) -> DepartmentOut:
        company_id = principal.company_id
        department = await self._load_department(company_id, department_id)
        changes = self._clean(
            data.model_dump(exclude_unset=True), required=("name",), optional=("description",)
        )
        if "head_employee_id" in changes:
            changes["head_employee_id"] = await self._validate_employee_ref(
                company_id, changes["head_employee_id"], "head_employee_id"
            )
        if not changes:
            return await self._department_detail(department)
        try:
            updated = await self._departments.update_by_id(company_id, department.id, changes)
        except DuplicateKeyError as exc:
            raise self._name_taken("department") from exc
        if updated is None:
            raise NotFoundError("Department not found.", code="department_not_found")
        await self._record(
            principal, "department.updated", "department", department.id, meta, {"fields": sorted(changes)}
        )
        return await self._department_detail(updated)

    async def delete_department(self, principal: Principal, department_id: str, meta: RequestMeta) -> None:
        company_id = principal.company_id
        department = await self._load_department(company_id, department_id)
        if await self._employees.exists(company_id, {"department_id": department.id}):
            raise ConflictError(
                "Move this department's employees elsewhere before deleting it.", code="department_in_use"
            )
        if await self._teams.exists(company_id, {"department_id": department.id}):
            raise ConflictError(
                "Move or delete this department's teams before deleting it.", code="department_in_use"
            )
        await self._departments.delete_by_id(company_id, department.id)
        await self._record(
            principal, "department.deleted", "department", department.id, meta, {"name": department.name}
        )

    # ------------------------------------------------------------------ teams
    async def list_teams(self, principal: Principal, department_id: str | None = None) -> list[TeamOut]:
        company_id = principal.company_id
        teams = await self._teams.list_all(company_id, parse_ref(department_id, "department_id"))
        member_counts = await self._employees.counts_by(company_id, "team_id")
        departments = await self._departments.find_by_ids(
            company_id, [t.department_id for t in teams if t.department_id]
        )
        leads = await self._employees.find_by_ids(
            company_id, [t.lead_employee_id for t in teams if t.lead_employee_id]
        )
        return [self._team_out(t, departments, leads, member_counts.get(t.id, 0)) for t in teams]

    async def get_team(self, principal: Principal, team_id: str) -> TeamOut:
        return await self._team_detail(await self._load_team(principal.company_id, team_id))

    async def create_team(self, principal: Principal, data: TeamCreate, meta: RequestMeta) -> TeamOut:
        company_id = principal.company_id
        department_id = await self._validate_department_ref(company_id, data.department_id)
        lead_id = await self._validate_employee_ref(company_id, data.lead_employee_id, "lead_employee_id")
        team = Team(
            company_id=company_id,
            name=data.name,
            department_id=department_id,
            description=data.description or None,
            lead_employee_id=lead_id,
        )
        try:
            await self._teams.create(company_id, team)
        except DuplicateKeyError as exc:
            raise self._name_taken("team") from exc
        await self._record(principal, "team.created", "team", team.id, meta, {"name": team.name})
        return await self._team_detail(team)

    async def update_team(
        self, principal: Principal, team_id: str, data: TeamUpdate, meta: RequestMeta
    ) -> TeamOut:
        company_id = principal.company_id
        team = await self._load_team(company_id, team_id)
        changes = self._clean(
            data.model_dump(exclude_unset=True), required=("name",), optional=("description",)
        )
        if "department_id" in changes:
            changes["department_id"] = await self._validate_department_ref(
                company_id, changes["department_id"]
            )
        if "lead_employee_id" in changes:
            changes["lead_employee_id"] = await self._validate_employee_ref(
                company_id, changes["lead_employee_id"], "lead_employee_id"
            )
        if not changes:
            return await self._team_detail(team)
        try:
            updated = await self._teams.update_by_id(company_id, team.id, changes)
        except DuplicateKeyError as exc:
            raise self._name_taken("team") from exc
        if updated is None:
            raise NotFoundError("Team not found.", code="team_not_found")
        if (
            "department_id" in changes
            and changes["department_id"] != team.department_id
            and changes["department_id"]
        ):
            # Members follow their team into the new department.
            await self._employees.set_department_for_team(company_id, team.id, changes["department_id"])
        await self._record(principal, "team.updated", "team", team.id, meta, {"fields": sorted(changes)})
        return await self._team_detail(updated)

    async def delete_team(self, principal: Principal, team_id: str, meta: RequestMeta) -> None:
        company_id = principal.company_id
        team = await self._load_team(company_id, team_id)
        if await self._employees.exists(company_id, {"team_id": team.id}):
            raise ConflictError("Move this team's members elsewhere before deleting it.", code="team_in_use")
        await self._teams.delete_by_id(company_id, team.id)
        await self._record(principal, "team.deleted", "team", team.id, meta, {"name": team.name})

    # ------------------------------------------------------------------ internals
    async def _load_department(self, company_id: ObjectId, department_id: str) -> Department:
        oid = parse_id(department_id, not_found="Department not found.", code="department_not_found")
        department = await self._departments.get_by_id(company_id, oid)
        if department is None:
            raise NotFoundError("Department not found.", code="department_not_found")
        return department

    async def _load_team(self, company_id: ObjectId, team_id: str) -> Team:
        oid = parse_id(team_id, not_found="Team not found.", code="team_not_found")
        team = await self._teams.get_by_id(company_id, oid)
        if team is None:
            raise NotFoundError("Team not found.", code="team_not_found")
        return team

    async def _validate_employee_ref(
        self, company_id: ObjectId, value: str | None, field: str
    ) -> ObjectId | None:
        oid = parse_ref(value, field)
        if oid is None:
            return None
        employee = await self._employees.get_by_id(company_id, oid)
        if employee is None or employee.status == EmployeeStatus.TERMINATED:
            raise BadRequestError("Employee not found.", code="invalid_employee", details={"field": field})
        return oid

    async def _validate_department_ref(self, company_id: ObjectId, value: str | None) -> ObjectId | None:
        oid = parse_ref(value, "department_id")
        if oid and not await self._departments.get_by_id(company_id, oid):
            raise BadRequestError(
                "Department not found.", code="invalid_department", details={"field": "department_id"}
            )
        return oid

    @staticmethod
    def _clean(
        changes: dict[str, Any], *, required: tuple[str, ...], optional: tuple[str, ...]
    ) -> dict[str, Any]:
        for field in required:
            if field in changes and not changes[field]:
                raise BadRequestError(
                    f"{field} cannot be empty.", code="invalid_field", details={"field": field}
                )
        for field in optional:
            if field in changes and not changes[field]:
                changes[field] = None
        return changes

    @staticmethod
    def _name_taken(kind: str) -> ConflictError:
        return ConflictError(
            f"A {kind} with this name already exists.", code=f"{kind}_name_taken", details={"field": "name"}
        )

    async def _department_detail(self, department: Department) -> DepartmentOut:
        company_id = department.company_id
        heads = await self._employees.find_by_ids(
            company_id, [department.head_employee_id] if department.head_employee_id else []
        )
        employee_count = await self._employees.count(
            company_id, {"department_id": department.id, "status": {"$ne": EmployeeStatus.TERMINATED.value}}
        )
        team_count = await self._teams.count(company_id, {"department_id": department.id})
        return self._department_out(department, heads, employee_count, team_count)

    @staticmethod
    def _department_out(
        department: Department, heads: dict[ObjectId, Employee], employee_count: int, team_count: int
    ) -> DepartmentOut:
        head = heads.get(department.head_employee_id) if department.head_employee_id else None
        return DepartmentOut(
            id=str(department.id),
            name=department.name,
            description=department.description,
            head=employee_ref(head) if head else None,
            employee_count=employee_count,
            team_count=team_count,
            created_at=department.created_at,
        )

    async def _team_detail(self, team: Team) -> TeamOut:
        company_id = team.company_id
        departments = await self._departments.find_by_ids(
            company_id, [team.department_id] if team.department_id else []
        )
        leads = await self._employees.find_by_ids(
            company_id, [team.lead_employee_id] if team.lead_employee_id else []
        )
        members = await self._employees.count(
            company_id, {"team_id": team.id, "status": {"$ne": EmployeeStatus.TERMINATED.value}}
        )
        return self._team_out(team, departments, leads, members)

    @staticmethod
    def _team_out(
        team: Team,
        departments: dict[ObjectId, Department],
        leads: dict[ObjectId, Employee],
        member_count: int,
    ) -> TeamOut:
        department = departments.get(team.department_id) if team.department_id else None
        lead = leads.get(team.lead_employee_id) if team.lead_employee_id else None
        return TeamOut(
            id=str(team.id),
            name=team.name,
            description=team.description,
            department=Ref(id=str(department.id), name=department.name) if department else None,
            lead=employee_ref(lead) if lead else None,
            member_count=member_count,
            created_at=team.created_at,
        )

    async def _record(
        self,
        principal: Principal,
        action: str,
        target_type: str,
        target_id: ObjectId,
        meta: RequestMeta,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        await self._audit.record(
            action,
            company_id=principal.company_id,
            actor_user_id=principal.user_id,
            target_type=target_type,
            target_id=str(target_id),
            meta=meta,
            metadata=metadata,
        )
