from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from app.auth.permissions import Role
from app.models.user import DashboardWidget, User, UserStatus
from app.schemas.common import APIModel


class DashboardWidgetIO(APIModel):
    #: A widget key from the dashboard's catalogue; keys the UI doesn't know are ignored when shown.
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,39}$")
    #: The dashboard keeps its fixed arrangement: a top row, a wide main column and a narrow side column.
    area: Literal["top", "main", "side"] = "main"
    title: str | None = Field(default=None, max_length=60)

    @field_validator("title")
    @classmethod
    def _clean_title(cls, value: str | None) -> str | None:
        value = (value or "").strip()
        return value or None

    @classmethod
    def from_model(cls, widget: DashboardWidget) -> DashboardWidgetIO:
        area = widget.area if widget.area in ("top", "main", "side") else "main"
        return cls(id=widget.id, area=area, title=widget.title)


class DashboardLayoutRequest(APIModel):
    widgets: list[DashboardWidgetIO] = Field(max_length=30)

    @field_validator("widgets")
    @classmethod
    def _unique(cls, widgets: list[DashboardWidgetIO]) -> list[DashboardWidgetIO]:
        ids = [w.id for w in widgets]
        if len(ids) != len(set(ids)):
            raise ValueError("Each widget can appear only once.")
        return widgets


class UserOut(APIModel):
    id: str
    company_id: str
    email: str
    full_name: str
    role: Role
    #: The assigned role's key (built-in Role value or a custom company role). Resolve the display name
    #: from the roles list. Defaults to the built-in role's value.
    role_key: str
    status: UserStatus
    email_verified: bool
    last_login_at: datetime | None
    created_at: datetime
    employee_id: str | None = None
    mfa_enabled: bool = False
    #: True once the person has acknowledged that this company device is monitored.
    monitoring_acknowledged: bool = False
    #: Dashboard sections an admin has hidden from this person; the UI omits them from their own view.
    hidden_sections: list[str] = Field(default_factory=list)
    #: The person's own dashboard arrangement; None means the standard layout.
    dashboard_layout: list[DashboardWidgetIO] | None = None

    @classmethod
    def from_model(cls, user: User) -> UserOut:
        return cls(
            id=str(user.id),
            company_id=str(user.company_id),
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            role_key=user.role_key or user.role.value,
            status=user.status,
            email_verified=user.email_verified,
            last_login_at=user.last_login_at,
            created_at=user.created_at,
            employee_id=str(user.employee_id) if user.employee_id else None,
            mfa_enabled=user.mfa_enabled,
            monitoring_acknowledged=user.monitoring_acknowledged_at is not None,
            hidden_sections=list(user.hidden_sections),
            dashboard_layout=(
                [DashboardWidgetIO.from_model(w) for w in user.dashboard_layout]
                if user.dashboard_layout is not None
                else None
            ),
        )


class UpdateProfileRequest(APIModel):
    full_name: str = Field(min_length=2, max_length=120)


class UserAdminOut(UserOut):
    """Admin view of a member (same fields; kept separate so it can diverge)."""

    @classmethod
    def from_user(cls, user: User) -> UserAdminOut:
        return cls(**UserOut.from_model(user).model_dump())


class RoleUpdateRequest(APIModel):
    #: A role key — a built-in Role value or a custom company role.
    role: str
