"""Live presence and work hours derived from agent heartbeats and work sessions."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

from app.auth.principal import Principal
from app.core.config import Settings
from app.core.exceptions import BadRequestError
from app.models.agent import WorkSession
from app.models.organization import Device, EmployeeStatus
from app.repositories.activity import ActivitySegmentRepository
from app.repositories.agent import WorkSessionRepository
from app.repositories.company import CompanyRepository
from app.repositories.organization import DeviceRepository, EmployeeQuery, EmployeeRepository, TeamRepository
from app.schemas.organization import Ref
from app.schemas.presence import (
    AttendanceDay,
    AttendanceDayStatus,
    AttendanceReport,
    AttendanceReportDay,
    AttendanceReportRow,
    AttendanceSession,
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
from app.services.productivity.engine import day_bounds, local_days, time_accounting
from app.services.work_sessions import effective_ends
from app.utils.time import utcnow

Period = Literal["daily", "weekly", "monthly"]
HISTORY_BUCKETS = 8
MAX_ATTENDANCE_DAYS = 92


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


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

    async def attendance_report(
        self,
        principal: Principal,
        start: date,
        end: date,
        *,
        team_id: str | None = None,
        department_id: str | None = None,
        employee_id: str | None = None,
        details: bool = True,
    ) -> AttendanceReport:
        """Per person: active time against the company's required hours, with each day's sign-in/out.

        Hours come from the same work-session accounting as the productivity views (``time_accounting``),
        so the numbers match; this report only compares them with ``Company.required_minutes``. Scope is the
        caller's usual employee scope (a standard employee sees only themselves).
        """
        if end < start:
            raise BadRequestError("The end date must not be before the start date.", code="invalid_range")
        if (end - start).days >= MAX_ATTENDANCE_DAYS:
            raise BadRequestError(f"Attendance covers at most {MAX_ATTENDANCE_DAYS} days.", code="range_too_long")
        company_id = principal.company_id
        company = await self._companies.get_by_id(company_id)
        tz_name = company.timezone if company else "UTC"
        tz = ZoneInfo(tz_name)
        work_days = set(company.work_days) if company else {1, 2, 3, 4, 5}
        holiday_dates = set(company.holidays) if company else set()
        required = ((list(company.required_minutes) if company else []) + [0] * 7)[:7]

        department = parse_ref(department_id, "department_id")
        person = parse_ref(employee_id, "employee_id")
        clauses = [
            c
            for c in (await self._visible_employee_query(principal, team_id), {"_id": person} if person else None)
            if c
        ]
        employees, _ = await self._employees.search(
            company_id,
            EmployeeQuery(
                statuses=(EmployeeStatus.ACTIVE,),
                department_id=department,
                limit=5000,
                extra={"$and": clauses} if clauses else {},
            ),
        )

        now = utcnow()
        today = now.astimezone(tz).date()
        days = local_days(start, end)
        range_start, _ = day_bounds(start, tz)
        _, range_end = day_bounds(end, tz)
        ids = [e.id for e in employees]
        sessions = await self._sessions.overlapping(company_id, ids, range_start, min(range_end, now)) if ids else []
        open_sessions = [s for s in sessions if s.ended_at is None]
        devices = await self._devices.find_by_ids(company_id, list({s.device_id for s in open_sessions})) if open_sessions else {}
        evidence = await self._segments.last_activity(company_id, [s.client_session_id for s in open_sessions])
        grace = timedelta(seconds=self._settings.agent_offline_after_seconds)
        open_ends = effective_ends(sessions, devices, now, grace, evidence)
        by_employee: dict[Any, list[WorkSession]] = defaultdict(list)
        for session in sessions:
            by_employee[session.employee_id].append(session)

        rows: list[AttendanceReportRow] = []
        # Without details (the organisation table), each day's breakdown is left out; it is still included
        # when the report covers one person, whose per-day export needs it.
        with_days = details or len(employees) <= 1
        for employee in employees:
            own = sorted(by_employee.get(employee.id, []), key=lambda s: s.started_at)
            metrics = time_accounting(own, days, tz, now, open_ends)
            out_days: list[AttendanceReportDay] = []
            totals = {
                "logged": 0, "work": 0, "expected": 0, "holidays": 0, "working": 0, "untracked": 0, "met": 0, "short": 0,
            }  # fmt: skip
            for day in days:
                lo, hi = day_bounds(day, tz)
                pieces: list[AttendanceSession] = []
                # The sessions clipped to this day are only shown in the day's detail, not used by any total.
                for s in own if with_days else ():
                    s_end = _aware(s.ended_at) if s.ended_at else open_ends.get(s.id, now)
                    a, b = max(_aware(s.started_at), lo), min(s_end, hi)
                    if b > a:
                        running = s.ended_at is None and now - s_end < grace and b == s_end
                        pieces.append(AttendanceSession(start=a, end=b, open=running))
                m = metrics[day]
                active, work = round(m.active), round(m.work)
                holiday = day.isoweekday() not in work_days or day.isoformat() in holiday_dates
                expected = 0 if holiday or day > today else required[day.isoweekday() - 1] * 60
                status: AttendanceDayStatus
                if day > today:
                    status = "upcoming"
                elif holiday:
                    status = "holiday"
                elif work <= 0:
                    status = "in_progress" if day == today else "absent"
                elif expected <= 0:
                    status = "no_target"
                elif active >= expected:
                    status = "met"
                else:
                    status = "in_progress" if day == today else "short"
                if holiday:
                    totals["holidays"] += 1
                elif day <= today:
                    totals["working"] += 1
                    totals["untracked"] += int(work <= 0 and day < today)
                    totals["met"] += int(status == "met")
                    totals["short"] += int(status == "short")
                totals["logged"] += active
                totals["work"] += work
                totals["expected"] += expected
                if not with_days:
                    continue
                out_days.append(
                    AttendanceReportDay(
                        day=day,
                        holiday=holiday,
                        status=status,
                        expected_seconds=expected,
                        active_seconds=active,
                        work_seconds=work,
                        idle_seconds=round(m.idle),
                        first_in=pieces[0].start if pieces else None,
                        last_out=None if not pieces or pieces[-1].open else max(p.end for p in pieces),
                        sessions=pieces,
                    )
                )
            rows.append(
                AttendanceReportRow(
                    employee=employee_ref(employee),
                    department_id=str(employee.department_id) if employee.department_id else None,
                    team_id=str(employee.team_id) if employee.team_id else None,
                    logged_seconds=totals["logged"],
                    work_seconds=totals["work"],
                    expected_seconds=totals["expected"],
                    holidays=totals["holidays"],
                    working_days=totals["working"],
                    untracked_days=totals["untracked"],
                    days_met=totals["met"],
                    days_short=totals["short"],
                    days=out_days,
                )
            )
        return AttendanceReport(start=start, end=end, timezone=tz_name, required_minutes=required, rows=rows)


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
