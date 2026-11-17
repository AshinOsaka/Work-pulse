"""Sends the automatic report e-mails and the unproductive-time alert.

Every minute one process in the cluster (lease) checks each workspace that switched the feature on:

* **Reports**: on a working day, once ``midday_time`` / ``evening_time`` (company time zone) has passed — and for up
  to `SEND_WINDOW` after, so a restart soon after still sends it, but a late restart doesn't send stale mail — the
  report is claimed once per workspace, day and slot (a unique record), the figures are collected, and each
  recipient gets one digest. The mid-day run stores a snapshot so the evening report can show the afternoon.
  Admins choose twice a day (mid-day + evening) or once (only one of them); without a mid-day report the evening
  one covers the whole day.
* **Unproductive alert**: every minute, today's Unproductive time per person — the day's total (once a day) and/or
  one continuous stretch (once per stretch, at most `MAX_STRETCH_ALERTS` a day). The employee and their manager are
  e-mailed and an in-app alert is raised. Data arrives as the desktop agent closes activity segments (on every app or
  website change, and at least every 15 minutes), so alerts follow within minutes.

Recipients: each employee's manager (Employee.manager_employee_id, else their team lead), plus the extra
recipients from Settings, who get everyone. An address appearing in both gets one e-mail with everyone it covers.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import anthropic
from bson import ObjectId
from pymongo import ASCENDING, DESCENDING, IndexModel, ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.auth.effective import permissions_for_user
from app.auth.permissions import Permission, Role
from app.auth.principal import Principal
from app.core.broker import Broker
from app.core.config import Settings
from app.models.company import Company
from app.models.notification import NotificationType
from app.models.organization import Employee, EmployeeStatus
from app.models.user import UserStatus
from app.repositories.activity import ActivitySegmentRepository
from app.repositories.company import CompanyRepository
from app.repositories.organization import DepartmentRepository, EmployeeRepository, TeamRepository
from app.repositories.productivity import ProductivityRuleRepository
from app.repositories.user import UserRepository
from app.services.auto_reports.figures import (
    SLOTS,
    Figures,
    PersonReport,
    SignIn,
    Slot,
    duration,
    usage_from_items,
    usage_minus,
    usage_snapshot,
)
from app.services.auto_reports.render import build_digest
from app.services.auto_reports.stretches import Stretch, unproductive_stretches
from app.services.auto_reports.summary import Summary, ai_summary, plain_summary
from app.services.email_service import EmailMessage, EmailSender
from app.services.notifications.notifier import AlertEvent, Notifier
from app.services.presence_service import PresenceService
from app.services.productivity.engine import Segment, classify_segments
from app.services.productivity.rules import EmployeeContext, RuleBook
from app.services.productivity.service import ProductivityService
from app.utils.schedule import is_working_day
from app.utils.time import utcnow

logger = logging.getLogger(__name__)

TICK_SECONDS = 60
SEND_WINDOW = timedelta(hours=2)
ALERT_CHECK_EVERY = timedelta(minutes=1)
MAX_STRETCH_ALERTS = 4
AVERAGE_DAYS = 7

RUNS = "auto_report_runs"
SNAPSHOTS = "auto_report_snapshots"
ALERTS = "auto_report_alert_log"
AI_USAGE = "auto_report_ai_usage"
#: One record per e-mail sent (or skipped), for the overview in Settings; kept 90 days.
DELIVERIES = "auto_report_deliveries"
#: E-mails sent per workspace and day, against `Settings.report_email_daily_cap`.
EMAIL_COUNT = "auto_report_email_count"


@dataclass
class Recipient:
    email: str
    name: str
    employee_ids: set[ObjectId] = field(default_factory=set)


@dataclass
class RunResult:
    people: int = 0
    sent: int = 0
    failed: int = 0
    ai: int = 0
    recipients: list[str] = field(default_factory=list)


def _hhmm(value: str) -> time:
    hour, minute = (int(part) for part in value.split(":"))
    return time(hour, minute)


class AutoReportJob:
    def __init__(
        self,
        db: AsyncDatabase[dict[str, Any]],
        settings: Settings,
        broker: Broker,
        email: EmailSender,
        notifier: Notifier,
        build_productivity: Callable[[], ProductivityService],
        build_presence: Callable[[], PresenceService],
    ) -> None:
        self._db = db
        self._settings = settings
        self._broker = broker
        self._email = email
        self._notifier = notifier
        self._build_productivity = build_productivity
        self._build_presence = build_presence
        self._companies = CompanyRepository(db)
        self._employees = EmployeeRepository(db)
        self._teams = TeamRepository(db)
        self._users = UserRepository(db)
        key = settings.report_ai_api_key.get_secret_value() if settings.report_ai_api_key else ""
        self._ai = anthropic.AsyncAnthropic(api_key=key, max_retries=2, timeout=60.0) if key else None
        self._last_alert_check: dict[ObjectId, datetime] = {}
        self._task: asyncio.Task[None] | None = None
        self._indexed = False

    @property
    def ai_available(self) -> bool:
        return self._ai is not None

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> None:
        self._task = asyncio.create_task(self._loop(), name="auto-reports")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def ensure_indexes(self) -> None:
        if self._indexed:
            return
        await self._db[RUNS].create_indexes(
            [
                IndexModel(
                    [("company_id", ASCENDING), ("day", ASCENDING), ("slot", ASCENDING)],
                    unique=True,
                    name="uniq_run",
                ),
                IndexModel([("company_id", ASCENDING), ("started_at", DESCENDING)], name="company_recent"),
            ]
        )
        await self._db[SNAPSHOTS].create_indexes(
            [
                IndexModel(
                    [("company_id", ASCENDING), ("day", ASCENDING), ("employee_id", ASCENDING)],
                    unique=True,
                    name="uniq_snapshot",
                ),
                # Snapshots are only needed until the evening report.
                IndexModel([("created_at", ASCENDING)], expireAfterSeconds=3 * 86_400, name="ttl"),
            ]
        )
        await self._db[ALERTS].create_indexes(
            [
                IndexModel(
                    [
                        ("company_id", ASCENDING),
                        ("day", ASCENDING),
                        ("employee_id", ASCENDING),
                        ("key", ASCENDING),
                    ],
                    unique=True,
                    name="uniq_alert",
                ),
                IndexModel([("created_at", ASCENDING)], expireAfterSeconds=40 * 86_400, name="ttl"),
            ]
        )
        await self._db[DELIVERIES].create_indexes(
            [
                IndexModel([("company_id", ASCENDING), ("sent_at", DESCENDING)], name="company_recent"),
                IndexModel([("sent_at", ASCENDING)], expireAfterSeconds=90 * 86_400, name="ttl"),
            ]
        )
        await self._db[EMAIL_COUNT].create_indexes(
            [
                IndexModel([("company_id", ASCENDING), ("day", ASCENDING)], unique=True, name="uniq_day"),
                IndexModel([("created_at", ASCENDING)], expireAfterSeconds=40 * 86_400, name="ttl"),
            ]
        )
        await self._db[AI_USAGE].create_indexes(
            [IndexModel([("company_id", ASCENDING), ("day", ASCENDING)], unique=True, name="uniq_day")]
        )
        self._indexed = True

    async def _loop(self) -> None:
        while True:
            try:
                if await self._broker.lease("auto-reports", TICK_SECONDS * 3):
                    await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Automatic reports check failed; will retry")
            await asyncio.sleep(TICK_SECONDS)

    # ------------------------------------------------------------------ schedule
    async def tick(self, now: datetime | None = None) -> int:
        """Runs whatever is due; returns how many reports ran."""
        await self.ensure_indexes()
        now = now or utcnow()
        ran = 0
        for company in await self._companies.active_companies():
            policy = company.auto_reports
            if not (policy.enabled or policy.unproductive_alert_enabled):
                continue
            zone = ZoneInfo(company.timezone)
            local = now.astimezone(zone)
            today = local.date()
            if not is_working_day(today, company.work_days, company.holidays):
                continue
            if policy.enabled:
                for slot in SLOTS:
                    if not (policy.midday_enabled if slot == "midday" else policy.evening_enabled):
                        continue
                    due = datetime.combine(today, _hhmm(self._slot_time(company, slot)), zone)
                    if due <= local < due + SEND_WINDOW and await self._claim_run(
                        company.id, today, slot, now
                    ):
                        try:
                            result = await self.run_slot(company, slot, today, now)
                            await self._finish_run(company.id, today, slot, result)
                        except Exception:
                            logger.exception("Automatic %s report failed for company %s", slot, company.id)
                            await self._finish_run(company.id, today, slot, None)
                        ran += 1
            if policy.unproductive_alert_enabled:
                last = self._last_alert_check.get(company.id)
                if last is None or now - last >= ALERT_CHECK_EVERY:
                    self._last_alert_check[company.id] = now
                    await self.check_unproductive(company, today, now)
        return ran

    @staticmethod
    def _slot_time(company: Company, slot: Slot) -> str:
        return company.auto_reports.midday_time if slot == "midday" else company.auto_reports.evening_time

    async def _claim_run(self, company_id: ObjectId, day: date, slot: Slot, now: datetime) -> bool:
        try:
            await self._db[RUNS].insert_one(
                {
                    "company_id": company_id,
                    "day": day.isoformat(),
                    "slot": slot,
                    "started_at": now,
                    "status": "running",
                }
            )
        except DuplicateKeyError:
            return False
        return True

    async def _finish_run(
        self, company_id: ObjectId, day: date, slot: Slot, result: RunResult | None
    ) -> None:
        update: dict[str, Any] = {"finished_at": utcnow(), "status": "failed" if result is None else "done"}
        if result is not None:
            update |= {"people": result.people, "sent": result.sent, "failed": result.failed, "ai": result.ai}
        await self._db[RUNS].update_one(
            {"company_id": company_id, "day": day.isoformat(), "slot": slot}, {"$set": update}
        )

    async def recent_runs(self, company_id: ObjectId, limit: int = 10) -> list[dict[str, Any]]:
        await self.ensure_indexes()
        cursor = self._db[RUNS].find({"company_id": company_id}).sort("started_at", -1).limit(limit)
        return [doc async for doc in cursor]

    # ------------------------------------------------------------------ figures
    async def _active_employees(self, company_id: ObjectId) -> list[Employee]:
        return await self._employees.find_many(
            company_id, {"status": EmployeeStatus.ACTIVE}, sort=(("full_name", 1),), limit=50_000
        )

    async def _system_principal(self, company_id: ObjectId) -> Principal | None:
        """A workspace administrator, so the attendance figures are computed exactly as on the Attendance page."""
        admins = await self._users.find_many(
            company_id,
            {
                "status": UserStatus.ACTIVE,
                "role": {"$in": [Role.COMPANY_ADMIN.value, Role.SUPER_ADMIN.value]},
            },
            sort=(("created_at", 1),),
            limit=1,
        )
        if not admins:
            return None
        return Principal(user=admins[0], permissions=await permissions_for_user(self._db, admins[0]))

    async def collect(
        self, company: Company, slot: Slot, today: date, *, store_snapshot: bool
    ) -> tuple[list[PersonReport], str | None]:
        """Everyone's figures for the slot, and the start of the period ("HH:MM") for the evening report."""
        employees = await self._active_employees(company.id)
        if not employees:
            return [], None
        zone = ZoneInfo(company.timezone)
        productivity = self._build_productivity()
        data = await productivity.compute(company, employees, today, today, with_segments=True)
        history = await productivity.compute(
            company,
            employees,
            today - timedelta(days=AVERAGE_DAYS),
            today - timedelta(days=1),
            with_segments=False,
        )
        first_activity = await self._first_activity(company.id, [e.id for e in employees], today, zone)
        screenshots = await self._screenshots_today(company.id, [e.id for e in employees], today, zone)
        workday_start = datetime.combine(today, _hhmm(company.start_check_time), zone)
        departments = await DepartmentRepository(self._db).find_by_ids(
            company.id, {e.department_id for e in employees if e.department_id}
        )
        teams = await self._teams.find_by_ids(company.id, {e.team_id for e in employees if e.team_id})
        attendance: dict[str, Any] = {}
        principal = await self._system_principal(company.id)
        if principal is not None:
            report = await self._build_presence().attendance_report(principal, today, today, details=True)
            attendance = {row.employee.id: row.days[0] for row in report.rows if row.days}

        # Week so far (Monday to today) and the same days last week, for the "week" items.
        week_start = today - timedelta(days=today.weekday())
        prev_start = week_start - timedelta(days=7)
        prev_end = prev_start + (today - week_start)
        week_rows: dict[str, Any] = {}
        if principal is not None:
            week_report = await self._build_presence().attendance_report(
                principal, week_start, today, details=False
            )
            week_rows = {row.employee.id: row for row in week_report.rows}
        weeks = await productivity.compute(company, employees, prev_start, today, with_segments=False)
        ids = [e.id for e in employees]
        pending = await self._pending_claims(company.id, ids)
        overdue = await self._overdue_tasks(company.id, ids, today, zone)

        snapshots: dict[ObjectId, dict[str, Any]] = {}
        period_start: str | None = None
        if slot == "evening":
            async for doc in self._db[SNAPSHOTS].find({"company_id": company.id, "day": today.isoformat()}):
                snapshots[doc["employee_id"]] = doc
            if snapshots:
                period_start = company.auto_reports.midday_time

        people: list[PersonReport] = []
        to_store: list[dict[str, Any]] = []
        for e in employees:
            own = data.get(e.id)
            m = own.days.get(today) if own else None
            day_figures = Figures.from_metrics(m) if m else Figures()
            day_usage = usage_from_items(own.day_items.get(today, []) if own else [])
            period, usage = day_figures, day_usage
            snap = snapshots.get(e.id)
            if slot == "evening" and snapshots:
                earlier = Figures.from_dict(snap["figures"]) if snap else Figures()
                period = day_figures.minus(earlier)
                usage = usage_minus(day_usage, snap["usage"] if snap else {})
            if store_snapshot:
                to_store.append(
                    {
                        "company_id": company.id,
                        "day": today.isoformat(),
                        "employee_id": e.id,
                        "figures": day_figures.to_dict(),
                        "usage": usage_snapshot(day_usage),
                        "created_at": utcnow(),
                    }
                )
            past = history.get(e.id)
            worked = [
                Figures.from_metrics(pm)
                for d, pm in (past.days.items() if past else [])
                if pm.work > 0 and is_working_day(d, company.work_days, company.holidays)
            ]
            avg_active = sum(f.active for f in worked) / len(worked) if worked else None
            shares = [f.productive_share for f in worked if f.productive_share is not None]
            row = attendance.get(str(e.id))
            wk = week_rows.get(str(e.id))
            this_week, last_week = Figures(), Figures()
            for d, wm in weeks[e.id].days.items() if e.id in weeks else []:
                if week_start <= d <= today:
                    this_week = this_week.plus(Figures.from_metrics(wm))
                elif prev_start <= d <= prev_end:
                    last_week = last_week.plus(Figures.from_metrics(wm))
            midnight = datetime.combine(today, time(0, 0), zone)
            sessions = [
                SignIn(
                    start=s.start.astimezone(zone),
                    end=s.end.astimezone(zone),
                    open=s.open,
                    from_yesterday=s.start.astimezone(zone) <= midnight,
                )
                for s in (row.sessions if row else [])
            ]
            dept = departments.get(e.department_id) if e.department_id else None
            team = teams.get(e.team_id) if e.team_id else None
            first_in = first_activity.get(e.id) or next(
                (s.start for s in sessions if not s.from_yesterday), None
            )
            people.append(
                PersonReport(
                    employee_id=e.id,
                    name=e.full_name,
                    email=e.email,
                    manager_id=e.manager_employee_id,
                    team_id=e.team_id,
                    period=period,
                    day=day_figures,
                    usage=usage,
                    first_in=first_in,
                    sessions=sessions,
                    department=dept.name if dept else "",
                    department_id=e.department_id,
                    meetings=row.meeting_seconds if row else 0,
                    screenshots=screenshots.get(e.id, 0),
                    week_active=wk.logged_seconds if wk else None,
                    week_expected=wk.expected_seconds if wk else 0,
                    week_met=wk.days_met if wk else 0,
                    week_days=wk.working_days if wk else 0,
                    this_week=this_week,
                    last_week=last_week if last_week.work > 0 else None,
                    pending_claims=pending.get(e.id, 0),
                    overdue_tasks=overdue.get(e.id, 0),
                    late_by=(
                        (first_in - workday_start).total_seconds()
                        if first_in and (first_in - workday_start).total_seconds() >= 60
                        else None
                    ),
                    team=team.name if team else "",
                    attendance=row.status if row else None,
                    attended_active=row.active_seconds if row else round(day_figures.active),
                    expected=row.expected_seconds if row else 0,
                    avg_active=avg_active,
                    avg_share=round(sum(shares) / len(shares)) if shares else None,
                )
            )
        # Grouped by department (then team) in the e-mail; people without one come last.
        people.sort(key=lambda p: (not p.department, p.department.lower(), p.team.lower(), p.name.lower()))
        if to_store:
            for doc in to_store:
                await self._db[SNAPSHOTS].replace_one(
                    {"company_id": doc["company_id"], "day": doc["day"], "employee_id": doc["employee_id"]},
                    doc,
                    upsert=True,
                )
        return people, period_start

    async def _first_activity(
        self, company_id: ObjectId, employee_ids: list[ObjectId], today: date, zone: ZoneInfo
    ) -> dict[ObjectId, datetime]:
        """Each person's first app or website activity that began today (company time zone).

        The attendance "first in" is the session start clipped to midnight, so a session left open overnight would
        read 00:00; the first activity that started today is what "started work" means in the report."""
        lo = datetime.combine(today, time(0, 0), zone).astimezone(UTC)
        hi = lo + timedelta(days=1)
        pipeline: list[dict[str, Any]] = [
            {
                "$match": {
                    "company_id": company_id,
                    "employee_id": {"$in": employee_ids},
                    "started_at": {"$gte": lo.replace(tzinfo=None), "$lt": hi.replace(tzinfo=None)},
                }
            },
            {"$group": {"_id": "$employee_id", "first": {"$min": "$started_at"}}},
        ]
        cursor = await self._db["activity_segments"].aggregate(pipeline)
        return {doc["_id"]: _aware(doc["first"]).astimezone(zone) async for doc in cursor}

    async def _pending_claims(
        self, company_id: ObjectId, employee_ids: list[ObjectId]
    ) -> dict[ObjectId, int]:
        """Meeting / time claims still waiting for approval, per person."""
        pipeline: list[dict[str, Any]] = [
            {"$match": {"company_id": company_id, "employee_id": {"$in": employee_ids}, "status": "pending"}},
            {"$group": {"_id": "$employee_id", "n": {"$sum": 1}}},
        ]
        cursor = await self._db["time_claims"].aggregate(pipeline)
        return {doc["_id"]: int(doc["n"]) async for doc in cursor}

    async def _overdue_tasks(
        self, company_id: ObjectId, employee_ids: list[ObjectId], today: date, zone: ZoneInfo
    ) -> dict[ObjectId, int]:
        """Open tasks whose due date has passed, per assignee."""
        midnight = datetime.combine(today, time(0, 0), zone).astimezone(UTC).replace(tzinfo=None)
        pipeline: list[dict[str, Any]] = [
            {
                "$match": {
                    "company_id": company_id,
                    "assignee_ids": {"$in": employee_ids},
                    "status": {"$ne": "COMPLETED"},
                    "due_date": {"$ne": None, "$lt": midnight},
                }
            },
            {"$unwind": "$assignee_ids"},
            {"$match": {"assignee_ids": {"$in": employee_ids}}},
            {"$group": {"_id": "$assignee_ids", "n": {"$sum": 1}}},
        ]
        cursor = await self._db["tasks"].aggregate(pipeline)
        return {doc["_id"]: int(doc["n"]) async for doc in cursor}

    async def _screenshots_today(
        self, company_id: ObjectId, employee_ids: list[ObjectId], today: date, zone: ZoneInfo
    ) -> dict[ObjectId, int]:
        lo = datetime.combine(today, time(0, 0), zone).astimezone(UTC).replace(tzinfo=None)
        pipeline: list[dict[str, Any]] = [
            {
                "$match": {
                    "company_id": company_id,
                    "employee_id": {"$in": employee_ids},
                    "captured_at": {"$gte": lo, "$lt": lo + timedelta(days=1)},
                }
            },
            {"$group": {"_id": "$employee_id", "n": {"$sum": 1}}},
        ]
        cursor = await self._db["screenshots"].aggregate(pipeline)
        return {doc["_id"]: int(doc["n"]) async for doc in cursor}

    # ------------------------------------------------------------------ recipients
    async def recipients(
        self, company: Company, people: list[PersonReport], slot: Slot | None = None
    ) -> list[Recipient]:
        policy = company.auto_reports
        by_email: dict[str, Recipient] = {}
        if policy.send_to_managers:
            employees = list(
                (await self._employees.find_by_ids(company.id, {p.employee_id for p in people})).values()
            )
            for employee_id, manager in (await self._managers_of(company, employees)).items():
                key = manager.email.strip().lower()
                by_email.setdefault(key, Recipient(manager.email, manager.full_name)).employee_ids.add(
                    employee_id
                )
        for extra in policy.extra_recipients:
            if slot is not None and not (extra.midday if slot == "midday" else extra.evening):
                continue
            covered = {p.employee_id for p in people if _covers(extra.department_ids, extra.team_ids, p)}
            key = extra.email.strip().lower()
            by_email.setdefault(
                key, Recipient(extra.email, extra.email.split("@")[0])
            ).employee_ids |= covered
        return [r for r in by_email.values() if r.employee_ids]

    # ------------------------------------------------------------------ summaries
    async def _ai_allowed(self, company: Company, day: date) -> bool:
        if (
            self._ai is None
            or not company.auto_reports.ai_summary
            or self._settings.report_ai_daily_calls <= 0
        ):
            return False
        doc = await self._db[AI_USAGE].find_one_and_update(
            {"company_id": company.id, "day": day.isoformat()},
            {"$inc": {"calls": 1}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return int((doc or {}).get("calls", 1)) <= self._settings.report_ai_daily_calls

    async def summarise(self, company: Company, people: list[PersonReport], slot: Slot, day: date) -> Summary:
        if self._ai is not None and await self._ai_allowed(company, day):
            result = await ai_summary(self._ai, self._settings.report_ai_model, people, slot)
            if result is not None:
                return result
        return plain_summary(people, slot)

    # ------------------------------------------------------------------ reports
    async def run_slot(
        self,
        company: Company,
        slot: Slot,
        today: date,
        now: datetime,
        *,
        only_to: tuple[str, str] | None = None,
    ) -> RunResult:
        """Builds and sends one slot's digests. With `only_to` (address, name): a test — one digest with everyone
        to that address, no snapshot stored and no manager e-mailed."""
        people, period_start = await self.collect(
            company, slot, today, store_snapshot=only_to is None and slot == "midday"
        )
        result = RunResult(people=len(people))
        if not people:
            return result
        if only_to is not None:
            targets = [Recipient(only_to[0], only_to[1], {p.employee_id for p in people})]
        else:
            targets = await self.recipients(company, people, slot)
        link = f"{self._settings.frontend_url.rstrip('/')}/productivity"
        period_end = now.astimezone(ZoneInfo(company.timezone)).strftime("%H:%M")
        for target in targets:
            subset = [p for p in people if p.employee_id in target.employee_ids]
            if "summary" in company.auto_reports.sections:
                summary = await self.summarise(company, subset, slot, today)
            else:  # no summary in the e-mail: no AI call either
                summary = Summary("", ["" for _ in subset], by_ai=False)
            result.ai += int(summary.by_ai)
            for p, note in zip(subset, summary.notes, strict=True):
                p.note = note
            digest = build_digest(
                company_name=company.name,
                recipient_name=target.name,
                people=subset,
                summary=summary,
                slot=slot,
                day=today,
                period_start=period_start,
                period_end=period_end,
                link=link,
                test=only_to is not None,
                sections=company.auto_reports.sections,
                actions_link=f"{self._settings.frontend_url.rstrip('/')}/time-claims",
            )
            status = await self._deliver(
                company,
                today,
                EmailMessage(to=target.email, subject=digest.subject, text=digest.text, html=digest.html),
                kind="report",
                slot=slot,
                name=target.name,
                employee_ids=[p.employee_id for p in subset],
                test=only_to is not None,
            )
            if status == "sent":
                result.sent += 1
                result.recipients.append(target.email)
            else:
                result.failed += 1
        if only_to is None:
            await self._send_own_reports(company, people, slot, today, period_start, period_end, link, result)
        return result

    async def _send_own_reports(
        self,
        company: Company,
        people: list[PersonReport],
        slot: Slot,
        today: date,
        period_start: str | None,
        period_end: str,
        link: str,
        result: RunResult,
    ) -> None:
        """Each employee's own report (when switched on): their row only, the default employee content or their
        own, and a summary written from the numbers (no AI, so cost doesn't grow with headcount)."""
        policy = company.auto_reports
        if not policy.employee_reports_enabled or not (
            policy.employee_midday if slot == "midday" else policy.employee_evening
        ):
            return
        settings = {s.employee_id: s for s in policy.employee_settings}
        for p in people:
            own = settings.get(str(p.employee_id))
            if (own and not own.enabled) or not p.email:
                continue
            sections = (own.sections if own and own.sections else None) or policy.employee_sections
            plain = plain_summary([p], slot)
            digest = build_digest(
                company_name=company.name,
                recipient_name=p.name.split(" ")[0] or p.name,
                people=[p],
                summary=Summary(plain.notes[0], [""], by_ai=False),
                slot=slot,
                day=today,
                period_start=period_start,
                period_end=period_end,
                link=link,
                sections=sections,
                personal=True,
            )
            status = await self._deliver(
                company,
                today,
                EmailMessage(to=p.email, subject=digest.subject, text=digest.text, html=digest.html),
                kind="own",
                slot=slot,
                name=p.name,
                employee_ids=[p.employee_id],
            )
            if status == "sent":
                result.sent += 1
            else:
                result.failed += 1

    async def _deliver(
        self,
        company: Company,
        day: date,
        message: EmailMessage,
        *,
        kind: str,
        slot: str | None,
        name: str,
        employee_ids: list[ObjectId],
        test: bool = False,
    ) -> str:
        """Sends one e-mail within the daily cap and records it: "sent", "failed" or "over_limit"."""
        cap = self._settings.report_email_daily_cap
        counter = await self._db[EMAIL_COUNT].find_one_and_update(
            {"company_id": company.id, "day": day.isoformat()},
            {"$inc": {"count": 1}, "$setOnInsert": {"created_at": utcnow()}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        if int((counter or {}).get("count", 1)) > cap:
            status = "over_limit"
            logger.warning("Daily e-mail limit (%d) reached for company %s; e-mail skipped", cap, company.id)
        else:
            try:
                await self._email.send(message)
                status = "sent"
            except Exception:
                logger.exception("Automatic %s e-mail failed (company %s)", kind, company.id)
                status = "failed"
        await self._db[DELIVERIES].insert_one(
            {
                "company_id": company.id,
                "day": day.isoformat(),
                "sent_at": utcnow(),
                "kind": kind,
                "slot": slot,
                "to": message.to.strip().lower(),
                "name": name,
                "employee_ids": employee_ids,
                "status": status,
                "test": test,
            }
        )
        return status

    # ------------------------------------------------------------------ alert history (Settings)
    async def alert_history(self, company: Company, start: date, end: date) -> list[dict[str, Any]]:
        """Unproductive alerts between two local days, newest first, with each person's current department and
        team and the manager who was told."""
        await self.ensure_indexes()
        docs = [
            d
            async for d in self._db[ALERTS]
            .find({"company_id": company.id, "day": {"$gte": start.isoformat(), "$lte": end.isoformat()}})
            .sort("created_at", -1)
            .limit(5000)
        ]
        if not docs:
            return []
        people = await self._employees.find_by_ids(company.id, {d["employee_id"] for d in docs})
        departments = await DepartmentRepository(self._db).find_by_ids(
            company.id, {e.department_id for e in people.values() if e.department_id}
        )
        teams = await self._teams.find_by_ids(company.id, {e.team_id for e in people.values() if e.team_id})
        zone = ZoneInfo(company.timezone)
        rows = []
        for d in docs:
            e = people.get(d["employee_id"])
            dept = departments.get(e.department_id) if e and e.department_id else None
            team = teams.get(e.team_id) if e and e.team_id else None
            start_at, end_at = d.get("stretch_start"), d.get("stretch_end")
            rows.append(
                {
                    "at": _aware(d["created_at"]),
                    "day": d["day"],
                    "employee_id": str(d["employee_id"]),
                    "employee": e.full_name if e else "Removed employee",
                    "department": dept.name if dept else "",
                    "team": team.name if team else "",
                    "manager": d.get("manager_name") or "",
                    "kind": d.get("kind", "total"),
                    "minutes": round(d["seconds"] / 60) if d.get("seconds") is not None else None,
                    "where": d.get("where") or "",
                    "span": (
                        f"{_aware(start_at).astimezone(zone):%H:%M} to {_aware(end_at).astimezone(zone):%H:%M}"
                        if start_at and end_at
                        else ""
                    ),
                }
            )
        return rows

    # ------------------------------------------------------------------ overview (Settings)
    async def overview(self, company: Company, now: datetime | None = None) -> dict[str, Any]:
        """Who gets what: departments, teams, heads and leads, each person's report recipient, the extra
        recipients they're covered by, and the e-mails of the last 7 days (sent, failed, over the daily limit)."""
        await self.ensure_indexes()
        now = now or utcnow()
        zone = ZoneInfo(company.timezone)
        today = now.astimezone(zone).date()
        employees = await self._active_employees(company.id)
        departments = await DepartmentRepository(self._db).list_all(company.id)
        teams = await self._teams.list_all(company.id)
        leaders = await self._employees.find_by_ids(
            company.id,
            {d.head_employee_id for d in departments if d.head_employee_id}
            | {t.lead_employee_id for t in teams if t.lead_employee_id},
        )
        report_to = (
            await self._managers_of(company, employees) if company.auto_reports.send_to_managers else {}
        )

        def person(emp_id: ObjectId | None) -> dict[str, str] | None:
            e = leaders.get(emp_id) if emp_id else None
            return {"name": e.full_name, "email": e.email} if e else None

        since = now - timedelta(days=7)
        deliveries = [
            d
            async for d in self._db[DELIVERIES].find(
                {"company_id": company.id, "sent_at": {"$gte": since}, "test": False}
            )
        ]
        reports: dict[ObjectId, int] = defaultdict(int)
        last_report: dict[ObjectId, datetime] = {}
        alerts: dict[ObjectId, int] = defaultdict(int)
        recipients: dict[str, dict[str, Any]] = {}
        for d in deliveries:
            r = recipients.setdefault(
                d["to"],
                {
                    "email": d["to"],
                    "name": d.get("name") or "",
                    "sent": 0,
                    "failed": 0,
                    "over_limit": 0,
                    "reports": 0,
                    "alerts": 0,
                    "last_sent_at": None,
                },
            )
            r[d["status"] if d["status"] in ("sent", "failed", "over_limit") else "failed"] += 1
            r["reports" if d["kind"] == "report" else "alerts"] += 1
            sent_at = _aware(d["sent_at"])
            if d["status"] == "sent" and (r["last_sent_at"] is None or sent_at > r["last_sent_at"]):
                r["last_sent_at"] = sent_at
            for emp in d.get("employee_ids") or []:
                if d["kind"] == "report" and d["status"] == "sent":
                    reports[emp] += 1
                    if emp not in last_report or sent_at > last_report[emp]:
                        last_report[emp] = sent_at
        # An alert e-mails the employee and their manager: count it once, by the e-mail to the employee.
        emails = {e.id: e.email.strip().lower() for e in employees}
        for d in deliveries:
            if d["kind"] == "alert":
                for emp in d.get("employee_ids") or []:
                    if emails.get(emp) == d["to"]:
                        alerts[emp] += 1

        dept_name = {d.id: d.name for d in departments}
        team_name = {t.id: t.name for t in teams}
        rows: list[dict[str, Any]] = []
        for e in employees:
            boss = report_to.get(e.id)
            snapshot = PersonReport(
                employee_id=e.id,
                name=e.full_name,
                email=e.email,
                manager_id=e.manager_employee_id,
                team_id=e.team_id,
                period=Figures(),
                day=Figures(),
                department_id=e.department_id,
            )
            extras = [
                x.email
                for x in company.auto_reports.extra_recipients
                if _covers(x.department_ids, x.team_ids, snapshot)
            ]
            rows.append(
                {
                    "id": str(e.id),
                    "name": e.full_name,
                    "department": dept_name.get(e.department_id, "") if e.department_id else "",
                    "team": team_name.get(e.team_id, "") if e.team_id else "",
                    "report_to": {"name": boss.full_name, "email": boss.email} if boss else None,
                    "extra_recipients": extras,
                    "reports_7d": reports.get(e.id, 0),
                    "alerts_7d": alerts.get(e.id, 0),
                    "last_report_at": last_report.get(e.id),
                }
            )
        rows.sort(
            key=lambda r: (not r["department"], r["department"].lower(), r["team"].lower(), r["name"].lower())
        )

        counts: dict[ObjectId | None, int] = defaultdict(int)
        team_counts: dict[ObjectId, int] = defaultdict(int)
        for e in employees:
            counts[e.department_id] += 1
            if e.team_id:
                team_counts[e.team_id] += 1
        structure = [
            {
                "id": str(d.id),
                "name": d.name,
                "head": person(d.head_employee_id),
                "employees": counts.get(d.id, 0),
                "teams": [
                    {
                        "id": str(t.id),
                        "name": t.name,
                        "lead": person(t.lead_employee_id),
                        "employees": team_counts.get(t.id, 0),
                    }
                    for t in teams
                    if t.department_id == d.id
                ],
            }
            for d in departments
        ]
        loose_teams = [t for t in teams if not t.department_id or t.department_id not in dept_name]
        if counts.get(None) or loose_teams:
            structure.append(
                {
                    "id": None,
                    "name": "No department",
                    "head": None,
                    "employees": counts.get(None, 0),
                    "teams": [
                        {
                            "id": str(t.id),
                            "name": t.name,
                            "lead": person(t.lead_employee_id),
                            "employees": team_counts.get(t.id, 0),
                        }
                        for t in loose_teams
                    ],
                }
            )
        counter = await self._db[EMAIL_COUNT].find_one({"company_id": company.id, "day": today.isoformat()})
        return {
            "emails_today": int((counter or {}).get("count", 0)),
            "email_daily_cap": self._settings.report_email_daily_cap,
            "departments": structure,
            "employees": rows,
            "not_covered": [r["name"] for r in rows if not r["report_to"] and not r["extra_recipients"]],
            "recipients": sorted(
                recipients.values(), key=lambda r: (-(r["reports"] + r["alerts"]), r["email"])
            ),
        }

    # ------------------------------------------------------------------ unproductive alert
    async def check_unproductive(self, company: Company, today: date, now: datetime) -> int:
        """E-mails the employee and their manager (and alerts in-app) when Unproductive time passes a limit."""
        policy = company.auto_reports
        total_limit = policy.unproductive_alert_minutes * 60 if policy.unproductive_total_enabled else None
        stretch_limit = (
            policy.unproductive_continuous_minutes * 60 if policy.unproductive_continuous_enabled else None
        )
        limits = [x for x in (total_limit, stretch_limit) if x is not None]
        if not limits:
            return 0
        employees = await self._active_employees(company.id)
        if not employees:
            return 0
        data = await self._build_productivity().compute(company, employees, today, today, with_segments=False)
        # A stretch can't be longer than the day's total, so only people over the lower limit are looked at.
        candidates = [
            e
            for e in employees
            if e.id in data
            and today in data[e.id].days
            and data[e.id].days[today].unproductive >= min(limits)
        ]
        if not candidates:
            return 0
        findings: list[tuple[Employee, Finding]] = []
        for e in candidates:
            seconds = data[e.id].days[today].unproductive
            if total_limit is not None and seconds >= total_limit:
                worst = [
                    u
                    for u in usage_from_items(data[e.id].day_items.get(today, []))
                    if u.category == "unproductive"
                ][:3]
                where = ", ".join(f"{u.name} ({duration(u.seconds)})" for u in worst)
                findings.append((e, Finding("total", "total", seconds, where)))
        if stretch_limit is not None:
            stretches = await self._stretches(company, candidates, today)
            for e in candidates:
                for st in stretches.get(e.id, []):
                    if st.seconds >= stretch_limit:
                        key = f"stretch:{st.start.isoformat()}"
                        findings.append((e, Finding("continuous", key, st.seconds, st.where(), st)))
        if not findings:
            return 0
        # Unproductive alerts always go to the employee's manager (or team lead), whatever the report routing.
        managers = await self._managers_of(
            company, list({e.id: e for e, _ in findings}.values()), route="manager"
        )
        zone = ZoneInfo(company.timezone)
        sent = 0
        for employee, finding in findings:
            if finding.kind == "continuous":
                told = await self._db[ALERTS].count_documents(
                    {
                        "company_id": company.id,
                        "day": today.isoformat(),
                        "employee_id": employee.id,
                        "kind": "continuous",
                    }
                )
                if told >= MAX_STRETCH_ALERTS:
                    continue
            manager = managers.get(employee.id)
            try:
                await self._db[ALERTS].insert_one(
                    {
                        "company_id": company.id,
                        "day": today.isoformat(),
                        "employee_id": employee.id,
                        "key": finding.key,
                        "kind": finding.kind,
                        "created_at": now,
                        # Kept for the alert history in Settings.
                        "seconds": round(finding.seconds),
                        "where": finding.where,
                        "stretch_start": finding.stretch.start if finding.stretch else None,
                        "stretch_end": finding.stretch.end if finding.stretch else None,
                        "manager_name": manager.full_name if manager else None,
                        "manager_email": manager.email if manager else None,
                    }
                )
            except DuplicateKeyError:
                continue  # already told
            await self._send_unproductive(company, employee, manager, finding, zone, today)
            if finding.kind == "total":
                title = f"{{employee}} passed {policy.unproductive_alert_minutes} minutes of Unproductive time today"
                body = f"{duration(finding.seconds)} in apps and websites marked Unproductive today"
            else:
                title = f"{{employee}} was Unproductive for {duration(finding.seconds)} without a break"
                body = f"{_span(finding, zone)} in apps and websites marked Unproductive"
            self._notifier.emit(
                AlertEvent(
                    company_id=company.id,
                    type=NotificationType.UNPRODUCTIVE_TIME,
                    title=title,
                    body=body + (f": {finding.where}." if finding.where else "."),
                    employee_id=employee.id,
                    link="/productivity",
                    subject=f"{employee.id}:{finding.key}",
                    dedupe_key=f"unproductive:{employee.id}:{today.isoformat()}:{finding.key}",
                    permission=Permission.ACTIVITY_VIEW,
                    include_employee=True,
                )
            )
            sent += 1
        return sent

    async def _stretches(
        self, company: Company, employees: list[Employee], today: date
    ) -> dict[ObjectId, list[Stretch]]:
        """Today's continuous Unproductive stretches per person, classified with each person's own rules."""
        zone = ZoneInfo(company.timezone)
        lo = datetime.combine(today, time(0, 0), zone)
        rules = await ProductivityRuleRepository(self._db).all_for_company(company.id)
        users = await self._users.find_by_ids(company.id, [e.user_id for e in employees if e.user_id])
        docs = await ActivitySegmentRepository(self._db).light_for_employees(
            company.id, [e.id for e in employees], lo, lo + timedelta(days=1), 100_000
        )
        segments: dict[ObjectId, list[Segment]] = defaultdict(list)
        for d in docs:
            segments[d["employee_id"]].append(
                Segment(
                    _aware(d["started_at"]),
                    _aware(d["ended_at"]),
                    d["app_id"],
                    d["app_name"],
                    d.get("domain"),
                )
            )
        out: dict[ObjectId, list[Stretch]] = {}
        for e in employees:
            user = users.get(e.user_id) if e.user_id else None
            context = EmployeeContext(
                department_id=e.department_id,
                team_id=e.team_id,
                role=user.role.value if user else None,
                profile_id=e.work_profile_id,
            )
            classified = classify_segments(segments.get(e.id, []), RuleBook(rules, context))
            out[e.id] = unproductive_stretches(classified)
        return out

    async def _managers_of(
        self, company: Company, employees: list[Employee], route: str | None = None
    ) -> dict[ObjectId, Employee]:
        """Who receives each person's report and alerts, by the workspace's choice (``route_by``): their manager,
        department head or team lead — falling back to the manager, then the team lead, when that isn't set.
        Never the person themselves, and only active people with an e-mail address."""
        route = route or company.auto_reports.route_by
        team_ids = {e.team_id for e in employees if e.team_id}
        leads = (
            {
                t.id: t.lead_employee_id
                for t in (await self._teams.find_by_ids(company.id, team_ids)).values()
                if t.lead_employee_id
            }
            if team_ids
            else {}
        )
        heads: dict[ObjectId, ObjectId] = {}
        if route == "department_head":
            dept_ids = {e.department_id for e in employees if e.department_id}
            heads = {
                d.id: d.head_employee_id
                for d in (await DepartmentRepository(self._db).find_by_ids(company.id, dept_ids)).values()
                if d.head_employee_id
            }

        def pick(e: Employee) -> ObjectId | None:
            lead = leads.get(e.team_id) if e.team_id else None
            head = heads.get(e.department_id) if e.department_id else None
            order = {
                "department_head": [head, e.manager_employee_id, lead],
                "team_lead": [lead, e.manager_employee_id],
            }.get(route, [e.manager_employee_id, lead])
            return next((b for b in order if b and b != e.id), None)

        boss_of = {e.id: pick(e) for e in employees}
        bosses = await self._employees.find_by_ids(company.id, {b for b in boss_of.values() if b})
        return {
            employee_id: bosses[boss_id]
            for employee_id, boss_id in boss_of.items()
            if boss_id
            and boss_id in bosses
            and boss_id != employee_id
            and bosses[boss_id].status == EmployeeStatus.ACTIVE
            and bosses[boss_id].email
        }

    async def _send_unproductive(
        self,
        company: Company,
        employee: Employee,
        manager: Employee | None,
        finding: Finding,
        zone: ZoneInfo,
        today: date,
    ) -> None:
        policy = company.auto_reports
        link = f"{self._settings.frontend_url.rstrip('/')}/productivity"
        detail = f"Mostly: {finding.where}.\n\n" if finding.where else ""
        first = employee.full_name.split(" ")[0] or employee.full_name
        if finding.kind == "total":
            what = (
                f"{duration(finding.seconds)} today in apps and websites that {company.name} marks as Unproductive "
                f"— more than the {policy.unproductive_alert_minutes} minutes a day set by your workspace"
            )
            subject = f"Unproductive time today: {duration(finding.seconds)}"
            how_often = "at most once a day"
        else:
            what = (
                f"{_span(finding, zone)} in apps and websites that {company.name} marks as Unproductive, without a "
                f"break — more than the {policy.unproductive_continuous_minutes} minutes set by your workspace"
            )
            subject = f"Unproductive for {duration(finding.seconds)} without a break"
            how_often = "once per stretch"
        messages = [
            EmailMessage(
                to=employee.email,
                subject=f"[WorkPulse] {subject}",
                text=(
                    f"Hello {first},\n\nWorkPulse has recorded {what}.\n\n{detail}"
                    + ("Your manager has received a copy of this message. " if manager else "")
                    + "If this time was work-related, please tell your manager so the rules can be corrected.\n\n"
                    f"You can see your own figures in WorkPulse: {link}\n\n"
                    f"This is an automatic message from WorkPulse, sent {how_often}."
                ),
            )
        ]
        if manager is not None:
            messages.append(
                EmailMessage(
                    to=manager.email,
                    subject=f"[WorkPulse] {employee.full_name}: {subject}",
                    text=(
                        f"Hello {manager.full_name.split(' ')[0] or manager.full_name},\n\n"
                        f"WorkPulse has recorded for {employee.full_name}: {what}.\n\n{detail}"
                        f"{employee.full_name} has been told the same. These are recorded figures under your "
                        "workspace's rules; if the time was work-related, the rules can be adjusted.\n\n"
                        f"Open WorkPulse: {link}\n\nThis is an automatic message, sent {how_often} per person."
                    ),
                )
            )
        for message, who in zip(messages, [employee, manager], strict=False):
            await self._deliver(
                company,
                today,
                message,
                kind="alert",
                slot=None,
                name=who.full_name if who else "",
                employee_ids=[employee.id],
            )


def _covers(department_ids: list[str], team_ids: list[str], p: PersonReport) -> bool:
    """Whether an extra recipient's choice (departments, teams; none = all) includes this person."""
    if department_ids and str(p.department_id or "") not in department_ids:
        return False
    return not team_ids or str(p.team_id or "") in team_ids


@dataclass
class Finding:
    kind: str  # "total" or "continuous"
    #: Unique per person and day: "total", or "stretch:<start>".
    key: str
    seconds: float
    where: str
    stretch: Stretch | None = None


def _span(finding: Finding, zone: ZoneInfo) -> str:
    """ "22m from 10:05 to 10:27"."""
    if finding.stretch is None:
        return duration(finding.seconds)
    start = finding.stretch.start.astimezone(zone).strftime("%H:%M")
    end = finding.stretch.end.astimezone(zone).strftime("%H:%M")
    return f"{duration(finding.seconds)} from {start} to {end}"


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)
