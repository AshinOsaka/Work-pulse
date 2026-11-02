from __future__ import annotations

from pydantic import Field

from app.auth.permissions import Role
from app.schemas.common import APIModel

# Base access levels a custom role may be built on (Super Admin is reserved for platform staff).
AssignableLevel = Role


class PermissionOut(APIModel):
    key: str
    name: str
    description: str
    category: str


class RoleOut(APIModel):
    key: str
    name: str
    description: str
    level: int
    #: The built-in access level this role grants. For built-in roles this equals ``key``.
    base_level: str
    is_system: bool
    permissions: list[str]


class RolesResponse(APIModel):
    roles: list[RoleOut]
    permissions: list[PermissionOut]


class RoleCreate(APIModel):
    name: str = Field(min_length=2, max_length=60)
    #: One of the built-in access levels the custom role is based on (not Super Admin).
    base_level: Role


class RoleUpdate(APIModel):
    name: str | None = Field(default=None, min_length=2, max_length=60)
    base_level: Role | None = None
