"""Time claims: logging time away from the computer, the daily limit without approval, and manager review.

Rules:

* Employees log their own time, for today or the previous 7 days, never in the future, without overlapping their
  other claims, within one local day.
* Up to the company's daily limit (``Company.time_claim_auto_minutes``, default 2 hours, counted over all of that
  day's claims) the time counts straight away and the employee's managers are told. Beyond it the claim waits
  for a manager. Managers can reject a counted claim later, or approve a rejected one.
* A claim manager is someone with ``TIME_CLAIM_MANAGE`` whose scope includes the employee (their reporting line,
  or everyone for administrators). They approve, reject, edit and delete those claims, and can log one meeting
  for several of their people at once (already approved, for the last 31 days). Nobody reviews their own
  claims, except company administrators (who have nobody above them).
* Approved time counts in attendance only (see ``PresenceService.attendance_report``), and only the part of it
  without keyboard or mouse input: time already counted from the computer is never counted twice.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from bson import ObjectId

from app.auth.permissions import Permission, Role
from app.auth.principal import Principal
from app.core.exceptions import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from app.models.notification import NotificationType, Severity
from app.models.time_claim import TimeClaim, TimeClaimKind, TimeClaimStatus
from app.repositories.company import CompanyRepository
from app.repositories.organization import EmployeeRepository
from app.repositories.time_claim import TimeClaimRepository, overlaps
from app.schemas.organization import Ref
from app.schemas.time_claims import (
    TimeClaimCreate,
    TimeClaimEdit,
    TimeClaimOut,
    TimeClaimPage,
    TimeClaimReview,
    TimeClaimSkipped,
    TimeClaimTeamCreate,
    TimeClaimTeamResult,
)
from app.services.access_scope import AccessScopeService
from app.services.audit_service import AuditService
from app.services.context import RequestMeta
from app.services.helpers import parse_id, parse_ref
from app.services.notifications.notifier import AlertEvent, Notifier
from app.utils.time import utcnow

#: How far back an employee can log time, and a manager can add or change it for their people.
MAX_DAYS_BACK = 7
MANAGER_DAYS_BACK = 31
MIN_MINUTES = 5
ADMIN_ROLES = frozenset({Role.SUPER_ADMIN, Role.COMPANY_ADMIN})

KIND_LABELS: dict[TimeClaimKind, str] = {
    TimeClaimKind.MEETING: "Meeting",
    TimeClaimKind.CLIENT_MEETING: "Client meeting",
    TimeClaimKind.FIELD_VISIT: "Field visit",
    TimeClaimKind.CALL: "Call",
    TimeClaimKind.OTHER: "Other work away from the computer",
}


def _minutes(claim: TimeClaim) -> int:
    return round((claim.ended_at - claim.started_at).total_seconds() / 60)


def _hours(minutes: int) -> str:
    hours, rest = divmod(minutes, 60)
    if hours and rest:
        return f"{hours}h {rest:02d}m"
    return f"{hours}h" if hours else f"{rest}m"


def claim_window(
    tz: ZoneInfo, day: date, start_time: str, end_time: str, *, days_back: int, now: datetime
) -> tuple[datetime, datetime]:
    """The claimed span as UTC datetimes, after the date and time rules (raises a field error otherwise)."""
    today = now.astimezone(tz).date()
    if day > today:
        raise BadRequestError("You can't log time for a future day.", code="future_day", details={"field": "day"})
    if day < today - timedelta(days=days_back):
        raise BadRequestError(
            f"Time can be logged for the last {days_back} days only.", code="too_old", details={"field": "day"}
        )
    start = datetime.combine(day, time.fromisoformat(start_time), tzinfo=tz)
    end = datetime.combine(day, time.fromisoformat(end_time), tzinfo=tz)
    if end <= start:
        raise BadRequestError(
            "The end time must be after the start time.", code="invalid_range", details={"field": "end_time"}
        )
    if (end - start) < timedelta(minutes=MIN_MINUTES):
        raise BadRequestError(f"Log at least {MIN_MINUTES} minutes.", code="too_short", details={"field": "end_time"})
    if end > now + timedelta(minutes=5):
        raise BadRequestError(
            "Time can be logged once it has happened, not ahead of time.",
            code="future_time",
            details={"field": "end_time"},
        )
    utc = ZoneInfo("UTC")
    return start.astimezone(utc), end.astimezone(utc)


class TimeClaimService:
    def __init__(
        self,
        *,
        claims: TimeClaimRepository,
        companies: CompanyRepository,
        employees: EmployeeRepository,
        scopes: AccessScopeService,
        notifier: Notifier,
        audit: AuditService,
    ) -> None:
        self._claims = claims
        self._companies = companies
        self._employees = employees
        self._scopes = scopes
        self._notifier = notifier
        self._audit = audit

    async def _company(self, principal: Principal) -> tuple[ZoneInfo, int, str]:
        company = await self._companies.get_by_id(principal.company_id)
        tz_name = company.timezone if company else "UTC"
        return ZoneInfo(tz_name), (company.time_claim_auto_minutes if company else 120), tz_name

    # ------------------------------------------------------------------ helpers
    async def _visible_ids(self, principal: Principal) -> set[ObjectId] | None:
        """Employees the viewer can see; None = everyone (administrators)."""
        scope = await self._scopes.employee_scope(principal)
        if scope.unrestricted:
            return None
        found = await self._employees.find_many(principal.company_id, scope.filter, sort=None, limit=5000)
        return {e.id for e in found}

    @staticmethod
    def _may_review(principal: Principal, claim: TimeClaim, visible: set[ObjectId] | None) -> bool:
        if not principal.has(Permission.TIME_CLAIM_MANAGE):
            return False
        if claim.user_id == principal.user_id and principal.role not in ADMIN_ROLES:
            return False
        return visible is None or claim.employee_id in visible

    @classmethod
    def _may_delete(cls, principal: Principal, claim: TimeClaim, visible: set[ObjectId] | None) -> bool:
        """The owner, until a manager has reviewed it; or anyone who may review it (a manager of that person)."""
        own_unreviewed = claim.user_id == principal.user_id and claim.reviewed_by is None
        return own_unreviewed or cls._may_review(principal, claim, visible)

    @classmethod
    def _may_edit(cls, principal: Principal, claim: TimeClaim, visible: set[ObjectId] | None) -> bool:
        """Their manager; or the person themselves, while nobody has reviewed it and they logged it."""
        own = claim.user_id == principal.user_id and claim.reviewed_by is None and claim.added_by is None
        return own or cls._may_review(principal, claim, visible)

    def _out(self, principal: Principal, claim: TimeClaim, visible: set[ObjectId] | None) -> TimeClaimOut:
        return TimeClaimOut(
            id=str(claim.id),
            employee=Ref(id=str(claim.employee_id), name=claim.employee_name),
            day=date.fromisoformat(claim.day),
            started_at=claim.started_at,
            ended_at=claim.ended_at,
            minutes=_minutes(claim),
            kind=claim.kind,
            with_whom=claim.with_whom,
            note=claim.note,
            status=claim.status,
            auto_approved=claim.auto_approved,
            reviewed_by=claim.reviewed_by_name,
            added_by=claim.added_by_name,
            reviewed_at=claim.reviewed_at,
            review_note=claim.review_note,
            created_at=claim.created_at,
            can_review=self._may_review(principal, claim, visible),
            can_delete=self._may_delete(principal, claim, visible),
            can_edit=self._may_edit(principal, claim, visible),
        )

    @staticmethod
    def _describe(claim: TimeClaim, tz: ZoneInfo) -> str:
        start, end = claim.started_at.astimezone(tz), claim.ended_at.astimezone(tz)
        when = f"{start:%d %b}, {start:%H:%M}–{end:%H:%M}"  # noqa: RUF001 - shown to people
        text = f"{KIND_LABELS[claim.kind]} with {claim.with_whom} · {when}"
        return f"{text} · {claim.note}" if claim.note else text

    # ------------------------------------------------------------------ create
    async def create(self, principal: Principal, data: TimeClaimCreate, meta: RequestMeta) -> TimeClaimOut:
        employee_id = principal.user.employee_id
        employee = await self._employees.get_by_id(principal.company_id, employee_id) if employee_id else None
        if employee is None:
            raise ForbiddenError(
                "Only people with an employee record can log time.", code="no_employee_record"
            )
        tz, auto_minutes, _ = await self._company(principal)
        start, end = claim_window(
            tz, data.day, data.start_time, data.end_time, days_back=MAX_DAYS_BACK, now=utcnow()
        )

        day_key = data.day.isoformat()
        same_day = await self._claims.for_day(principal.company_id, employee.id, day_key)
        if any(overlaps(start, end, c.started_at, c.ended_at) for c in same_day):
            raise ConflictError(
                "This overlaps time you already logged that day.",
                code="overlap",
                details={"field": "start_time"},
            )
        minutes = round((end - start).total_seconds() / 60)
        used = sum(_minutes(c) for c in same_day)
        within_limit = used + minutes <= auto_minutes
        claim = TimeClaim(
            company_id=principal.company_id,
            employee_id=employee.id,
            employee_name=employee.full_name,
            user_id=principal.user_id,
            day=day_key,
            started_at=start,
            ended_at=end,
            kind=data.kind,
            with_whom=data.with_whom,
            note=data.note,
            status=TimeClaimStatus.APPROVED if within_limit else TimeClaimStatus.PENDING,
            auto_approved=within_limit,
        )
        await self._claims.create(principal.company_id, claim)
        await self._audit.record(
            "time_claim.created",
            company_id=principal.company_id,
            actor_user_id=principal.user_id,
            target_type="time_claim",
            target_id=str(claim.id),
            subject_employee_id=employee.id,
            meta=meta,
            metadata={
                "day": day_key,
                "minutes": minutes,
                "kind": data.kind.value,
                "status": claim.status.value,
            },
        )
        title = (
            f"{employee.full_name} logged {_hours(minutes)} away from the computer"
            if within_limit
            else f"{employee.full_name} asks you to approve {_hours(minutes)} away from the computer"
        )
        self._notifier.emit(
            AlertEvent(
                company_id=principal.company_id,
                type=NotificationType.TIME_CLAIM_LOGGED,
                severity=Severity.INFO if within_limit else Severity.WARNING,
                title=title,
                body=self._describe(claim, tz),
                employee_id=employee.id,
                link="/time-claims",
                subject=f"time-claim:{claim.id}",
                permission=Permission.TIME_CLAIM_MANAGE,
                exclude_user_ids=[principal.user_id],
            )
        )
        visible = await self._visible_ids(principal)
        return self._out(principal, claim, visible)

    # ------------------------------------------------------------------ list
    async def list(
        self,
        principal: Principal,
        *,
        status: TimeClaimStatus | None,
        employee_id: str | None,
        mine: bool,
        page: int,
        page_size: int,
    ) -> TimeClaimPage:
        _, auto_minutes, tz_name = await self._company(principal)
        visible = await self._visible_ids(principal)
        clauses: list[dict[str, Any]] = []
        if mine or not principal.has(Permission.TIME_CLAIM_MANAGE):
            clauses.append({"user_id": principal.user_id})
        elif visible is not None:
            clauses.append({"employee_id": {"$in": sorted(visible)}})
        if person := parse_ref(employee_id, "employee_id"):
            clauses.append({"employee_id": person})
        if status:
            clauses.append({"status": status})
        query: dict[str, Any] = {"$and": clauses} if clauses else {}
        items, total = await self._claims.search(
            principal.company_id, query, (page - 1) * page_size, page_size
        )
        return TimeClaimPage(
            items=[self._out(principal, c, visible) for c in items],
            total=total,
            pending_for_me=await self._pending_for(principal, visible),
            auto_minutes=auto_minutes,
            timezone=tz_name,
        )

    async def _pending_for(self, principal: Principal, visible: set[ObjectId] | None) -> int:
        if not principal.has(Permission.TIME_CLAIM_MANAGE):
            return 0
        query: dict[str, Any] = {"status": TimeClaimStatus.PENDING}
        if visible is not None:
            query["employee_id"] = {"$in": sorted(visible)}
        if principal.role not in ADMIN_ROLES:
            query["user_id"] = {"$ne": principal.user_id}
        return await self._claims.count(principal.company_id, query)

    async def pending_count(self, principal: Principal) -> int:
        return await self._pending_for(principal, await self._visible_ids(principal))

    # ------------------------------------------------------------------ review / delete
    async def _get(self, principal: Principal, claim_id: str) -> TimeClaim:
        claim = await self._claims.get_by_id(
            principal.company_id, parse_id(claim_id, not_found="Time claim not found.")
        )
        if claim is None:
            raise NotFoundError("Time claim not found.")
        return claim

    async def review(
        self, principal: Principal, claim_id: str, data: TimeClaimReview, meta: RequestMeta
    ) -> TimeClaimOut:
        claim = await self._get(principal, claim_id)
        visible = await self._visible_ids(principal)
        if claim.user_id != principal.user_id and visible is not None and claim.employee_id not in visible:
            raise NotFoundError("Time claim not found.")
        if not self._may_review(principal, claim, visible):
            raise ForbiddenError("You can't approve or reject this time.", code="insufficient_permissions")
        target = TimeClaimStatus.APPROVED if data.decision == "approve" else TimeClaimStatus.REJECTED
        if target == TimeClaimStatus.APPROVED and claim.status != TimeClaimStatus.APPROVED:
            others = await self._claims.for_day(principal.company_id, claim.employee_id, claim.day)
            if any(
                o.id != claim.id and overlaps(claim.started_at, claim.ended_at, o.started_at, o.ended_at)
                for o in others
            ):
                raise ConflictError("This overlaps other time logged that day.", code="overlap")
        updated = await self._claims.update_status(
            principal.company_id,
            claim.id,
            {
                "status": target,
                "reviewed_by": principal.user_id,
                "reviewed_by_name": principal.user.full_name,
                "reviewed_at": utcnow(),
                "review_note": (data.note or "").strip() or None,
            },
        )
        assert updated is not None
        await self._audit.record(
            f"time_claim.{'approved' if target == TimeClaimStatus.APPROVED else 'rejected'}",
            company_id=principal.company_id,
            actor_user_id=principal.user_id,
            target_type="time_claim",
            target_id=str(claim.id),
            subject_employee_id=claim.employee_id,
            meta=meta,
            metadata={"day": claim.day, "minutes": _minutes(claim), "from": claim.status.value},
        )
        if claim.user_id != principal.user_id:
            tz, _, _ = await self._company(principal)
            verb = "approved" if target == TimeClaimStatus.APPROVED else "rejected"
            body = self._describe(updated, tz)
            if updated.review_note:
                body += f" · “{updated.review_note}”"
            self._notifier.emit(
                AlertEvent(
                    company_id=principal.company_id,
                    type=NotificationType.TIME_CLAIM_REVIEWED,
                    severity=Severity.INFO if target == TimeClaimStatus.APPROVED else Severity.WARNING,
                    title=f"{principal.user.full_name} {verb} your {_hours(_minutes(claim))} of logged time",
                    body=body,
                    employee_id=claim.employee_id,
                    link="/time-claims",
                    subject=f"time-claim-review:{claim.id}",
                    user_ids=[claim.user_id],
                )
            )
        return self._out(principal, updated, visible)

    async def edit(
        self, principal: Principal, claim_id: str, data: TimeClaimEdit, meta: RequestMeta
    ) -> TimeClaimOut:
        """Change a claim's date, time, type, who with or note (its manager, or its owner before review)."""
        claim = await self._get(principal, claim_id)
        visible = await self._visible_ids(principal)
        own = claim.user_id == principal.user_id
        if not own and visible is not None and claim.employee_id not in visible:
            raise NotFoundError("Time claim not found.")
        if not self._may_edit(principal, claim, visible):
            raise ForbiddenError("You can't change this time.", code="insufficient_permissions")
        manager = self._may_review(principal, claim, visible)
        tz, auto_minutes, _ = await self._company(principal)
        old_start, old_end = claim.started_at.astimezone(tz), claim.ended_at.astimezone(tz)
        day = data.day or date.fromisoformat(claim.day)
        start, end = claim_window(
            tz,
            day,
            data.start_time or f"{old_start:%H:%M}",
            data.end_time or f"{old_end:%H:%M}",
            days_back=MANAGER_DAYS_BACK if manager else MAX_DAYS_BACK,
            now=utcnow(),
        )
        others = [
            c for c in await self._claims.for_day(principal.company_id, claim.employee_id, day.isoformat())
            if c.id != claim.id
        ]
        if any(overlaps(start, end, c.started_at, c.ended_at) for c in others):
            raise ConflictError(
                "This overlaps other time logged that day.", code="overlap", details={"field": "start_time"}
            )
        changes: dict[str, Any] = {
            "day": day.isoformat(),
            "started_at": start,
            "ended_at": end,
            "kind": data.kind or claim.kind,
            "with_whom": data.with_whom or claim.with_whom,
            "note": data.note.strip() or None if data.note is not None else claim.note,
        }
        if not manager:
            # The person's own change counts against the daily limit again, like a new claim.
            minutes = round((end - start).total_seconds() / 60)
            used = sum(_minutes(c) for c in others)
            within = used + minutes <= auto_minutes
            changes["status"] = TimeClaimStatus.APPROVED if within else TimeClaimStatus.PENDING
            changes["auto_approved"] = within
        updated = await self._claims.update_status(principal.company_id, claim.id, changes)
        assert updated is not None
        await self._audit.record(
            "time_claim.edited",
            company_id=principal.company_id,
            actor_user_id=principal.user_id,
            target_type="time_claim",
            target_id=str(claim.id),
            subject_employee_id=claim.employee_id,
            meta=meta,
            metadata={"from": self._describe(claim, tz), "to": self._describe(updated, tz)},
        )
        if not own:
            self._notifier.emit(
                AlertEvent(
                    company_id=principal.company_id,
                    type=NotificationType.TIME_CLAIM_REVIEWED,
                    severity=Severity.INFO,
                    title=f"{principal.user.full_name} changed your logged time",
                    body=f"Was: {self._describe(claim, tz)} → Now: {self._describe(updated, tz)}",
                    employee_id=claim.employee_id,
                    link="/time-claims",
                    subject=f"time-claim-review:{claim.id}",
                    user_ids=[claim.user_id],
                )
            )
        return self._out(principal, updated, visible)

    async def create_for_team(
        self, principal: Principal, data: TimeClaimTeamCreate, meta: RequestMeta
    ) -> TimeClaimTeamResult:
        """Log one meeting for several of the people this manager manages: one approved claim each."""
        if not principal.has(Permission.TIME_CLAIM_MANAGE):
            raise ForbiddenError("You can't log time for other people.", code="insufficient_permissions")
        tz, _, _ = await self._company(principal)
        start, end = claim_window(
            tz, data.day, data.start_time, data.end_time, days_back=MANAGER_DAYS_BACK, now=utcnow()
        )
        visible = await self._visible_ids(principal)
        ids = []
        for raw in dict.fromkeys(data.employee_ids):
            oid = parse_ref(raw, "employee_ids")
            if oid is not None:
                ids.append(oid)
        employees = await self._employees.find_by_ids(principal.company_id, ids)
        created: list[TimeClaimOut] = []
        skipped: list[TimeClaimSkipped] = []
        now = utcnow()
        for oid in ids:
            employee = employees.get(oid)
            if employee is None or (visible is not None and oid not in visible):
                skipped.append(TimeClaimSkipped(employee=Ref(id=str(oid), name="Unknown"), reason="Not one of your people"))
                continue
            ref = Ref(id=str(employee.id), name=employee.full_name)
            if employee.user_id is None:
                skipped.append(TimeClaimSkipped(employee=ref, reason="Has no WorkPulse account"))
                continue
            same_day = await self._claims.for_day(principal.company_id, employee.id, data.day.isoformat())
            if any(overlaps(start, end, c.started_at, c.ended_at) for c in same_day):
                skipped.append(TimeClaimSkipped(employee=ref, reason="Already has time logged then"))
                continue
            claim = TimeClaim(
                company_id=principal.company_id,
                employee_id=employee.id,
                employee_name=employee.full_name,
                user_id=employee.user_id,
                day=data.day.isoformat(),
                started_at=start,
                ended_at=end,
                kind=data.kind,
                with_whom=data.with_whom,
                note=data.note,
                status=TimeClaimStatus.APPROVED,
                added_by=principal.user_id,
                added_by_name=principal.user.full_name,
                reviewed_by=principal.user_id,
                reviewed_by_name=principal.user.full_name,
                reviewed_at=now,
            )
            await self._claims.create(principal.company_id, claim)
            await self._audit.record(
                "time_claim.added_for_employee",
                company_id=principal.company_id,
                actor_user_id=principal.user_id,
                target_type="time_claim",
                target_id=str(claim.id),
                subject_employee_id=employee.id,
                meta=meta,
                metadata={"day": claim.day, "minutes": _minutes(claim), "kind": data.kind.value},
            )
            if employee.user_id != principal.user_id:
                self._notifier.emit(
                    AlertEvent(
                        company_id=principal.company_id,
                        type=NotificationType.TIME_CLAIM_REVIEWED,
                        severity=Severity.INFO,
                        title=f"{principal.user.full_name} logged {_hours(_minutes(claim))} for you",
                        body=self._describe(claim, tz),
                        employee_id=employee.id,
                        link="/time-claims",
                        subject=f"time-claim-review:{claim.id}",
                        user_ids=[employee.user_id],
                    )
                )
            created.append(self._out(principal, claim, visible))
        return TimeClaimTeamResult(created=created, skipped=skipped)

    async def delete(self, principal: Principal, claim_id: str, meta: RequestMeta) -> None:
        claim = await self._get(principal, claim_id)
        visible = await self._visible_ids(principal)
        own = claim.user_id == principal.user_id
        if not own and visible is not None and claim.employee_id not in visible:
            raise NotFoundError("Time claim not found.")
        if not self._may_delete(principal, claim, visible):
            if own:
                raise ForbiddenError(
                    "A manager has already reviewed this time, so it can't be deleted.", code="already_reviewed"
                )
            raise ForbiddenError("You can't delete this time.", code="insufficient_permissions")
        await self._claims.delete_by_id(principal.company_id, claim.id)
        await self._audit.record(
            "time_claim.deleted",
            company_id=principal.company_id,
            actor_user_id=principal.user_id,
            target_type="time_claim",
            target_id=str(claim.id),
            subject_employee_id=claim.employee_id,
            meta=meta,
            metadata={"day": claim.day, "minutes": _minutes(claim)},
        )
        if not own:
            # The person's logged time disappeared from their attendance: tell them who removed it.
            tz, _, _ = await self._company(principal)
            self._notifier.emit(
                AlertEvent(
                    company_id=principal.company_id,
                    type=NotificationType.TIME_CLAIM_REVIEWED,
                    severity=Severity.WARNING,
                    title=f"{principal.user.full_name} deleted your {_hours(_minutes(claim))} of logged time",
                    body=self._describe(claim, tz),
                    employee_id=claim.employee_id,
                    link="/time-claims",
                    subject=f"time-claim-review:{claim.id}",
                    user_ids=[claim.user_id],
                )
            )
