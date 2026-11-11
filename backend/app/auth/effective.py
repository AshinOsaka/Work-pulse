"""A person's effective permissions: their custom role's chosen permissions, or their built-in role's.

Built-in roles (Employee, Team Lead, Manager, Company Admin, Super Admin) have fixed permissions from the
catalogue. A company's custom role (e.g. "HR Manager") stores the permissions an administrator ticked for it;
its base level still decides whose data the person can see (their reporting line, or everyone for admins)
and which roles they may assign. Every check that turns a user into permissions goes through here.
"""

from __future__ import annotations

from typing import Any

from bson import ObjectId
from pymongo.asynchronous.database import AsyncDatabase

from app.auth.permissions import Permission, Role, permissions_for_role
from app.models.role import RoleDocument
from app.models.user import User
from app.repositories.role import RoleRepository

BUILT_IN_KEYS = frozenset(r.value for r in Role)
_VALID = frozenset(p.value for p in Permission)


def is_custom_role(user: User) -> bool:
    return bool(user.role_key) and user.role_key not in BUILT_IN_KEYS


def role_permissions(doc: RoleDocument) -> frozenset[Permission]:
    """The permissions stored on a custom role (unknown names are ignored)."""
    return frozenset(Permission(p) for p in doc.permissions if p in _VALID)


def _resolve(user: User, doc: RoleDocument | None) -> frozenset[Permission]:
    if user.role == Role.SUPER_ADMIN or doc is None:
        return permissions_for_role(user.role)
    return role_permissions(doc)


async def permissions_for_user(db: AsyncDatabase[dict[str, Any]], user: User) -> frozenset[Permission]:
    """One user's permissions (one extra read, only for people with a custom role)."""
    if not is_custom_role(user):
        return permissions_for_role(user.role)
    doc = await RoleRepository(db).get_company_role(user.company_id, str(user.role_key))
    return _resolve(user, doc)


async def custom_roles(db: AsyncDatabase[dict[str, Any]], company_id: ObjectId) -> dict[str, RoleDocument]:
    """The company's custom roles by key, for resolving many users at once."""
    return {r.key: r for r in await RoleRepository(db).list_for_company(company_id) if not r.is_system}


def permissions_with(user: User, roles: dict[str, RoleDocument]) -> frozenset[Permission]:
    """A user's permissions given their company's custom roles (see ``custom_roles``)."""
    if not is_custom_role(user):
        return permissions_for_role(user.role)
    return _resolve(user, roles.get(str(user.role_key)))
