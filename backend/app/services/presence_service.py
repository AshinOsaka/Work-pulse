"""Live presence and work hours derived from agent heartbeats and work sessions."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

from app.auth.principal import Principal
from app.core.config import Settings
from app.core.exceptions import BadRequestError
from app.models.organization import Device, EmployeeStatus
from app.repositories.activity import ActivitySegmentRepository
from app.repositories.agent import WorkSessionRepository
from app.repositories.company import CompanyRepository
from app.repositories.organization import DeviceRepository, EmployeeQuery, EmployeeRepository, TeamRepository
from app.schemas.organization import Ref
from app.schemas.presence import (
    AttendanceDay,
    AttendanceSummary,
    EmployeePresence,
    PresenceCounts,
    PresenceDevice,
    PresenceOverview,
    PresenceStatus,
    WorkHoursSummary,
)
from app.services.access_scope import AccessScopeService
from app.services.employee_service import employee_ref
from app.services.helpers import parse_ref
from app.services.work_sessions import effective_ends
from app.utils.time import utcnow

Period = Literal["daily", "weekly", "monthly"]
HISTORY_BUCKETS = 8
MAX_ATTENDANCE_DAYS = 92


class PresenceService:
    def __init__(
        self,
        *,
        settings: Settings,
        companies: CompanyRepository,
        employees: EmployeeRepository,
        teams: TeamRepository,
        devices: DeviceRepository,
        sessions: WorkSessionRepository,
        segments: ActivitySegmentRepository,
        scopes: AccessScopeService,
    ) -> None:
        self._settings = settings
        self._segments = segments
        self._companies = companies
        self._employees = employees
        self._teams = teams
        self._devices = devices
        self._sessions = sessions
        self._scopes = scopes

    async def _visible_employee_query(self, principal: Principal, team_id: str | None) -> dict[str, Any]:
        scope = await self._scopes.employee_scope(principal)
        team = parse_ref(team_id, "team_id")
        clauses = [c for c in (scope.filter, {"team_id": team} if team else None) if c]
        return {"$and": clauses} if len(clauses) > 1 else (clauses[0] if clauses else {})

    def connected(self, device: Device, now: datetime) -> bool:
        if device.last_seen_at is None:
            return False
        if device.agent_stopped_at and device.agent_stopped_at >= device.last_seen_at:
            return False
        return now - device.last_seen_at <= timedelta(seconds=self._settings.agent_offline_after_seconds)

    async def overview(self, principal: Principal, team_id: str | None) -> PresenceOverview:
        company_id = principal.company_id
        now = utcnow()
        employees, _ = await self._employees.search(
            company_id,
            EmployeeQuery(
                statuses=(EmployeeStatus.ACTIVE, EmployeeStatus.ON_LEAVE),
                limit=5000,
                extra=await self._visible_employee_query(principal, team_id),
            ),
        )
        devices = await self._devices.latest_by_employee(company_id, [e.id for e in employees])
        teams = await self._teams.find_by_ids(company_id, [e.team_id for e in employees if e.team_id])
        open_sessions = {
            s.client_session_id: s
            for s in await self._sessions.find_many(
                company_id,
                {"device_id": {"$in": [d.id for d in devices.values()]}, "ended_at": None},
                limit=5000,
            )
        }

        rows: list[EmployeePresence] = []
        for employee in employees:
            device = devices.get(employee.id)
            connected = bool(device and self.connected(device, now))
            status: PresenceStatus = "offline"
            since = None
            session_started = None
            if device:
                if connected and device.presence:
                    status = device.presence.value
                    since = device.presence_since
                    session = open_sessions.get(device.current_session_id or "")
                    session_started = session.started_at if session else None
                else:
                    since = device.agent_stopped_at or device.last_seen_at
            team = teams.get(employee.team_id) if employee.team_id else None
            rows.append(
                EmployeePresence(
                    employee=employee_ref(employee),
                    team=Ref(id=str(team.id), name=team.name) if team else None,
                    status=status,
                    connected=connected,
                    since=since,
                    session_started_at=session_started,
                    device=PresenceDevice(
                        id=str(device.id),
                        name=device.name,
                        os=device.os,
                        agent_version=device.agent_version,
                        last_seen_at=device.last_seen_at,
                    )
                    if device
                    else None,
                    current_app=device.current_app if device and status != "offline" else None,
                )
            )

        counts = PresenceCounts(
            online=sum(r.connected for r in rows),
            active=sum(r.status == "active" for r in rows),
            idle=sum(r.status == "idle" for r in rows),
            offline=sum(r.status == "offline" for r in rows),
        )
        return PresenceOverview(employees=rows, counts=counts, as_of=now)

    async def work_hours(self, principal: Principal, period: Period, team_id: str | None) -> WorkHoursSummary:
        company_id = principal.company_id
        company = await self._companies.get_by_id(company_id)
        tz_name = company.timezone if company else "UTC"
        tz = ZoneInfo(tz_name)
        now = utcnow()
        buckets = _buckets(period, now.astimezone(tz), HISTORY_BUCKETS)
        employee_ids = await self._employees.ids_matching(
            company_id, await self._visible_employee_query(principal, team_id)
        )
        sessions = (
            await self._sessions.overlapping(company_id, employee_ids, buckets[0][0], now)
            if employee_ids
            else []
        )

        open_sessions = [s for s in sessions if s.ended_at is None]
        open_devices = list({s.device_id for s in open_sessions})
        devices = await self._devices.find_by_ids(company_id, open_devices) if open_devices else {}
        evidence = await self._segments.last_activity(
            company_id, [s.client_session_id for s in open_sessions]
        )
        open_ends = effective_ends(
            sessions, devices, now, timedelta(seconds=self._settings.agent_offline_after_seconds), evidence
        )

        history: list[float] = []
        for start, end in buckets:
            seconds = 0.0
            for session in sessions:
                session_end = session.ended_at or open_ends.get(session.id, now)
                overlap = (min(session_end, end, now) - max(session.started_at, start)).total_seconds()
                seconds += max(0.0, overlap)
            history.append(round(seconds / 3600, 2))
        return WorkHoursSummary(
            period=period,
            timezone=tz_name,
            current_hours=history[-1],
            previous_hours=history[-2],
            history=history,
        )


    async def attendance(
        self, principal: Principal, start: date, end: date, team_id: str | None
    ) -> AttendanceSummary:
        """Present (had a work session that local day) vs away (expected, no session), per working day.

        Away counts only active-status employees on working days; weekly days off and company holidays
        are marked and expect no one. WorkPulse has no per-day leave history, so nothing is invented.
        """
        if end < start:
            raise BadRequestError("The end date must not be before the start date.", code="invalid_range")
        if (end - start).days >= MAX_ATTENDANCE_DAYS:
            raise BadRequestError(f"Attendance covers at most {MAX_ATTENDANCE_DAYS} days.", code="range_too_long")
        company_id = principal.company_id
        company = await self._companies.get_by_id(company_id)
        tz = ZoneInfo(company.timezone if company else "UTC")
        work_days = set(company.work_days) if company else {1, 2, 3, 4, 5}
        holidays = set(company.holidays) if company else set()

        # "Expected" baseline is the active head-count; on-leave people are not counted as away.
        employee_ids = await self._employees.ids_matching(
            company_id,
            {"$and": [c for c in (await self._visible_employee_query(principal, team_id), {"status": EmployeeStatus.ACTIVE.value}) if c]},
        )
        now = utcnow()
        range_start = datetime.combine(start, time.min, tzinfo=tz)
        range_end = datetime.combine(end + timedelta(days=1), time.min, tzinfo=tz)
        sessions = (
            await self._sessions.overlapping(company_id, employee_ids, range_start, min(range_end, now))
            if employee_ids
            else []
        )
        open_sessions = [s for s in sessions if s.ended_at is None]
        open_devices = list({s.device_id for s in open_sessions})
        devices = await self._devices.find_by_ids(company_id, open_devices) if open_devices else {}
        evidence = await self._segments.last_activity(company_id, [s.client_session_id for s in open_sessions])
        open_ends = effective_ends(
            sessions, devices, now, timedelta(seconds=self._settings.agent_offline_after_seconds), evidence
        )

        expected = len(employee_ids)
        days: list[AttendanceDay] = []
        current = start
        while current <= end:
            day_start = datetime.combine(current, time.min, tzinfo=tz)
            day_end = datetime.combine(current + timedelta(days=1), time.min, tzinfo=tz)
            is_holiday = current.isoweekday() not in work_days or current.isoformat() in holidays
            present_ids: set[Any] = set()
            for session in sessions:
                session_end = session.ended_at or open_ends.get(session.id, now)
                if session.started_at < day_end and session_end > day_start:
                    present_ids.add(session.employee_id)
            present = len(present_ids)
            away = 0 if is_holiday else max(0, expected - present)
            days.append(AttendanceDay(day=current, holiday=is_holiday, present=present, away=away))
            current += timedelta(days=1)

        return AttendanceSummary(
            start=start, end=end, timezone=company.timezone if company else "UTC", expected=expected, days=days
        )


def _buckets(period: Period, local_now: datetime, count: int) -> list[tuple[datetime, datetime]]:
    """[start, end) windows in the company timezone, oldest first; the last contains `local_now`."""
    day_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
    starts: list[datetime] = []
    if period == "daily":
        starts = [day_start - timedelta(days=i) for i in range(count)]
    elif period == "weekly":
        week_start = day_start - timedelta(days=day_start.weekday())
        starts = [week_start - timedelta(weeks=i) for i in range(count)]
    else:
        month = day_start.replace(day=1)
        for _ in range(count):
            starts.append(month)
            month = (month - timedelta(days=1)).replace(day=1)
    starts.reverse()

    def next_start(start: datetime) -> datetime:
        if period == "daily":
            return (start + timedelta(days=1, hours=2)).replace(hour=0)  # DST-safe
        if period == "weekly":
            return (start + timedelta(days=7, hours=2)).replace(hour=0)
        return (start + timedelta(days=32)).replace(day=1, hour=0)

    return [(s, next_start(s)) for s in starts]
