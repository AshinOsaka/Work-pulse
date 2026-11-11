"""Custom company roles: a name, a built-in base level, and the permissions an administrator chose.

Built-in roles (the ``Role`` enum) are seeded as system roles and cannot be changed or removed. A company
may add its own roles (e.g. "BDM", "HR Manager"). The base level decides whose data the person sees (their
reporting line, or everyone for an admin level) and which roles they may assign; the chosen permissions decide
what they can do (see ``app.auth.effective``). Nobody can grant a permission they don't hold themselves.
"""

from __future__ import annotations

import re

from bson import ObjectId

from app.auth.effective import BUILT_IN_KEYS, EDITABLE_BUILT_IN
from app.auth.permissions import Permission, Role, can_assign_role, permissions_for_role, role_level
from app.auth.principal import Principal
from app.core.exceptions import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from app.models.role import RoleDocument
from app.repositories.role import RoleRepository
from app.repositories.user import UserRepository
from app.schemas.role import RoleCreate, RoleUpdate
from app.services.audit_service import AuditService
from app.services.context import RequestMeta


def _slug(name: str) -> str:
    base = re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_").upper()
    return base or "ROLE"


class RoleService:
    def __init__(self, *, roles: RoleRepository, users: UserRepository, audit: AuditService) -> None:
        self._roles = roles
        self._users = users
        self._audit = audit

    async def list_roles(self, company_id: ObjectId) -> list[RoleDocument]:
        return await self._roles.list_for_company(company_id)

    async def resolve(self, company_id: ObjectId, key: str) -> RoleDocument:
        role = await self._roles.get_effective(company_id, key)
        if role is None:
            raise BadRequestError(f"Unknown role {key!r}.", code="invalid_role", details={"field": "role"})
        return role

    @staticmethod
    def _ensure_assignable_level(principal: Principal, base_level: Role) -> None:
        if base_level == Role.SUPER_ADMIN:
            raise BadRequestError(
                "Super Admin is reserved and cannot be used as a base level.", code="invalid_base_level"
            )
        if not can_assign_role(principal.role, base_level):
            raise ForbiddenError(
                "You cannot create a role with an access level above your own.",
                code="role_not_assignable",
                details={"field": "base_level"},
            )

    @staticmethod
    def _grantable(principal: Principal, permissions: list[Permission]) -> list[str]:
        """The chosen permissions, sorted; refuses any the administrator doesn't hold themselves."""
        missing = sorted(p.value for p in set(permissions) if p not in principal.permissions)
        if missing:
            raise ForbiddenError(
                "You can't give a role a permission you don't have yourself.",
                code="permission_not_grantable",
                details={"field": "permissions", "permissions": missing},
            )
        return sorted({p.value for p in permissions})

    async def _unique_key(self, company_id: ObjectId, name: str) -> str:
        base = _slug(name)
        key = base
        suffix = 2
        while await self._roles.key_taken(company_id, key):
            key = f"{base}_{suffix}"
            suffix += 1
        return key

    async def create(self, principal: Principal, data: RoleCreate, meta: RequestMeta) -> RoleDocument:
        if Permission.USER_MANAGE not in principal.permissions:
            raise ForbiddenError("You cannot manage roles.", code="insufficient_permissions")
        self._ensure_assignable_level(principal, data.base_level)
        company_id = principal.company_id
        key = await self._unique_key(company_id, data.name)
        chosen = (
            self._grantable(principal, data.permissions)
            if data.permissions is not None
            else sorted(p.value for p in permissions_for_role(data.base_level))
        )
        role = RoleDocument(
            company_id=company_id,
            key=key,
            name=data.name.strip(),
            description="",
            level=role_level(data.base_level),
            base_level=data.base_level.value,
            permissions=chosen,
            is_system=False,
        )
        created = await self._roles.create(role)
        await self._audit.record(
            "role.created",
            company_id=company_id,
            actor_user_id=principal.user_id,
            target_type="role",
            target_id=key,
            meta=meta,
            metadata={"name": created.name, "base_level": created.base_level, "permissions": created.permissions},
        )
        return created

    async def update(
        self, principal: Principal, key: str, data: RoleUpdate, meta: RequestMeta
    ) -> RoleDocument:
        if Permission.USER_MANAGE not in principal.permissions:
            raise ForbiddenError("You cannot manage roles.", code="insufficient_permissions")
        company_id = principal.company_id
        if key in BUILT_IN_KEYS:
            return await self._update_built_in(principal, key, data, meta)
        existing = await self._roles.get_company_role(company_id, key)
        if existing is None:
            raise NotFoundError("Role not found.", code="role_not_found")

        changes: dict[str, object] = {}
        if data.name is not None and data.name.strip() != existing.name:
            changes["name"] = data.name.strip()
        if data.base_level is not None and data.base_level.value != existing.base_level:
            self._ensure_assignable_level(principal, data.base_level)
            changes["base_level"] = data.base_level.value
            changes["level"] = role_level(data.base_level)
            changes["permissions"] = sorted(p.value for p in permissions_for_role(data.base_level))
        if data.permissions is not None:
            chosen = self._grantable(principal, data.permissions)
            if chosen != sorted(existing.permissions) or "permissions" in changes:
                changes["permissions"] = chosen
        if not changes:
            return existing

        updated = await self._roles.update_company_role(company_id, key, changes)
        if updated is None:
            raise NotFoundError("Role not found.", code="role_not_found")
        # Members of this role inherit the new access level on their next request.
        if "base_level" in changes:
            await self._users.set_access_level_for_role(company_id, key, Role(updated.base_level))
        await self._audit.record(
            "role.updated",
            company_id=company_id,
            actor_user_id=principal.user_id,
            target_type="role",
            target_id=key,
            meta=meta,
            metadata={"fields": sorted(changes), **({"permissions": changes["permissions"]} if "permissions" in changes else {})},
        )
        return updated

    async def _update_built_in(
        self, principal: Principal, key: str, data: RoleUpdate, meta: RequestMeta
    ) -> RoleDocument:
        """Re-tick a built-in role for this company only (Employee, Team Lead, Manager); its name and level stay."""
        if key not in EDITABLE_BUILT_IN:
            raise ConflictError(
                "Company Admin always has every permission and can't be changed.", code="role_is_system"
            )
        level = Role(key)
        if data.name is not None or (data.base_level is not None and data.base_level != level):
            raise BadRequestError(
                "A built-in role's name and level can't be changed; only its permissions.", code="role_is_system"
            )
        if not can_assign_role(principal.role, level):
            raise ForbiddenError("You cannot change this role.", code="role_not_assignable")
        company_id = principal.company_id
        current = await self._roles.get_effective(company_id, key)
        if current is None:
            raise NotFoundError("Role not found.", code="role_not_found")
        if data.permissions is None:
            return current
        chosen = self._grantable(principal, data.permissions)
        default = sorted(p.value for p in permissions_for_role(level))
        own = await self._roles.get_company_role(company_id, key)
        if chosen == default:
            # Back to the standard permissions: drop the company's own version.
            if own is not None:
                await self._roles.delete_company_role(company_id, key)
        elif own is not None:
            await self._roles.update_company_role(company_id, key, {"permissions": chosen})
        else:
            await self._roles.create(
                RoleDocument(
                    company_id=company_id,
                    key=key,
                    name=current.name,
                    description=current.description,
                    level=current.level,
                    base_level=key,
                    permissions=chosen,
                    is_system=True,
                )
            )
        await self._audit.record(
            "role.updated",
            company_id=company_id,
            actor_user_id=principal.user_id,
            target_type="role",
            target_id=key,
            meta=meta,
            metadata={"fields": ["permissions"], "permissions": chosen, "reset": chosen == default},
        )
        updated = await self._roles.get_effective(company_id, key)
        assert updated is not None
        return updated

    async def delete(self, principal: Principal, key: str, meta: RequestMeta) -> None:
        if Permission.USER_MANAGE not in principal.permissions:
            raise ForbiddenError("You cannot manage roles.", code="insufficient_permissions")
        company_id = principal.company_id
        if key in BUILT_IN_KEYS:
            raise ConflictError("Built-in roles can't be deleted.", code="role_is_system")
        existing = await self._roles.get_company_role(company_id, key)
        if existing is None:
            raise NotFoundError("Role not found.", code="role_not_found")
        if await self._users.count_with_role_key(company_id, key) > 0:
            raise ConflictError(
                "This role still has members. Move them to another role first.", code="role_in_use"
            )
        await self._roles.delete_company_role(company_id, key)
        await self._audit.record(
            "role.deleted",
            company_id=company_id,
            actor_user_id=principal.user_id,
            target_type="role",
            target_id=key,
            meta=meta,
            metadata={"name": existing.name},
        )
