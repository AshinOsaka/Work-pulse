from __future__ import annotations

from pydantic import Field

from app.models.base import MongoModel, PyObjectId


class RoleDocument(MongoModel):
    """A role definition. `company_id=None` marks a platform-wide system role.

    Custom company roles carry a ``base_level`` — one of the built-in access levels (the ``Role`` enum
    values) — which decides what the role can access. The built-in roles use their own key as base level.
    """

    company_id: PyObjectId | None = None
    key: str
    name: str
    description: str = ""
    level: int = 0
    #: The built-in access level this role grants (a Role enum value). Built-ins: base_level == key.
    base_level: str = "EMPLOYEE"
    permissions: list[str] = Field(default_factory=list)
    is_system: bool = False


class PermissionDocument(MongoModel):
    key: str
    name: str
    description: str = ""
    category: str = "General"
