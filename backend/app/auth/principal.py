from __future__ import annotations

from dataclasses import dataclass

from bson import ObjectId

from app.auth.permissions import Permission, Role
from app.models.user import User


@dataclass(frozen=True, slots=True)
class Principal:
    """The authenticated actor for the current request or connection."""

    user: User
    permissions: frozenset[Permission]
    #: The sign-in session behind the access token (None for internal callers such as signed-URL downloads).
    session_id: ObjectId | None = None

    @property
    def user_id(self) -> ObjectId:
        return self.user.id

    @property
    def company_id(self) -> ObjectId:
        return self.user.company_id

    @property
    def role(self) -> Role:
        return self.user.role

    def has(self, *permissions: Permission) -> bool:
        return all(p in self.permissions for p in permissions)
