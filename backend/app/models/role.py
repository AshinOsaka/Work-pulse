from __future__ import annotations

from pydantic import Field

from app.models.base import MongoModel, PyObjectId


class RoleDocument(MongoModel):
    """A role definition. `company_id=None` marks a platform-wide system role."""

    company_id: PyObjectId | None = None
    key: str
    name: str
    description: str = ""
    level: int = 0
    permissions: list[str] = Field(default_factory=list)
    is_system: bool = False


class PermissionDocument(MongoModel):
    key: str
    name: str
    description: str = ""
    category: str = "General"
