"""Live screen viewing: policy, online-employee discovery and session requests (REST side).

Who may watch: `LIVE_STREAM_VIEW` within the viewer's access scope (out of scope or foreign: 404).
A stream can only be requested when the workspace has live viewing enabled, the employee's agent is
online, and a work session is running; one stream per employee at a time. Every request — granted or
denied — is audited. The signalling itself happens over WebSockets (see `LiveHub`).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.auth.permissions import Permission
from app.auth.principal import Principal
from app.core.config import Settings
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.models.company import Company
from app.models.live import LiveEventType, LiveSession, LiveStatus
from app.models.organization import Device, DeviceStatus, Employee, EmployeeStatus, PresenceState
from app.repositories.company import CompanyRepository
from app.repositories.live import LiveSessionEventRepository, LiveSessionRepository
from app.repositories.organization import (
    DepartmentRepository,
    DeviceRepository,
    EmployeeRepository,
    TeamRepository,
)
from app.schemas.live import (
    CONNECTION_STATE,
    Availability,
    LiveDevice,
    LiveEmployee,
    LiveEmployeeList,
    LivePolicyOut,
    LivePolicyUpdate,
    LiveSessionEventList,
    LiveSessionEventOut,
    LiveSessionList,
    LiveSessionOut,
    LiveSessionRef,
)
from app.schemas.organization import Ref
from app.services.access_scope import AccessScopeService
from app.services.audit_service import AuditService
from app.services.context import RequestMeta
from app.services.employee_service import employee_ref
from app.services.helpers import parse_id
from app.services.live_hub import LiveHub
from app.utils.time import utcnow

MAX_CONCURRENT_PER_VIEWER = 4
MAX_HISTORY = 200
_NOT_FOUND = "Live session not found."


def policy_out(company: Company) -> LivePolicyOut:
    return LivePolicyOut(**company.live_policy.model_dump())


def _device_out(device: Device | None) -> LiveDevice | None:
    if device is None:
        return None
    return LiveDevice(
        id=str(device.id), name=device.name, os=device.os.value, last_seen_at=device.last_seen_at
    )


class LiveService:
    def __init__(
        self,
        *,
        settings: Settings,
        companies: CompanyRepository,
        employees: EmployeeRepository,
        departments: DepartmentRepository,
        teams: TeamRepository,
        devices: DeviceRepository,
        sessions: LiveSessionRepository,
        events: LiveSessionEventRepository,
        scopes: AccessScopeService,
        audit: AuditService,
        hub: LiveHub,
    ) -> None:
        self._settings = settings
        self._companies = companies
        self._employees = employees
        self._departments = departments
        self._teams = teams
        self._devices = devices
        self._sessions = sessions
        self._events = events
        self._scopes = scopes
        self._audit = audit
        self._hub = hub

    async def _company(self, company_id: ObjectId) -> Company:
        company = await self._companies.get_by_id(company_id)
        if company is None:
            raise NotFoundError("Workspace not found.")
        return company

    # ------------------------------------------------------------------ policy
    async def get_policy(self, principal: Principal) -> LivePolicyOut:
        """Visible to every member, so employees know whether their screen can be viewed."""
        return policy_out(await self._company(principal.company_id))

    async def update_policy(
        self, principal: Principal, data: LivePolicyUpdate, meta: RequestMeta
    ) -> LivePolicyOut:
        company = await self._company(principal.company_id)
        changes = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}
        if not changes:
            return policy_out(company)
        merged = company.live_policy.model_copy(update=changes)
        updated = await self._companies.update_by_id(company.id, {"live_policy": merged.model_dump()})
        await self._audit.record(
            "policy.live_view_updated",
            company_id=company.id,
            actor_user_id=principal.user_id,
            target_type="company",
            target_id=str(company.id),
            meta=meta,
            metadata={"fields": sorted(changes), "enabled": merged.enabled},
        )
        if not merged.enabled:
            for session in await self._sessions.active_in_company(company.id):
                await self._hub.end(session.id, "live_view_disabled", actor_user_id=principal.user_id)
        return policy_out(updated or company)

    # ------------------------------------------------------------------ discovery
    def _working(self, device: Device) -> bool:
        return bool(device.current_session_id) and device.presence in (
            PresenceState.ACTIVE,
            PresenceState.IDLE,
        )

    def _pick_device(self, devices: list[Device], online_ids: set[ObjectId]) -> Device | None:
        """Prefer an online device with a running work session, then any online device, then the latest seen."""
        online = [d for d in devices if d.id in online_ids]
        working = [d for d in online if self._working(d)]
        ranked = working or online or devices
        return max(ranked, key=lambda d: d.last_seen_at or d.created_at) if ranked else None

    async def employees(self, principal: Principal) -> LiveEmployeeList:
        company = await self._company(principal.company_id)
        scope = await self._scopes.employee_scope(principal)
        clauses: list[dict[str, Any]] = [{"status": {"$ne": EmployeeStatus.TERMINATED}}]
        if scope.filter:
            clauses.append(scope.filter)
        ids = await self._employees.ids_matching(principal.company_id, {"$and": clauses})
        people = await self._employees.find_by_ids(principal.company_id, ids)
        devices = await self._devices.find_many(
            principal.company_id,
            {"employee_id": {"$in": ids}, "status": DeviceStatus.ACTIVE},
            sort=None,
            limit=5000,
        )
        by_employee: dict[ObjectId, list[Device]] = {}
        for item in devices:
            by_employee.setdefault(item.employee_id, []).append(item)
        online_ids = await self._hub.online_devices([d.id for d in devices])  # one round trip
        teams = await self._teams.find_by_ids(
            principal.company_id, [e.team_id for e in people.values() if e.team_id]
        )
        departments = await self._departments.find_by_ids(
            principal.company_id, [e.department_id for e in people.values() if e.department_id]
        )
        live = {s.employee_id: s for s in await self._sessions.active_in_company(principal.company_id)}
        enabled = company.live_policy.enabled

        rows: list[LiveEmployee] = []
        for employee in people.values():
            device = self._pick_device(by_employee.get(employee.id, []), online_ids)
            if device is None:
                continue  # no agent installed: nothing to show on a live page
            online = device.id in online_ids
            working = online and self._working(device)
            session = live.get(employee.id)
            availability: Availability
            if not enabled:
                availability = "disabled"
            elif session:
                availability = "in_session"
            elif not online:
                availability = "offline"
            elif not working:
                availability = "not_working"
            else:
                availability = "available"
            team = teams.get(employee.team_id) if employee.team_id else None
            department = departments.get(employee.department_id) if employee.department_id else None
            rows.append(
                LiveEmployee(
                    employee=employee_ref(employee),
                    department=Ref(id=str(department.id), name=department.name) if department else None,
                    team=Ref(id=str(team.id), name=team.name) if team else None,
                    device=_device_out(device),
                    online=online,
                    presence=device.presence.value if working and device.presence else None,
                    current_app=device.current_app if working else None,
                    status_since=device.presence_since if working else device.last_seen_at,
                    live_session=LiveSessionRef(
                        id=str(session.id),
                        status=session.status,
                        viewer_name=session.viewer_name,
                        mine=session.viewer_user_id == principal.user_id,
                    )
                    if session
                    else None,
                    availability=availability,
                )
            )
        order = {"available": 0, "in_session": 1, "not_working": 2, "offline": 3, "disabled": 4}
        rows.sort(key=lambda r: (order[r.availability], r.employee.full_name.lower()))
        return LiveEmployeeList(
            enabled=enabled, max_session_minutes=company.live_policy.max_session_minutes, employees=rows
        )

    # ------------------------------------------------------------------ sessions
    async def _deny(self, principal: Principal, employee: Employee, reason: str, meta: RequestMeta) -> None:
        await self._audit.record(
            "live.session_denied",
            company_id=principal.company_id,
            actor_user_id=principal.user_id,
            target_type="employee",
            target_id=str(employee.id),
            subject_employee_id=employee.id,
            meta=meta,
            metadata={"reason": reason},
        )

    async def start(
        self, principal: Principal, employee_id: str, meta: RequestMeta, device_id: str | None = None
    ) -> LiveSessionOut:
        """Start viewing an employee's screen. Company and viewer always come from the signed-in principal.

        `device_id` is optional: without it the employee's working, online device is chosen. With it, that device
        must belong to the employee, be registered (active) and be online.
        """
        company = await self._company(principal.company_id)
        oid = parse_id(employee_id, not_found="Employee not found.", code="employee_not_found")
        scope = await self._scopes.employee_scope(principal)
        employee = await self._employees.get_in_scope(principal.company_id, oid, scope.filter)
        if employee is None or employee.status == EmployeeStatus.TERMINATED:
            raise NotFoundError("Employee not found.", code="employee_not_found")

        if not company.live_policy.enabled:
            await self._deny(principal, employee, "disabled", meta)
            raise ForbiddenError("Live viewing is turned off for this workspace.", code="live_view_disabled")
        devices = await self._devices.find_many(
            principal.company_id, {"employee_id": employee.id, "status": DeviceStatus.ACTIVE}, sort=None
        )
        if device_id is not None:
            wanted = parse_id(device_id, not_found="Device not found.", code="device_not_found")
            chosen = next((d for d in devices if d.id == wanted), None)
            if chosen is None:
                # Unknown, revoked, another employee's or another company's device: all look the same.
                raise NotFoundError("Device not found for this employee.", code="device_not_found")
            devices = [chosen]
        device = self._pick_device(devices, await self._hub.online_devices([d.id for d in devices]))
        if device is None or not await self._hub.is_online(device.id):
            await self._deny(principal, employee, "offline", meta)
            raise ConflictError(f"{employee.full_name}'s desktop agent is offline.", code="agent_offline")
        if not self._working(device):
            await self._deny(principal, employee, "not_working", meta)
            raise ConflictError(
                f"{employee.full_name} isn't in a work session. Live viewing is only possible while they work.",
                code="not_working",
            )
        existing = await self._sessions.active_for_employee(principal.company_id, employee.id)
        if existing:
            if existing.viewer_user_id == principal.user_id:
                return self._out(existing, employee, device)  # rejoin your own stream
            await self._deny(principal, employee, "in_session", meta)
            raise ConflictError(
                f"{existing.viewer_name} is already viewing this screen.", code="already_live"
            )
        mine = [
            s
            for s in await self._sessions.active_in_company(principal.company_id)
            if s.viewer_user_id == principal.user_id
        ]
        if len(mine) >= MAX_CONCURRENT_PER_VIEWER:
            raise ConflictError(
                "Stop one of your live streams before starting another.", code="too_many_streams"
            )

        now = utcnow()
        session = LiveSession(
            company_id=principal.company_id,
            employee_id=employee.id,
            device_id=device.id,
            viewer_user_id=principal.user_id,
            viewer_name=principal.user.full_name,
            expires_at=now + timedelta(minutes=company.live_policy.max_session_minutes),
            media_route=self._hub.route.name,
        )
        try:
            await self._sessions.create(principal.company_id, session)
        except DuplicateKeyError:
            # Lost a race with a simultaneous request: the same viewer gets that session (a double click is
            # idempotent), anyone else is told who is already viewing.
            existing = await self._sessions.active_for_employee(principal.company_id, employee.id)
            if existing and existing.viewer_user_id == principal.user_id:
                return self._out(existing, employee, device)
            raise ConflictError(
                f"{existing.viewer_name if existing else 'Someone'} is already viewing this screen.",
                code="already_live",
            ) from None
        await self._hub.open_session(session)
        await self._hub.record_event(
            session,
            LiveEventType.REQUESTED,
            actor_role="viewer",
            actor_id=principal.user_id,
            role=principal.role.value,
            device_id=str(device.id),
        )
        await self._hub.record_event(
            session,
            LiveEventType.AUTHORIZED,
            actor_role="viewer",
            actor_id=principal.user_id,
            checks=["permission", "scope", "policy", "device_registered", "device_online", "work_session"],
            max_minutes=company.live_policy.max_session_minutes,
        )
        await self._audit.record(
            "live.session_requested",
            company_id=principal.company_id,
            actor_user_id=principal.user_id,
            target_type="live_session",
            target_id=str(session.id),
            subject_employee_id=employee.id,
            meta=meta,
            metadata={
                "max_minutes": company.live_policy.max_session_minutes,
                "device": device.name,
                "device_id": str(device.id),
            },
        )
        return self._out(session, employee, device)

    async def _owned(self, principal: Principal, session_id: str) -> LiveSession:
        """Viewers see their own sessions; anyone else in scope with the permission sees them too (read only)."""
        oid = parse_id(session_id, not_found=_NOT_FOUND, code="live_session_not_found")
        session = await self._sessions.get_by_id(principal.company_id, oid)
        if session is None:
            raise NotFoundError(_NOT_FOUND, code="live_session_not_found")
        scope = await self._scopes.employee_scope(principal)
        if (
            await self._employees.get_in_scope(principal.company_id, session.employee_id, scope.filter)
            is None
        ):
            raise NotFoundError(_NOT_FOUND, code="live_session_not_found")
        return session

    async def get(self, principal: Principal, session_id: str) -> LiveSessionOut:
        session = await self._owned(principal, session_id)
        employee = await self._employees.get_by_id(principal.company_id, session.employee_id)
        device = await self._devices.get_by_id(principal.company_id, session.device_id)
        assert employee is not None
        return self._out(session, employee, device)

    async def events(self, principal: Principal, session_id: str) -> LiveSessionEventList:
        """The session's timeline, for whoever may see the session."""
        session = await self._owned(principal, session_id)
        rows = await self._events.for_session(principal.company_id, session.id)
        return LiveSessionEventList(
            session_id=str(session.id),
            items=[
                LiveSessionEventOut(
                    id=str(e.id),
                    event=e.event,
                    actor_role=e.actor_role,
                    actor_id=str(e.actor_id) if e.actor_id else None,
                    metadata=e.metadata,
                    timestamp=e.timestamp,
                )
                for e in rows
            ],
        )

    async def stop(self, principal: Principal, session_id: str) -> LiveSessionOut:
        session = await self._owned(principal, session_id)
        if session.viewer_user_id != principal.user_id and not principal.has(Permission.POLICY_MANAGE):
            raise ForbiddenError("Only the viewer can stop this stream.", code="not_your_stream")
        if session.status != LiveStatus.ENDED:
            ended = await self._hub.end(session.id, "viewer_stopped", actor_user_id=principal.user_id)
            if not ended:  # not tracked by this process (e.g. restarted): close the record directly
                await self._sessions.set_status(
                    principal.company_id,
                    session.id,
                    {"status": LiveStatus.ENDED, "ended_at": utcnow(), "end_reason": "viewer_stopped"},
                )
        return await self.get(principal, session_id)

    async def history(self, principal: Principal, employee_id: str | None, limit: int) -> LiveSessionList:
        """The session log: who watched whom, on which device, when, for how long and why it ended.

        Scoped like everything else: a manager sees sessions on people in their reporting line, whoever watched.
        """
        scope = await self._scopes.employee_scope(principal)
        if employee_id is not None:
            oid = parse_id(employee_id, not_found="Employee not found.", code="employee_not_found")
            if await self._employees.get_in_scope(principal.company_id, oid, scope.filter) is None:
                raise NotFoundError("Employee not found.", code="employee_not_found")
            ids: list[ObjectId] | None = [oid]
        elif scope.filter:
            ids = await self._employees.ids_matching(principal.company_id, scope.filter)
        else:
            ids = None
        sessions = await self._sessions.recent(principal.company_id, ids, min(limit, MAX_HISTORY))
        people = await self._employees.find_by_ids(
            principal.company_id, list({s.employee_id for s in sessions})
        )
        devices = await self._devices.find_by_ids(principal.company_id, list({s.device_id for s in sessions}))
        return LiveSessionList(
            items=[
                self._out(s, people[s.employee_id], devices.get(s.device_id))
                for s in sessions
                if s.employee_id in people
            ]
        )

    def can_join(self, principal: Principal, session: LiveSession) -> bool:
        return session.viewer_user_id == principal.user_id and session.status != LiveStatus.ENDED

    @staticmethod
    def _out(session: LiveSession, employee: Employee, device: Device | None) -> LiveSessionOut:
        return LiveSessionOut(
            id=str(session.id),
            status=session.status,
            employee=employee_ref(employee),
            device=_device_out(device),
            viewer_name=session.viewer_name,
            created_at=session.created_at,
            connected_at=session.connected_at,
            expires_at=session.expires_at,
            ended_at=session.ended_at,
            end_reason=session.end_reason,
            duration_seconds=session.duration_seconds,
            reconnects=session.reconnects,
            media_route=session.media_route,
            connection_state=CONNECTION_STATE[session.status],
        )
