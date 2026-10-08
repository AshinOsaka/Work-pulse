"""User account administration: listing members and assigning roles."""

from __future__ import annotations

from app.auth.permissions import Role, can_assign_role
from app.auth.principal import Principal
from app.core.exceptions import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from app.models.user import UserStatus
from app.repositories.user import UserRepository
from app.schemas.common import Page
from app.schemas.user import UserAdminOut
from app.services.audit_service import AuditService
from app.services.context import RequestMeta
from app.services.helpers import parse_id


class UserAdminService:
    def __init__(self, *, users: UserRepository, audit: AuditService) -> None:
        self._users = users
        self._audit = audit

    async def list_users(
        self, principal: Principal, *, search: str | None, role: Role | None, page: int, page_size: int
    ) -> Page[UserAdminOut]:
        items, total = await self._users.search(
            principal.company_id,
            search=search or None,
            role=role.value if role else None,
            skip=(page - 1) * page_size,
            limit=page_size,
        )
        return Page[UserAdminOut].build([UserAdminOut.from_user(u) for u in items], total, page, page_size)

    async def change_role(
        self, principal: Principal, user_id: str, role: Role, meta: RequestMeta
    ) -> UserAdminOut:
        company_id = principal.company_id
        oid = parse_id(user_id, not_found="User not found.", code="user_not_found")
        target = await self._users.get_by_id(company_id, oid)
        if target is None:
            raise NotFoundError("User not found.", code="user_not_found")
        if target.id == principal.user_id:
            raise BadRequestError("You cannot change your own role.", code="cannot_change_own_role")
        if not can_assign_role(principal.role, target.role) or not can_assign_role(principal.role, role):
            raise ForbiddenError(
                "You cannot assign this role.", code="role_not_assignable", details={"field": "role"}
            )
        if target.role == role:
            return UserAdminOut.from_user(target)
        if (
            target.role == Role.COMPANY_ADMIN
            and target.status == UserStatus.ACTIVE
            and await self._users.count_active_with_role(company_id, Role.COMPANY_ADMIN.value) <= 1
        ):
            raise ConflictError("A workspace must keep at least one active Company Admin.", code="last_admin")

        updated = await self._users.update_by_id(company_id, target.id, {"role": role})
        if updated is None:
            raise NotFoundError("User not found.", code="user_not_found")
        # Roles are re-read on every request, so the change applies immediately.
        await self._audit.record(
            "user.role_changed",
            company_id=company_id,
            actor_user_id=principal.user_id,
            target_type="user",
            subject_employee_id=target.employee_id,
            target_id=str(target.id),
            meta=meta,
            metadata={"from": target.role.value, "to": role.value},
        )
        return UserAdminOut.from_user(updated)
