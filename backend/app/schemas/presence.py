from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from app.models.organization import DeviceOs
from app.schemas.common import APIModel
from app.schemas.organization import EmployeeRef, Ref

PresenceStatus = Literal["active", "idle", "offline"]


class PresenceDevice(APIModel):
    id: str
    name: str
    os: DeviceOs
    agent_version: str | None
    last_seen_at: datetime | None


class EmployeePresence(APIModel):
    employee: EmployeeRef
    team: Ref | None
    status: PresenceStatus
    #: Agent connected (recent heartbeat), whether or not a work session is running.
    connected: bool
    #: When the current status began.
    since: datetime | None
    session_started_at: datetime | None
    device: PresenceDevice | None
    #: Foreground application while working (when application tracking is enabled).
    current_app: str | None = None


class PresenceCounts(APIModel):
    online: int
    active: int
    idle: int
    offline: int


class PresenceOverview(APIModel):
    employees: list[EmployeePresence]
    counts: PresenceCounts
    as_of: datetime


class WorkHoursSummary(APIModel):
    period: Literal["daily", "weekly", "monthly"]
    timezone: str
    current_hours: float
    previous_hours: float
    #: Hours per bucket, oldest first; the last entry is the current period.
    history: list[float]


class AttendanceDay(APIModel):
    day: date
    #: A weekly day off or a company holiday: no one is expected, so `away` is 0.
    holiday: bool
    #: Distinct employees who had a work session overlapping this local day.
    present: int
    #: Employees expected on a working day (active status) with no session that day.
    away: int


class AttendanceSummary(APIModel):
    start: date
    end: date
    timezone: str
    #: Head-count used as the "expected" baseline on working days (active employees in scope).
    expected: int
    days: list[AttendanceDay]


# --------------------------------------------------------------------------- attendance report
#: Per-day outcome against the required hours.
#: met / short = a working day with a requirement, compared on active time; in_progress = today, not met yet;
#: absent = a past working day with no work session; holiday = weekly day off or company holiday;
#: no_target = a working day worked with no requirement set; upcoming = later than today.
AttendanceDayStatus = Literal["met", "short", "in_progress", "absent", "holiday", "no_target", "upcoming"]


class AttendanceSession(APIModel):
    """One work session, clipped to the local day."""

    start: datetime
    end: datetime
    #: Still running (end is "now").
    open: bool


class AttendanceReportDay(APIModel):
    day: date
    holiday: bool
    status: AttendanceDayStatus
    #: Required seconds for this day (0 on holidays, later days, or weekdays without a requirement).
    expected_seconds: int
    #: Active time (keyboard or mouse input): what is compared with the required hours.
    active_seconds: int
    #: Time signed in to a work session (active + idle).
    work_seconds: int
    idle_seconds: int
    #: Idle time with a customer system in front, counted as active (already included in active_seconds).
    customer_seconds: int = 0
    #: First sign-in and last sign-out of the day (local day bounds), or None without a session.
    first_in: datetime | None
    last_out: datetime | None
    sessions: list[AttendanceSession]


class AttendanceReportRow(APIModel):
    employee: EmployeeRef
    department_id: str | None
    team_id: str | None
    #: Active time over the range (the "logged" hours).
    logged_seconds: int
    work_seconds: int
    #: Required seconds over the working days up to today.
    expected_seconds: int
    #: Weekly days off and company holidays in the range.
    holidays: int
    #: Working days up to today.
    working_days: int
    #: Working days up to today with no work session at all.
    untracked_days: int
    #: Working days with a requirement that met it.
    days_met: int
    #: Past working days that had work but under the requirement.
    days_short: int = 0
    #: Customer-system idle time counted as active over the range (already included in logged_seconds).
    customer_seconds: int = 0
    #: Each day's detail. Left empty when the report was asked without details and has more than one person.
    days: list[AttendanceReportDay]


class AttendanceReport(APIModel):
    start: date
    end: date
    timezone: str
    #: Required minutes per weekday, Monday first (0 = no requirement).
    required_minutes: list[int]
    rows: list[AttendanceReportRow]
