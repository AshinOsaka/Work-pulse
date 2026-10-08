"""Periodic checks for conditions nobody "does": devices going quiet, long idle, overdue tasks, deadlines.

Each finding has a dedupe key, so every occurrence is announced once (an employee going offline during one work
session, a task becoming overdue on a given date…), however often the scanner runs and across restarts. Look-backs
are capped so the first run after deployment doesn't flood anyone with history.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from pymongo.asynchronous.database import AsyncDatabase

from app.auth.permissions import Permission
from app.core.broker import Broker, MemoryBroker
from app.core.config import Settings
from app.models.company import Company, CompanyStatus
from app.models.notification import NotificationType, Severity
from app.models.organization import Device, DeviceStatus, PresenceState
from app.models.work import ProjectStatus, TaskStatus
from app.repositories.company import CompanyRepository
from app.repositories.organization import DeviceRepository, EmployeeRepository
from app.repositories.work import ProjectRepository, TaskRepository
from app.services.notifications.notifier import AlertEvent, Notifier
from app.utils.time import utcnow

logger = logging.getLogger(__name__)

EXTENDED_IDLE = timedelta(minutes=30)
DEVICE_STALE = timedelta(hours=24)
LOOKBACK = timedelta(days=7)
DUE_SOON_DAYS = 2


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


class AlertScanner:
    def __init__(
        self,
        db: AsyncDatabase[dict[str, Any]],
        settings: Settings,
        notifier: Notifier,
        broker: Broker | None = None,
    ) -> None:
        self._broker: Broker = broker or MemoryBroker()
        self._settings = settings
        self._notifier = notifier
        self._companies = CompanyRepository(db)
        self._devices = DeviceRepository(db)
        self._employees = EmployeeRepository(db)
        self._projects = ProjectRepository(db)
        self._tasks = TaskRepository(db)
        self._task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._loop(), name="alert-scanner")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _loop(self) -> None:
        while True:
            try:
                # One process per cluster scans; the lease outlives a round, so a crashed holder is replaced.
                if await self._broker.lease("alert-scanner", self._settings.alert_scan_seconds * 3):
                    await self.scan_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Alert scan failed; will retry")
            await asyncio.sleep(self._settings.alert_scan_seconds)

    async def scan_once(self, now: datetime | None = None) -> int:
        """Emits events for every workspace; returns how many were emitted (before de-duplication)."""
        now = now or utcnow()
        emitted = 0
        for company in await self._companies.active_companies():
            if company.status == CompanyStatus.SUSPENDED:
                continue
            emitted += await self._devices_scan(company, now)
            emitted += await self._work_scan(company, now)
        return emitted

    def _emit(self, event: AlertEvent) -> int:
        self._notifier.emit(event)
        return 1

    # ------------------------------------------------------------------ devices & presence
    async def _devices_scan(self, company: Company, now: datetime) -> int:
        offline_after = timedelta(seconds=self._settings.agent_offline_after_seconds)
        devices = await self._devices.find_many(
            company.id, {"status": DeviceStatus.ACTIVE}, sort=None, limit=50_000
        )
        online_by_employee: dict[Any, int] = {}
        for d in devices:
            if d.last_seen_at and now - _aware(d.last_seen_at) <= offline_after:
                online_by_employee[d.employee_id] = online_by_employee.get(d.employee_id, 0) + 1
        emitted = 0
        for d in devices:
            seen = _aware(d.last_seen_at) if d.last_seen_at else None
            if seen is None:
                continue
            silent = now - seen
            # Went quiet in the middle of a work session (not a clean shutdown), and no other device is online.
            if (
                d.current_session_id
                and silent > offline_after
                and silent <= LOOKBACK
                and d.agent_stopped_at is None
                and not online_by_employee.get(d.employee_id)
            ):
                emitted += self._emit(
                    AlertEvent(
                        company_id=company.id,
                        type=NotificationType.EMPLOYEE_OFFLINE,
                        title="{employee} went offline during a work session",
                        body=f"{d.name} stopped reporting {_ago(silent)} ago while a work session was open. It may have "
                        "lost its network connection, been shut down or gone to sleep.",
                        employee_id=d.employee_id,
                        link="/live",
                        dedupe_key=f"employee-offline:{d.id}:{d.current_session_id}",
                        permission=Permission.ACTIVITY_VIEW,
                        data={"device_id": str(d.id)},
                    )
                )
            if DEVICE_STALE < silent <= LOOKBACK:
                emitted += self._emit(
                    AlertEvent(
                        company_id=company.id,
                        type=NotificationType.DEVICE_OFFLINE,
                        title=f"{d.name} hasn't been seen for {_ago(silent)}",
                        body="The desktop agent on {employee}'s computer last reported "
                        f"{seen.strftime('%d %b %H:%M UTC')}. If the computer is no longer used, revoke it under People.",
                        employee_id=d.employee_id,
                        link=f"/people/employees/{d.employee_id}",
                        subject=f"device:{d.id}",
                        dedupe_key=f"device-offline:{d.id}:{seen.isoformat()}",
                        permission=Permission.ACTIVITY_VIEW,
                        data={"device_id": str(d.id)},
                    )
                )
            if self._idle(d, now, offline_after):
                assert d.presence_since is not None
                emitted += self._emit(
                    AlertEvent(
                        company_id=company.id,
                        type=NotificationType.EXTENDED_IDLE,
                        title="{employee} has been idle for " + _ago(now - _aware(d.presence_since)),
                        body="No keyboard or mouse input during an open work session — often a call, a meeting or a "
                        "break. Not a judgement; just context.",
                        employee_id=d.employee_id,
                        link=f"/people/employees/{d.employee_id}",
                        dedupe_key=f"idle:{d.id}:{_aware(d.presence_since).isoformat()}",
                        permission=Permission.ACTIVITY_VIEW,
                    )
                )
        return emitted

    @staticmethod
    def _idle(d: Device, now: datetime, offline_after: timedelta) -> bool:
        return bool(
            d.current_session_id
            and d.presence == PresenceState.IDLE
            and d.presence_since
            and now - _aware(d.presence_since) >= EXTENDED_IDLE
            and d.last_seen_at
            and now - _aware(d.last_seen_at) <= offline_after
        )

    # ------------------------------------------------------------------ tasks & projects
    async def _work_scan(self, company: Company, now: datetime) -> int:
        today = now.astimezone(ZoneInfo(company.timezone)).date()
        projects = {
            p.id: p for p in await self._projects.visible(company.id, {"status": ProjectStatus.ACTIVE})
        }
        if not projects:
            return 0
        owners = await self._employees.find_by_ids(
            company.id, [p.owner_employee_id for p in projects.values() if p.owner_employee_id]
        )
        overdue = await self._tasks.query(
            company.id,
            {
                "project_id": {"$in": list(projects)},
                "status": {"$ne": TaskStatus.COMPLETED},
                "due_date": {"$gte": _midnight(today - LOOKBACK), "$lt": _midnight(today)},
            },
            limit=5000,
        )
        assignees = await self._employees.find_by_ids(
            company.id, list({a for t in overdue for a in t.assignee_ids})
        )
        emitted = 0
        for t in overdue:
            p = projects[t.project_id]
            owner = owners.get(p.owner_employee_id) if p.owner_employee_id else None
            users = [assignees[a].user_id for a in t.assignee_ids if a in assignees and assignees[a].user_id]
            if owner and owner.user_id:
                users.append(owner.user_id)
            if not users:
                continue
            due = _aware(t.due_date).date() if t.due_date else today
            emitted += self._emit(
                AlertEvent(
                    company_id=company.id,
                    type=NotificationType.TASK_OVERDUE,
                    title=f"{p.key}-{t.number} is overdue",
                    body=f"“{t.title}” in {p.name} was due {due.strftime('%d %b')} and isn't completed.",
                    link=f"/projects/{p.id}?task={t.id}",
                    subject=f"task:{t.id}",
                    dedupe_key=f"task-overdue:{t.id}:{due.isoformat()}",
                    user_ids=[u for u in users if u is not None],
                    data={"task_id": str(t.id), "project_id": str(p.id)},
                )
            )
        counts = await self._tasks.counts_by_project(company.id, list(projects))
        for p in projects.values():
            if not p.due_date:
                continue
            due = _aware(p.due_date).date()
            c = counts.get(p.id, {})
            open_tasks = sum(
                v for k, v in c.items() if k not in ("time_spent_seconds", TaskStatus.COMPLETED.value)
            )
            if not open_tasks:
                continue
            owner = owners.get(p.owner_employee_id) if p.owner_employee_id else None
            owner_users = [owner.user_id] if owner and owner.user_id else []
            if today <= due <= today + timedelta(days=DUE_SOON_DAYS):
                days_left = (due - today).days
                emitted += self._emit(
                    AlertEvent(
                        company_id=company.id,
                        type=NotificationType.PROJECT_DEADLINE,
                        title=f"{p.name} is due {'today' if days_left == 0 else 'tomorrow' if days_left == 1 else f'in {days_left} days'}",
                        body=f"{open_tasks} task{'s are' if open_tasks != 1 else ' is'} still open.",
                        link=f"/projects/{p.id}",
                        subject=f"project:{p.id}",
                        dedupe_key=f"project-due:{p.id}:{due.isoformat()}",
                        user_ids=owner_users,
                        permission=Permission.PROJECT_MANAGE,
                    )
                )
            elif today - LOOKBACK <= due < today:
                emitted += self._emit(
                    AlertEvent(
                        company_id=company.id,
                        type=NotificationType.PROJECT_DEADLINE,
                        severity=Severity.CRITICAL,
                        title=f"{p.name} is past its due date",
                        body=f"It was due {due.strftime('%d %b')} and {open_tasks} task{'s are' if open_tasks != 1 else ' is'} still open.",
                        link=f"/projects/{p.id}",
                        subject=f"project:{p.id}",
                        dedupe_key=f"project-overdue:{p.id}:{due.isoformat()}",
                        user_ids=owner_users,
                        permission=Permission.PROJECT_MANAGE,
                    )
                )
        return emitted


def _midnight(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=UTC)


def _ago(delta: timedelta) -> str:
    minutes = int(delta.total_seconds() // 60)
    if minutes < 60:
        return f"{minutes} min"
    hours = minutes // 60
    if hours < 48:
        return f"{hours} h"
    return f"{hours // 24} days"
