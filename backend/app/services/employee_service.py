"""Employee use-cases: directory, profiles, reporting lines, status and invitations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.auth.permissions import Permission, Role, can_assign_role, permissions_for_role
from app.auth.principal import Principal
from app.core.config import Settings
from app.core.exceptions import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from app.core.security import UNUSABLE_PASSWORD, generate_opaque_token, hash_token
from app.models.auth_tokens import InvitationToken
from app.models.organization import Department, Employee, EmployeeStatus, Team
from app.models.user import User, UserStatus
from app.repositories.auth_tokens import InvitationTokenRepository, RefreshTokenRepository
from app.repositories.company import CompanyRepository
from app.repositories.organization import (
    DepartmentRepository,
    DeviceRepository,
    EmployeeQuery,
    EmployeeRepository,
    TeamRepository,
)
from app.repositories.user import UserRepository
from app.schemas.common import Page
from app.schemas.organization import (
    AccessState,
    AccountOut,
    CountByRef,
    EmployeeCreate,
    EmployeeDetailOut,
    EmployeeListParams,
    EmployeeOut,
    EmployeeRef,
    EmployeeUpdate,
    PeopleSummary,
    Ref,
)
from app.services.access_scope import AccessScopeService, EmployeeScope
from app.services.audit_service import AuditService
from app.services.context import RequestMeta
from app.services.email_service import EmailDeliveryError, EmailService
from app.services.helpers import (
    date_to_datetime,
    datetime_to_date,
    duplicate_key_fields,
    parse_id,
    parse_ref,
)
from app.utils.text import normalise_email
from app.utils.time import utcnow

_ACCESS_BY_USER_STATUS: dict[UserStatus, AccessState] = {
    UserStatus.ACTIVE: "active",
    UserStatus.INVITED: "invited",
    UserStatus.SUSPENDED: "suspended",
    UserStatus.DEACTIVATED: "deactivated",
}
_REQUIRED_FIELDS = ("full_name", "email", "employment_type", "timezone")


def employee_ref(employee: Employee) -> EmployeeRef:
    return EmployeeRef(
        id=str(employee.id),
        full_name=employee.full_name,
        email=employee.email,
        job_title=employee.job_title,
        status=employee.status,
    )


@dataclass(frozen=True, slots=True)
class _Relations:
    department_id: ObjectId | None
    team_id: ObjectId | None
    manager_employee_id: ObjectId | None


class EmployeeService:
    def __init__(
        self,
        *,
        settings: Settings,
        employees: EmployeeRepository,
        departments: DepartmentRepository,
        teams: TeamRepository,
        users: UserRepository,
        companies: CompanyRepository,
        devices: DeviceRepository,
        invitations: InvitationTokenRepository,
        refresh_tokens: RefreshTokenRepository,
        scopes: AccessScopeService,
        email: EmailService,
        audit: AuditService,
    ) -> None:
        self._settings = settings
        self._employees = employees
        self._departments = departments
        self._teams = teams
        self._users = users
        self._companies = companies
        self._devices = devices
        self._invitations = invitations
        self._refresh_tokens = refresh_tokens
        self._scopes = scopes
        self._email = email
        self._audit = audit

    # ------------------------------------------------------------------ queries
    async def list_employees(self, principal: Principal, params: EmployeeListParams) -> Page[EmployeeOut]:
        scope = await self._scopes.employee_scope(principal)
        query = EmployeeQuery(
            search=params.search or None,
            statuses=params.status,
            department_id=parse_ref(params.department_id, "department_id"),
            team_id=parse_ref(params.team_id, "team_id"),
            manager_id=parse_ref(params.manager_id, "manager_id"),
            sort=params.sort,
            descending=params.order == "desc",
            skip=(params.page - 1) * params.page_size,
            limit=params.page_size,
            extra=scope.filter or {},
        )
        items, total = await self._employees.search(principal.company_id, query)
        return Page[EmployeeOut].build(
            await self._present_many(principal.company_id, items), total, params.page, params.page_size
        )

    async def get(self, principal: Principal, employee_id: str) -> EmployeeDetailOut:
        scope = await self._scopes.employee_scope(principal)
        employee = await self._get_visible(principal, employee_id, scope)
        return await self._present_detail(employee, scope)

    async def options(self, principal: Principal, search: str | None) -> list[EmployeeRef]:
        """Lightweight list for pickers (manager, team lead, department head)."""
        scope = await self._scopes.employee_scope(principal)
        items, _ = await self._employees.search(
            principal.company_id,
            EmployeeQuery(
                search=search or None,
                statuses=(EmployeeStatus.ACTIVE, EmployeeStatus.ON_LEAVE),
                limit=200,
                extra=scope.filter or {},
            ),
        )
        return [employee_ref(e) for e in items]

    async def managers(self, principal: Principal) -> list[EmployeeRef]:
        """Employees who manage at least one employee visible to the caller."""
        scope = await self._scopes.employee_scope(principal)
        ids = await self._employees.distinct_manager_ids(principal.company_id, scope.filter)
        found = await self._employees.find_by_ids(principal.company_id, ids)
        return sorted((employee_ref(e) for e in found.values()), key=lambda r: r.full_name.lower())

    async def summary(self, principal: Principal) -> PeopleSummary:
        company_id = principal.company_id
        scope = await self._scopes.employee_scope(principal)
        by_status = await self._employees.status_counts(company_id, scope.filter)
        by_department = await self._employees.counts_by(company_id, "department_id", scope.filter)
        departments = await self._departments.find_by_ids(company_id, [k for k in by_department if k])
        user_ids = await self._employees.distinct_user_ids(company_id, scope.filter)
        pending = (
            await self._users.count(
                company_id, {"_id": {"$in": user_ids}, "status": UserStatus.INVITED.value}
            )
            if user_ids
            else 0
        )
        breakdown = [
            CountByRef(
                id=str(key) if key else None,
                name=departments[key].name if key in departments else "Unassigned",
                count=count,
            )
            for key, count in by_department.items()
            if key is None or key in departments
        ]
        breakdown.sort(key=lambda row: (-row.count, row.name.lower()))
        recent = await self._employees.recent(company_id, scope.filter)
        return PeopleSummary(
            total=sum(by_status.values()),
            by_status={s.value: by_status.get(s.value, 0) for s in EmployeeStatus},
            pending_invitations=pending,
            departments=breakdown,
            recent=[employee_ref(e) for e in recent],
        )

    # ------------------------------------------------------------------ commands
    async def create(
        self, principal: Principal, data: EmployeeCreate, meta: RequestMeta
    ) -> EmployeeDetailOut:
        company_id = principal.company_id
        if data.invite:
            self._ensure_can_invite(principal, data.role)
        email = normalise_email(data.email)
        if data.invite and await self._users.email_exists(email):
            raise ConflictError(
                "A user account with this email already exists.",
                code="email_taken",
                details={"field": "email"},
            )

        relations = await self._validate_relations(
            company_id,
            employee_id=None,
            department_id=parse_ref(data.department_id, "department_id"),
            team_id=parse_ref(data.team_id, "team_id"),
            manager_id=parse_ref(data.manager_employee_id, "manager_employee_id"),
        )
        employee = Employee(
            company_id=company_id,
            full_name=data.full_name,
            email=email,
            employee_code=data.employee_code or None,
            job_title=data.job_title or None,
            department_id=relations.department_id,
            team_id=relations.team_id,
            manager_employee_id=relations.manager_employee_id,
            employment_type=data.employment_type,
            timezone=data.timezone or await self._company_timezone(company_id),
            location=data.location or None,
            hired_on=date_to_datetime(data.hired_on),
        )
        try:
            await self._employees.create(company_id, employee)
        except DuplicateKeyError as exc:
            raise self._duplicate_error(exc) from exc

        invitation_error: EmailDeliveryError | None = None
        if data.invite:
            try:
                employee = await self._create_invited_user(principal, employee, data.role)
            except EmailDeliveryError as exc:
                invitation_error = exc  # employee and account exist; reported after the audit record below
            except Exception:
                await self._employees.delete_by_id(company_id, employee.id)
                raise

        await self._audit.record(
            "employee.created",
            company_id=company_id,
            actor_user_id=principal.user_id,
            target_type="employee",
            target_id=str(employee.id),
            subject_employee_id=employee.id,
            meta=meta,
            metadata={"invited": data.invite},
        )
        if invitation_error is not None:
            raise invitation_error
        return await self._present_detail(employee, EmployeeScope(company_id, unrestricted=True))

    async def update(
        self, principal: Principal, employee_id: str, data: EmployeeUpdate, meta: RequestMeta
    ) -> EmployeeDetailOut:
        scope = await self._scopes.employee_scope(principal)
        employee = await self._get_visible(principal, employee_id, scope)
        changes: dict[str, Any] = data.model_dump(exclude_unset=True)

        for field in _REQUIRED_FIELDS:
            if field in changes and changes[field] is None:
                raise BadRequestError(
                    f"{field} cannot be empty.", code="invalid_field", details={"field": field}
                )

        if "email" in changes:
            new_email = normalise_email(changes["email"])
            if new_email != employee.email and employee.user_id:
                raise ConflictError(
                    "This employee has a user account; their sign-in email cannot be changed here.",
                    code="email_locked",
                    details={"field": "email"},
                )
            changes["email"] = new_email

        relation_keys = {"department_id", "team_id", "manager_employee_id"}
        if relation_keys & changes.keys():
            relations = await self._validate_relations(
                principal.company_id,
                employee_id=employee.id,
                department_id=parse_ref(changes["department_id"], "department_id")
                if "department_id" in changes
                else employee.department_id,
                team_id=parse_ref(changes["team_id"], "team_id")
                if "team_id" in changes
                else employee.team_id,
                manager_id=parse_ref(changes["manager_employee_id"], "manager_employee_id")
                if "manager_employee_id" in changes
                else employee.manager_employee_id,
            )
            changes.update(
                department_id=relations.department_id,
                team_id=relations.team_id,
                manager_employee_id=relations.manager_employee_id,
            )

        if "hired_on" in changes:
            changes["hired_on"] = date_to_datetime(changes["hired_on"])
        for optional in ("employee_code", "job_title", "location"):
            if optional in changes and not changes[optional]:
                changes[optional] = None

        if not changes:
            return await self._present_detail(employee, scope)

        try:
            updated = await self._employees.update_by_id(principal.company_id, employee.id, changes)
        except DuplicateKeyError as exc:
            raise self._duplicate_error(exc) from exc
        if updated is None:
            raise NotFoundError("Employee not found.", code="employee_not_found")

        if "full_name" in changes and updated.user_id:
            await self._users.update_by_id(
                principal.company_id, updated.user_id, {"full_name": updated.full_name}
            )

        await self._audit.record(
            "employee.updated",
            company_id=principal.company_id,
            actor_user_id=principal.user_id,
            target_type="employee",
            target_id=str(employee.id),
            subject_employee_id=employee.id,
            meta=meta,
            metadata={"fields": sorted(changes)},
        )
        return await self._present_detail(updated, scope)

    async def change_status(
        self, principal: Principal, employee_id: str, status: EmployeeStatus, meta: RequestMeta
    ) -> EmployeeDetailOut:
        scope = await self._scopes.employee_scope(principal)
        employee = await self._get_visible(principal, employee_id, scope)
        if employee.id == principal.user.employee_id:
            raise BadRequestError(
                "You cannot change your own employment status.", code="cannot_change_own_status"
            )
        if employee.status == status:
            return await self._present_detail(employee, scope)

        user = (
            await self._users.get_by_id(principal.company_id, employee.user_id) if employee.user_id else None
        )
        changes: dict[str, Any] = {"status": status}

        if status == EmployeeStatus.TERMINATED:
            if user and user.role == Role.COMPANY_ADMIN and user.status == UserStatus.ACTIVE:
                await self._ensure_not_last_admin(principal.company_id)
            changes["terminated_at"] = utcnow()
            if user:
                await self._users.update_by_id(
                    principal.company_id, user.id, {"status": UserStatus.DEACTIVATED}
                )
                await self._refresh_tokens.revoke_all_for_user(
                    principal.company_id, user.id, "employee_terminated"
                )
                await self._invitations.invalidate_for_user(principal.company_id, user.id)
        else:
            changes["terminated_at"] = None
            if user and employee.status == EmployeeStatus.TERMINATED:
                # Restore access: users who never set a password go back to "invited".
                restored = UserStatus.ACTIVE if user.password_changed_at else UserStatus.INVITED
                await self._users.update_by_id(principal.company_id, user.id, {"status": restored})

        updated = await self._employees.update_by_id(principal.company_id, employee.id, changes)
        if updated is None:
            raise NotFoundError("Employee not found.", code="employee_not_found")
        await self._audit.record(
            "employee.status_changed",
            company_id=principal.company_id,
            actor_user_id=principal.user_id,
            target_type="employee",
            target_id=str(employee.id),
            subject_employee_id=employee.id,
            meta=meta,
            metadata={"from": employee.status.value, "to": status.value},
        )
        return await self._present_detail(updated, scope)

    async def invite(
        self, principal: Principal, employee_id: str, role: Role, meta: RequestMeta
    ) -> EmployeeDetailOut:
        """Create an account and send an invitation, or re-send a pending one."""
        self._ensure_can_invite(principal, role)
        scope = await self._scopes.employee_scope(principal)
        employee = await self._get_visible(principal, employee_id, scope)
        if employee.status == EmployeeStatus.TERMINATED:
            raise BadRequestError("Terminated employees cannot be invited.", code="employee_terminated")

        user = (
            await self._users.get_by_id(principal.company_id, employee.user_id) if employee.user_id else None
        )
        if user is None:
            if await self._users.email_exists(employee.email):
                raise ConflictError("A user account with this email already exists.", code="email_taken")
            employee = await self._create_invited_user(principal, employee, role)
        elif user.status == UserStatus.INVITED:
            if user.role != role:
                user = await self._users.update_by_id(principal.company_id, user.id, {"role": role}) or user
            await self._send_invitation(principal, user)
        else:
            raise ConflictError("This employee already has an active account.", code="account_exists")

        await self._audit.record(
            "employee.invited",
            company_id=principal.company_id,
            actor_user_id=principal.user_id,
            target_type="employee",
            target_id=str(employee.id),
            subject_employee_id=employee.id,
            meta=meta,
            metadata={"role": role.value},
        )
        return await self._present_detail(employee, scope)

    # ------------------------------------------------------------------ internals
    async def _company_timezone(self, company_id: ObjectId) -> str:
        company = await self._companies.get_by_id(company_id)
        return company.timezone if company else "UTC"

    async def _get_visible(self, principal: Principal, employee_id: str, scope: EmployeeScope) -> Employee:
        oid = parse_id(employee_id, not_found="Employee not found.", code="employee_not_found")
        employee = await self._employees.get_in_scope(principal.company_id, oid, scope.filter)
        if employee is None:
            # Same response for "other tenant", "out of scope" and "does not exist".
            raise NotFoundError("Employee not found.", code="employee_not_found")
        return employee

    @staticmethod
    def _ensure_can_invite(principal: Principal, role: Role) -> None:
        if Permission.USER_MANAGE not in principal.permissions:
            raise ForbiddenError(
                "You do not have permission to invite users.",
                code="insufficient_permissions",
                details={"missing": [Permission.USER_MANAGE.value]},
            )
        if not can_assign_role(principal.role, role):
            raise ForbiddenError(
                "You cannot grant this role.", code="role_not_assignable", details={"field": "role"}
            )

    async def _ensure_not_last_admin(self, company_id: ObjectId) -> None:
        if await self._users.count_active_with_role(company_id, Role.COMPANY_ADMIN.value) <= 1:
            raise ConflictError("A workspace must keep at least one active Company Admin.", code="last_admin")

    async def _validate_relations(
        self,
        company_id: ObjectId,
        *,
        employee_id: ObjectId | None,
        department_id: ObjectId | None,
        team_id: ObjectId | None,
        manager_id: ObjectId | None,
    ) -> _Relations:
        if department_id and not await self._departments.get_by_id(company_id, department_id):
            raise BadRequestError(
                "Department not found.", code="invalid_department", details={"field": "department_id"}
            )

        if team_id:
            team = await self._teams.get_by_id(company_id, team_id)
            if team is None:
                raise BadRequestError("Team not found.", code="invalid_team", details={"field": "team_id"})
            if team.department_id:
                if department_id is None:
                    department_id = team.department_id
                elif department_id != team.department_id:
                    raise BadRequestError(
                        "The selected team belongs to a different department.",
                        code="team_department_mismatch",
                        details={"field": "team_id"},
                    )

        if manager_id:
            if manager_id == employee_id:
                raise BadRequestError(
                    "An employee cannot manage themselves.",
                    code="invalid_manager",
                    details={"field": "manager_employee_id"},
                )
            manager = await self._employees.get_by_id(company_id, manager_id)
            if manager is None or manager.status == EmployeeStatus.TERMINATED:
                raise BadRequestError(
                    "Manager not found.", code="invalid_manager", details={"field": "manager_employee_id"}
                )
            if employee_id and manager_id in await self._employees.descendant_ids(company_id, employee_id):
                raise BadRequestError(
                    "This would create a circular reporting line.",
                    code="manager_cycle",
                    details={"field": "manager_employee_id"},
                )

        return _Relations(department_id, team_id, manager_id)

    @staticmethod
    def _duplicate_error(exc: DuplicateKeyError) -> ConflictError:
        fields = duplicate_key_fields(exc)
        if "employee_code" in fields:
            return ConflictError(
                "Another employee already uses this employee ID.",
                code="employee_code_taken",
                details={"field": "employee_code"},
            )
        return ConflictError(
            "An employee with this email already exists.",
            code="employee_email_taken",
            details={"field": "email"},
        )

    async def _create_invited_user(self, principal: Principal, employee: Employee, role: Role) -> Employee:
        user = User(
            company_id=employee.company_id,
            email=employee.email,
            full_name=employee.full_name,
            password_hash=UNUSABLE_PASSWORD,
            role=role,
            status=UserStatus.INVITED,
            employee_id=employee.id,
        )
        try:
            await self._users.create(employee.company_id, user)
        except DuplicateKeyError as exc:
            raise ConflictError(
                "A user account with this email already exists.",
                code="email_taken",
                details={"field": "email"},
            ) from exc
        try:
            updated = await self._employees.update_by_id(
                employee.company_id, employee.id, {"user_id": user.id}
            )
            await self._send_invitation(principal, user)
        except EmailDeliveryError as exc:
            # The account is complete; only the e-mail is missing, and "Resend invitation" sends a fresh one.
            raise EmailDeliveryError(
                "The account was created, but the invitation e-mail couldn't be sent. "
                "Use “Resend invitation” on their profile to try again."
            ) from exc
        except Exception:
            # Don't leave an account behind that blocks a retry with "email already taken".
            await self._users.delete_by_id(employee.company_id, user.id)
            await self._employees.update_by_id(employee.company_id, employee.id, {"user_id": None})
            raise
        return updated or employee

    async def _send_invitation(self, principal: Principal, user: User) -> None:
        await self._invitations.invalidate_for_user(user.company_id, user.id)
        raw = generate_opaque_token()
        await self._invitations.create(
            user.company_id,
            InvitationToken(
                company_id=user.company_id,
                user_id=user.id,
                email=user.email,
                token_hash=hash_token(raw),
                invited_by_user_id=principal.user_id,
                expires_at=utcnow() + timedelta(days=self._settings.invitation_token_expire_days),
            ),
        )
        company = await self._companies.get_by_id(user.company_id)
        await self._email.send_invitation(
            to=user.email,
            name=user.full_name,
            company_name=company.name if company else "your company",
            inviter_name=principal.user.full_name,
            token=raw,
        )

    async def _present_many(self, company_id: ObjectId, employees: list[Employee]) -> list[EmployeeOut]:
        departments = await self._departments.find_by_ids(
            company_id, [e.department_id for e in employees if e.department_id]
        )
        teams = await self._teams.find_by_ids(company_id, [e.team_id for e in employees if e.team_id])
        managers = await self._employees.find_by_ids(
            company_id, [e.manager_employee_id for e in employees if e.manager_employee_id]
        )
        users = await self._users.find_by_ids(company_id, [e.user_id for e in employees if e.user_id])
        return [self._to_out(e, departments, teams, managers, users) for e in employees]

    @staticmethod
    def _to_out(
        employee: Employee,
        departments: dict[ObjectId, Department],
        teams: dict[ObjectId, Team],
        managers: dict[ObjectId, Employee],
        users: dict[ObjectId, User],
    ) -> EmployeeOut:
        department = departments.get(employee.department_id) if employee.department_id else None
        team = teams.get(employee.team_id) if employee.team_id else None
        manager = managers.get(employee.manager_employee_id) if employee.manager_employee_id else None
        user = users.get(employee.user_id) if employee.user_id else None
        return EmployeeOut(
            id=str(employee.id),
            full_name=employee.full_name,
            email=employee.email,
            employee_code=employee.employee_code,
            job_title=employee.job_title,
            employment_type=employee.employment_type,
            status=employee.status,
            timezone=employee.timezone,
            location=employee.location,
            hired_on=datetime_to_date(employee.hired_on),
            terminated_at=employee.terminated_at,
            department=Ref(id=str(department.id), name=department.name) if department else None,
            team=Ref(id=str(team.id), name=team.name) if team else None,
            manager=employee_ref(manager) if manager else None,
            account=AccountOut(
                user_id=str(user.id),
                role=user.role,
                status=user.status,
                email_verified=user.email_verified,
                last_login_at=user.last_login_at,
            )
            if user
            else None,
            access=_ACCESS_BY_USER_STATUS[user.status] if user else "none",
            created_at=employee.created_at,
            updated_at=employee.updated_at,
        )

    async def _present_detail(self, employee: Employee, scope: EmployeeScope) -> EmployeeDetailOut:
        company_id = employee.company_id
        [base] = await self._present_many(company_id, [employee])
        reports, _ = await self._employees.search(
            company_id, EmployeeQuery(manager_id=employee.id, limit=200, extra=scope.filter or {})
        )
        device_count = await self._devices.count(
            company_id, {"employee_id": employee.id, "status": {"$ne": "revoked"}}
        )
        permissions = (
            sorted(permissions_for_role(base.account.role))
            if base.account and base.access == "active"
            else []
        )
        return EmployeeDetailOut(
            **base.model_dump(),
            direct_reports=[employee_ref(r) for r in reports],
            device_count=device_count,
            permissions=permissions,
        )
