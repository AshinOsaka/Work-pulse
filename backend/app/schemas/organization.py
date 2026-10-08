"""API schemas for the organisation module: departments, teams, employees, devices."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import EmailStr, Field, field_validator

from app.auth.permissions import Permission, Role
from app.models.organization import DeviceOs, DeviceStatus, EmployeeStatus, EmploymentType
from app.models.user import UserStatus
from app.schemas.common import APIModel, ObjectIdStr, Timezone

# --------------------------------------------------------------------------- references


class Ref(APIModel):
    id: str
    name: str


class EmployeeRef(APIModel):
    id: str
    full_name: str
    email: str
    job_title: str | None = None
    status: EmployeeStatus


# --------------------------------------------------------------------------- departments


class DepartmentCreate(APIModel):
    name: str = Field(min_length=2, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    head_employee_id: ObjectIdStr | None = None


class DepartmentUpdate(APIModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    description: str | None = Field(default=None, max_length=500)
    head_employee_id: ObjectIdStr | None = None


class DepartmentOut(APIModel):
    id: str
    name: str
    description: str | None
    head: EmployeeRef | None
    employee_count: int
    team_count: int
    created_at: datetime


# --------------------------------------------------------------------------- teams


class TeamCreate(APIModel):
    name: str = Field(min_length=2, max_length=80)
    department_id: ObjectIdStr | None = None
    description: str | None = Field(default=None, max_length=500)
    lead_employee_id: ObjectIdStr | None = None


class TeamUpdate(APIModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    department_id: ObjectIdStr | None = None
    description: str | None = Field(default=None, max_length=500)
    lead_employee_id: ObjectIdStr | None = None


class TeamOut(APIModel):
    id: str
    name: str
    description: str | None
    department: Ref | None
    lead: EmployeeRef | None
    member_count: int
    created_at: datetime


# --------------------------------------------------------------------------- employees

AccessState = Literal["none", "invited", "active", "suspended", "deactivated"]
EmployeeSort = Literal["full_name", "job_title", "status", "employee_code", "hired_on", "created_at"]


class AccountOut(APIModel):
    user_id: str
    role: Role
    status: UserStatus
    email_verified: bool
    last_login_at: datetime | None


class EmployeeOut(APIModel):
    id: str
    full_name: str
    email: str
    employee_code: str | None
    job_title: str | None
    employment_type: EmploymentType
    status: EmployeeStatus
    timezone: str
    location: str | None
    hired_on: date | None
    terminated_at: datetime | None
    department: Ref | None
    team: Ref | None
    manager: EmployeeRef | None
    account: AccountOut | None
    access: AccessState
    created_at: datetime
    updated_at: datetime


class EmployeeDetailOut(EmployeeOut):
    direct_reports: list[EmployeeRef]
    device_count: int
    permissions: list[Permission]


class _EmployeeFields(APIModel):
    employee_code: str | None = Field(default=None, max_length=32, pattern=r"^[A-Za-z0-9._\-]+$")
    job_title: str | None = Field(default=None, max_length=120)
    department_id: ObjectIdStr | None = None
    team_id: ObjectIdStr | None = None
    manager_employee_id: ObjectIdStr | None = None
    employment_type: EmploymentType = EmploymentType.FULL_TIME
    timezone: Timezone | None = Field(default=None, description="Defaults to the workspace timezone.")
    location: str | None = Field(default=None, max_length=120)
    hired_on: date | None = None

    @field_validator("hired_on")
    @classmethod
    def _not_far_future(cls, value: date | None) -> date | None:
        if value and value.year > date.today().year + 1:
            raise ValueError("Hire date is too far in the future.")
        return value


class EmployeeCreate(_EmployeeFields):
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    invite: bool = Field(default=False, description="Create a user account and e-mail an invitation.")
    role: Role = Role.EMPLOYEE


class EmployeeUpdate(APIModel):
    """Partial update: only fields present in the request body are changed."""

    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    email: EmailStr | None = None
    employee_code: str | None = Field(default=None, max_length=32, pattern=r"^[A-Za-z0-9._\-]+$")
    job_title: str | None = Field(default=None, max_length=120)
    department_id: ObjectIdStr | None = None
    team_id: ObjectIdStr | None = None
    manager_employee_id: ObjectIdStr | None = None
    employment_type: EmploymentType | None = None
    timezone: Timezone | None = None
    location: str | None = Field(default=None, max_length=120)
    hired_on: date | None = None


class EmployeeStatusUpdate(APIModel):
    status: EmployeeStatus


class InviteRequest(APIModel):
    role: Role = Role.EMPLOYEE


class EmployeeListParams(APIModel):
    search: str | None = Field(default=None, max_length=100)
    status: list[EmployeeStatus] = Field(default_factory=list)
    department_id: ObjectIdStr | None = None
    team_id: ObjectIdStr | None = None
    manager_id: ObjectIdStr | None = None
    sort: EmployeeSort = "full_name"
    order: Literal["asc", "desc"] = "asc"
    page: int = Field(default=1, ge=1, le=10_000)
    page_size: int = Field(default=25, ge=1, le=100)


class CountByRef(APIModel):
    id: str | None
    name: str
    count: int


class PeopleSummary(APIModel):
    total: int
    by_status: dict[str, int]
    pending_invitations: int
    departments: list[CountByRef]
    recent: list[EmployeeRef]


# --------------------------------------------------------------------------- devices


class DeviceCreate(APIModel):
    name: str = Field(min_length=2, max_length=80)
    hostname: str | None = Field(default=None, max_length=255, pattern=r"^[A-Za-z0-9.\-_]+$")
    os: DeviceOs = DeviceOs.WINDOWS
    os_version: str | None = Field(default=None, max_length=60)


class DeviceOut(APIModel):
    id: str
    employee_id: str
    name: str
    hostname: str | None
    os: DeviceOs
    os_version: str | None
    agent_version: str | None
    status: DeviceStatus
    enrollment_expires_at: datetime | None
    enrolled_at: datetime | None
    last_seen_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime


class DeviceRegistered(DeviceOut):
    enrollment_code: str = Field(description="Shown once. Entered in the desktop agent to enrol the device.")
