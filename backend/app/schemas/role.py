from __future__ import annotations

from app.schemas.common import APIModel


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
    is_system: bool
    permissions: list[str]


class RolesResponse(APIModel):
    roles: list[RoleOut]
    permissions: list[PermissionOut]
