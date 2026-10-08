"""Organisational structure: departments, teams, employees and their devices."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from app.models.base import PyObjectId, TenantModel


class RecordStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class Department(TenantModel):
    name: str
    description: str | None = None
    head_employee_id: PyObjectId | None = None
    status: RecordStatus = RecordStatus.ACTIVE


class Team(TenantModel):
    name: str
    department_id: PyObjectId | None = None
    description: str | None = None
    lead_employee_id: PyObjectId | None = None
    status: RecordStatus = RecordStatus.ACTIVE


class EmployeeStatus(StrEnum):
    ACTIVE = "active"
    ON_LEAVE = "on_leave"
    TERMINATED = "terminated"


class EmploymentType(StrEnum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACTOR = "contractor"


class ScreenshotMode(StrEnum):
    INHERIT = "inherit"
    ENABLED = "enabled"
    DISABLED = "disabled"


class ScreenshotOverride(BaseModel):
    """Per-employee exception to the workspace screenshot policy."""

    mode: ScreenshotMode = ScreenshotMode.INHERIT
    interval_minutes: int | None = None


class Employee(TenantModel):
    full_name: str
    email: str
    user_id: PyObjectId | None = None
    employee_code: str | None = None
    job_title: str | None = None
    department_id: PyObjectId | None = None
    team_id: PyObjectId | None = None
    #: Work profile (job role) whose productivity rules apply; see `models.productivity.WorkProfile`.
    work_profile_id: PyObjectId | None = None
    manager_employee_id: PyObjectId | None = None
    employment_type: EmploymentType = EmploymentType.FULL_TIME
    status: EmployeeStatus = EmployeeStatus.ACTIVE
    timezone: str = "UTC"
    location: str | None = None
    # Stored as a datetime (BSON has no date type); exposed as a date by the API.
    hired_on: datetime | None = None
    terminated_at: datetime | None = None
    screenshot_override: ScreenshotOverride = Field(default_factory=ScreenshotOverride)


class DeviceStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    INACTIVE = "inactive"
    REVOKED = "revoked"


class DeviceOs(StrEnum):
    WINDOWS = "windows"
    MACOS = "macos"
    LINUX = "linux"


class PresenceState(StrEnum):
    ACTIVE = "active"
    IDLE = "idle"


class Device(TenantModel):
    """A machine running the WorkPulse desktop agent.

    A device becomes `active` when the agent registers (employee sign-in) or
    redeems an admin-issued enrolment code. The agent then authenticates with a
    per-device secret, stored here only as a SHA-256 digest.
    """

    employee_id: PyObjectId
    name: str
    hostname: str | None = None
    os: DeviceOs = DeviceOs.WINDOWS
    os_version: str | None = None
    agent_version: str | None = None
    status: DeviceStatus = DeviceStatus.PENDING
    enrollment_code_hash: str | None = None
    enrollment_expires_at: datetime | None = None
    registered_by_user_id: PyObjectId | None = None
    enrolled_at: datetime | None = None
    last_seen_at: datetime | None = None
    revoked_at: datetime | None = None
    # Agent credentials & identity (Phase 4)
    secret_hash: str | None = None
    fingerprint_hash: str | None = None
    # Live presence, maintained by heartbeats and agent events
    presence: PresenceState | None = None
    presence_since: datetime | None = None
    current_session_id: str | None = None
    last_ip: str | None = None
    # Set when the agent reports a clean shutdown; cleared by the next heartbeat.
    agent_stopped_at: datetime | None = None
    # Foreground application name (only when application tracking is enabled).
    current_app: str | None = None
    current_app_since: datetime | None = None
