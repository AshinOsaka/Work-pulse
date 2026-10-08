"""Desktop agent use-cases: device registration, authentication, heartbeat and event intake."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from bson import ObjectId
from bson.errors import InvalidId

from app.auth.permissions import Permission
from app.core.config import Settings
from app.core.exceptions import BadRequestError, ForbiddenError, UnauthorizedError
from app.core.privacy import domain_excluded, is_excluded, is_sensitive, normalise_domain, redact_title
from app.core.security import (
    burn_password_check,
    create_device_token,
    generate_device_secret,
    hash_token,
    normalise_enrollment_code,
    verify_password,
    verify_token_hash,
)
from app.models.activity import ActivitySegment
from app.models.agent import AgentEvent, WorkSession
from app.models.company import Company, CompanyStatus
from app.models.notification import NotificationType
from app.models.organization import Device, DeviceStatus, Employee, EmployeeStatus, PresenceState
from app.models.user import UserStatus
from app.repositories.activity import ActivityDailyRepository, ActivitySegmentRepository, DailyIncrement
from app.repositories.agent import AgentEventRepository, WorkSessionRepository
from app.repositories.company import CompanyRepository
from app.repositories.organization import DeviceRepository, EmployeeRepository
from app.repositories.productivity import WebsiteDailyRepository, WebsiteIncrement
from app.repositories.user import UserRepository
from app.schemas.agent import (
    ActivityPolicyOut,
    ActivitySegmentEvent,
    AgentCompany,
    AgentCredentials,
    AgentEmployee,
    AgentEnrollRequest,
    AgentEventIn,
    AgentIdentity,
    AgentPolicy,
    AgentRegisterRequest,
    AgentTokenRequest,
    AgentTokenResponse,
    DeviceInfo,
    EventBatch,
    EventBatchResult,
    HeartbeatRequest,
    HeartbeatResponse,
    PresenceChangedEvent,
    RejectedEvent,
    SessionStartedEvent,
    SessionStoppedEvent,
)
from app.schemas.live import LivePolicyOut
from app.services import throttle as limits
from app.services.audit_service import AuditService
from app.services.context import RequestMeta
from app.services.notifications.notifier import AlertEvent, Notifier, NullNotifier
from app.services.productivity.day_cache import ProductivityDayRepository, stale_past_days
from app.services.screenshot_service import agent_policy
from app.services.throttle import Throttle
from app.utils.text import normalise_email
from app.utils.time import utcnow

logger = logging.getLogger(__name__)

_INVALID_CREDENTIALS = "Invalid email or password."
_MAX_FUTURE_SKEW = timedelta(minutes=5)
_MAX_EVENT_AGE = timedelta(days=30)


@dataclass(slots=True)
class DeviceContext:
    """The authenticated device for an agent request."""

    device: Device
    employee: Employee
    #: Loaded together with the device when the request is authenticated (saves a round trip).
    company: Company | None = None

    @property
    def company_id(self) -> ObjectId:
        return self.device.company_id


class AgentService:
    def __init__(
        self,
        *,
        settings: Settings,
        users: UserRepository,
        companies: CompanyRepository,
        employees: EmployeeRepository,
        devices: DeviceRepository,
        sessions: WorkSessionRepository,
        events: AgentEventRepository,
        segments: ActivitySegmentRepository,
        daily: ActivityDailyRepository,
        websites: WebsiteDailyRepository,
        audit: AuditService,
        notifier: Notifier | None = None,
        throttle: Throttle | None = None,
    ) -> None:
        self._throttle = throttle
        self._notifier = notifier or NullNotifier()
        self._settings = settings
        self._users = users
        self._companies = companies
        self._employees = employees
        self._devices = devices
        self._sessions = sessions
        self._events = events
        self._segments = segments
        self._daily = daily
        self._websites = websites
        self._audit = audit

    def policy(self, company: Company, employee: Employee) -> AgentPolicy:
        s = self._settings
        activity = company.activity_policy
        return AgentPolicy(
            heartbeat_interval_seconds=s.agent_heartbeat_interval_seconds,
            sync_interval_seconds=s.agent_sync_interval_seconds,
            idle_threshold_seconds=s.agent_idle_threshold_seconds,
            max_batch_size=s.agent_max_batch_size,
            activity=ActivityPolicyOut(
                track_applications=activity.track_applications,
                capture_window_titles=activity.capture_window_titles,
                track_websites=activity.track_websites,
                excluded_apps=activity.excluded_apps,
            ),
            screenshots=agent_policy(company, employee),
            live=LivePolicyOut(**company.live_policy.model_dump()),
        )

    # ------------------------------------------------------------------ registration
    async def register(self, data: AgentRegisterRequest, meta: RequestMeta) -> AgentCredentials:
        """Employee signs in from the agent; the device receives its own long-lived secret.

        The password is used once for this exchange and is never stored by the agent.
        """
        address = normalise_email(data.email)
        if self._throttle:
            await self._throttle.hit(limits.AGENT_SIGN_IN_PER_IP, meta.ip_address)
            await self._throttle.check(limits.AGENT_FAILURES_PER_ACCOUNT, address)
        user = await self._users.find_by_email_for_auth(address)
        if user is None or not verify_password(user.password_hash, data.password):
            if user is None:
                burn_password_check(data.password)
            if self._throttle:
                await self._throttle.fail(limits.AGENT_FAILURES_PER_ACCOUNT, address)
            if user is not None:
                await self._audit.record(
                    "agent.login_failed", company_id=user.company_id, actor_user_id=user.id, meta=meta
                )
            raise UnauthorizedError(_INVALID_CREDENTIALS, code="invalid_credentials")
        if user.status != UserStatus.ACTIVE:
            raise ForbiddenError("This account is not active.", code="account_not_active")
        if user.mfa_enabled:
            # A device credential is long-lived; issuing one on a password alone would bypass the second factor.
            raise ForbiddenError(
                "Two-step verification is on for this account. Ask an administrator for a device enrolment code.",
                code="mfa_enrollment_required",
            )
        company = await self._active_company(user.company_id)
        employee = await self._employees.get_by_id(company.id, user.employee_id) if user.employee_id else None
        if employee is None:
            raise ForbiddenError("This account has no employee record.", code="no_employee_record")
        self._ensure_employee_active(employee)

        secret = generate_device_secret()
        existing = await self._devices.find_for_fingerprint(company.id, employee.id, data.device.fingerprint)
        if existing:
            device = await self._devices.update_by_id(
                company.id, existing.id, self._device_fields(data.device, secret, meta, existing)
            )
            assert device is not None
        else:
            device = Device(
                company_id=company.id,
                employee_id=employee.id,
                **self._device_fields(data.device, secret, meta, None),
            )
            await self._devices.create(company.id, device)

        await self._audit.record(
            "device.enrolled",
            company_id=company.id,
            actor_user_id=user.id,
            target_type="device",
            target_id=str(device.id),
            subject_employee_id=employee.id,
            meta=meta,
            metadata={"method": "sign_in", "os": data.device.os.value},
        )
        return AgentCredentials(
            **self._identity(device, employee, company).model_dump(), device_secret=secret
        )

    async def enroll(self, data: AgentEnrollRequest, meta: RequestMeta) -> AgentCredentials:
        """Redeem an admin-issued one-time enrolment code (for managed / silent installs)."""
        if self._throttle:
            await self._throttle.hit(limits.AGENT_SIGN_IN_PER_IP, meta.ip_address)
        invalid = BadRequestError(
            "This enrolment code is invalid or has expired.", code="invalid_enrollment_code"
        )
        pending = await self._devices.find_by_enrollment_hash(
            hash_token(normalise_enrollment_code(data.enrollment_code))
        )
        if pending is None or (pending.enrollment_expires_at and pending.enrollment_expires_at < utcnow()):
            raise invalid
        company = await self._active_company(pending.company_id)
        employee = await self._employees.get_by_id(company.id, pending.employee_id)
        if employee is None:
            raise invalid
        self._ensure_employee_active(employee)

        secret = generate_device_secret()
        fields = self._device_fields(data.device, secret, meta, pending)
        fields["name"] = pending.name  # keep the admin-chosen name
        fields.update(enrollment_code_hash=None, enrollment_expires_at=None)
        device = await self._devices.update_by_id(company.id, pending.id, fields)
        assert device is not None
        await self._audit.record(
            "device.enrolled",
            company_id=company.id,
            actor_user_id=employee.user_id,
            target_type="device",
            target_id=str(device.id),
            subject_employee_id=employee.id,
            meta=meta,
            metadata={"method": "enrollment_code", "os": data.device.os.value},
        )
        return AgentCredentials(
            **self._identity(device, employee, company).model_dump(), device_secret=secret
        )

    @staticmethod
    def _device_fields(
        info: DeviceInfo, secret: str, meta: RequestMeta, existing: Device | None
    ) -> dict[str, Any]:
        now = utcnow()
        return {
            "name": info.name,
            "hostname": info.hostname,
            "os": info.os,
            "os_version": info.os_version,
            "agent_version": info.agent_version,
            "fingerprint_hash": info.fingerprint,
            "secret_hash": hash_token(secret),
            "status": DeviceStatus.ACTIVE,
            "enrolled_at": existing.enrolled_at if existing and existing.enrolled_at else now,
            "last_seen_at": now,
            "last_ip": meta.ip_address,
            "revoked_at": None,
        }

    # ------------------------------------------------------------------ authentication
    async def issue_token(self, data: AgentTokenRequest) -> AgentTokenResponse:
        invalid = UnauthorizedError(
            "Device credentials are invalid or revoked.", code="invalid_device_credentials"
        )
        try:
            device_id = ObjectId(data.device_id)
        except (InvalidId, TypeError) as exc:
            raise invalid from exc
        device = await self._devices.get_for_auth(device_id)
        if device is None or not verify_token_hash(data.device_secret, device.secret_hash):
            raise invalid
        if device.status != DeviceStatus.ACTIVE:
            raise invalid
        company = await self._active_company(device.company_id)
        employee = await self._employees.get_by_id(company.id, device.employee_id)
        if employee is None:
            raise invalid
        self._ensure_employee_active(employee)

        token, expires_at = create_device_token(
            device_id=str(device.id),
            company_id=str(company.id),
            employee_id=str(employee.id),
            settings=self._settings,
        )
        return AgentTokenResponse(
            **self._identity(device, employee, company).model_dump(),
            access_token=token,
            expires_in=int((expires_at - utcnow()).total_seconds()),
        )

    async def identity(self, ctx: DeviceContext) -> AgentIdentity:
        company = await self._active_company(ctx.company_id)
        return self._identity(ctx.device, ctx.employee, company)

    # ------------------------------------------------------------------ heartbeat
    async def heartbeat(
        self, ctx: DeviceContext, data: HeartbeatRequest, meta: RequestMeta
    ) -> HeartbeatResponse:
        now = utcnow()
        device = ctx.device
        company = await self._context_company(ctx)
        presence = PresenceState(data.presence) if data.presence else None
        current_app = data.current_app if presence and company.activity_policy.track_applications else None
        if current_app and is_excluded("", current_app, company.activity_policy.excluded_apps):
            current_app = None
        changes: dict[str, Any] = {
            "last_seen_at": now,
            "agent_stopped_at": None,
            "agent_version": data.agent_version,
            "last_ip": meta.ip_address,
            "presence": presence,
            "current_session_id": str(data.session_id) if data.session_id and presence else None,
        }
        if presence != device.presence or device.presence_since is None:
            changes["presence_since"] = now
        if current_app != device.current_app:
            changes.update(current_app=current_app, current_app_since=now if current_app else None)
        await self._devices.set_fields(ctx.company_id, device.id, changes)
        return HeartbeatResponse(
            server_time=now,
            device_status=device.status,
            policy=self.policy(company, ctx.employee),
        )

    # ------------------------------------------------------------------ events
    async def ingest(self, ctx: DeviceContext, batch: EventBatch) -> EventBatchResult:
        """Idempotent: re-sending an event (same client id) is acknowledged as a duplicate."""
        now = utcnow()
        accepted = duplicates = 0
        rejected: list[RejectedEvent] = []
        segments: list[ActivitySegmentEvent] = []
        applied_at: list[datetime] = []
        for event in sorted(batch.events, key=lambda e: e.occurred_at):
            if event.occurred_at > now + _MAX_FUTURE_SKEW or event.occurred_at < now - _MAX_EVENT_AGE:
                rejected.append(RejectedEvent(id=str(event.id), reason="occurred_at_out_of_range"))
                continue
            if isinstance(event, ActivitySegmentEvent):
                segments.append(event)  # high-volume: written in bulk below
                continue
            record = AgentEvent(
                company_id=ctx.company_id,
                employee_id=ctx.employee.id,
                device_id=ctx.device.id,
                event_id=str(event.id),
                type=event.type,
                occurred_at=event.occurred_at,
                payload=event.model_dump(mode="json", exclude={"id", "type", "occurred_at"}),
            )
            if not await self._events.record(record):
                duplicates += 1
                continue
            accepted += 1
            await self._apply(ctx, event)
            applied_at.append(event.occurred_at)
        if applied_at and min(applied_at) < now - timedelta(hours=1):
            await self._invalidate_settled_days(ctx, applied_at)
        if segments:
            new, repeated, refused = await self._ingest_segments(ctx, segments)
            accepted += new
            duplicates += repeated
            rejected.extend(refused)
        return EventBatchResult(accepted=accepted, duplicates=duplicates, rejected=rejected)

    async def _invalidate_settled_days(self, ctx: DeviceContext, moments: list[datetime]) -> None:
        """Session events uploaded late (offline queue) can change a past day's time accounting."""
        company = await self._context_company(ctx)
        tz = ZoneInfo(company.timezone)
        late = stale_past_days(
            {m.astimezone(tz).date().isoformat() for m in moments}, utcnow().astimezone(tz).date()
        )
        if late:
            await ProductivityDayRepository(self._daily._db).invalidate(ctx.company_id, ctx.employee.id, late)

    async def _ingest_segments(
        self, ctx: DeviceContext, events: list[ActivitySegmentEvent]
    ) -> tuple[int, int, list[RejectedEvent]]:
        """One insert_many + one bulk upsert per batch, whatever its size."""
        company = await self._context_company(ctx)
        policy = company.activity_policy
        tz = ZoneInfo(company.timezone)
        refused: list[RejectedEvent] = []
        rows: list[ActivitySegment] = []
        for event in events:
            if not policy.track_applications:
                refused.append(RejectedEvent(id=str(event.id), reason="tracking_disabled"))
                continue
            if is_excluded(event.app_id, event.app_name, policy.excluded_apps):
                refused.append(RejectedEvent(id=str(event.id), reason="excluded_application"))
                continue
            # Defence in depth: the server re-applies the title policy, whatever the agent sent.
            title = None
            if policy.capture_window_titles and not is_sensitive(event.app_id, event.window_title):
                title = redact_title(event.window_title)
            domain = None
            if policy.track_websites and event.domain:
                domain = normalise_domain(event.domain)
                if domain and domain_excluded(domain, policy.excluded_apps):
                    domain = None
            duration = max(0, round((event.ended_at - event.started_at).total_seconds()))
            rows.append(
                ActivitySegment(
                    company_id=ctx.company_id,
                    employee_id=ctx.employee.id,
                    device_id=ctx.device.id,
                    event_id=str(event.id),
                    session_id=str(event.session_id),
                    app_id=event.app_id.lower(),
                    app_name=event.app_name.strip(),
                    window_title=title,
                    domain=domain,
                    started_at=event.started_at,
                    ended_at=event.ended_at,
                    duration_seconds=duration,
                    active_seconds=min(event.active_seconds, duration),
                    activity_level=event.activity_level,
                )
            )
        inserted = await self._segments.insert_batch(rows)
        fresh = [row for row in rows if row.event_id in inserted]
        pieces = [(row, piece) for row in fresh for piece in split_by_local_day(row, tz)]
        await self._daily.increment([piece for _, piece in pieces])
        await self._websites.increment(
            [
                WebsiteIncrement(
                    p.company_id, p.employee_id, p.day, p.app_id, row.domain, p.seconds, p.active_seconds
                )
                for row, p in pieces
                if row.domain
            ]
        )
        # Late uploads (the agent's offline queue) change past days: drop their cached analysis.
        late = stale_past_days({p.day.isoformat() for _, p in pieces}, utcnow().astimezone(tz).date())
        if late:
            await ProductivityDayRepository(self._daily._db).invalidate(ctx.company_id, ctx.employee.id, late)
        return len(inserted), len(rows) - len(inserted), refused

    async def _shift_event(
        self, ctx: DeviceContext, occurred_at: datetime, *, started: bool, minutes: int = 0
    ) -> None:
        """Shift alerts come from work sessions. Events uploaded late from the offline queue stay silent."""
        at = occurred_at if occurred_at.tzinfo else occurred_at.replace(tzinfo=UTC)
        if utcnow() - at > timedelta(seconds=self._settings.alert_event_freshness_seconds):
            return
        company = await self._companies.get_by_id(ctx.company_id)
        tz = ZoneInfo(company.timezone) if company else ZoneInfo("UTC")
        local = at.astimezone(tz)
        if started:
            event = AlertEvent(
                company_id=ctx.company_id,
                type=NotificationType.SHIFT_STARTED,
                title="{employee} started work",
                body=f"First work session of the day started at {local.strftime('%H:%M')} on {ctx.device.name}.",
                employee_id=ctx.employee.id,
                link=f"/people/employees/{ctx.employee.id}",
                dedupe_key=f"shift-start:{ctx.employee.id}:{local.date().isoformat()}",
                permission=Permission.ACTIVITY_VIEW,
            )
        else:
            event = AlertEvent(
                company_id=ctx.company_id,
                type=NotificationType.SHIFT_ENDED,
                title="{employee} stopped work",
                body=f"A work session of {minutes // 60}h {minutes % 60:02d}m ended at {local.strftime('%H:%M')} "
                f"on {ctx.device.name}.",
                employee_id=ctx.employee.id,
                link=f"/people/employees/{ctx.employee.id}",
                permission=Permission.ACTIVITY_VIEW,
            )
        self._notifier.emit(event)

    async def _apply(self, ctx: DeviceContext, event: AgentEventIn) -> None:
        company_id, device = ctx.company_id, ctx.device
        if isinstance(event, SessionStartedEvent):
            session_id = str(event.session_id)
            opened = await self._sessions.open_session(
                WorkSession(
                    company_id=company_id,
                    employee_id=ctx.employee.id,
                    device_id=device.id,
                    client_session_id=session_id,
                    started_at=event.occurred_at,
                )
            )
            if opened:
                await self._update_device(
                    ctx,
                    {
                        "current_session_id": session_id,
                        "presence": PresenceState.ACTIVE,
                        "presence_since": event.occurred_at,
                    },
                )
                await self._record_work("work.session_started", ctx, session_id, {}, event.occurred_at)
                await self._shift_event(ctx, event.occurred_at, started=True)
        elif isinstance(event, SessionStoppedEvent):
            session_id = str(event.session_id)
            changes = {
                "ended_at": event.occurred_at,
                "end_reason": event.reason,
                "active_seconds": event.active_seconds,
                "idle_seconds": event.idle_seconds,
            }
            closed = await self._sessions.close_session(company_id, device.id, session_id, changes)
            if (
                closed is None
                and await self._sessions.get_by_client_id(company_id, device.id, session_id) is None
            ):
                # The start event was lost: reconstruct the session from the reported durations.
                started = event.occurred_at - timedelta(seconds=event.active_seconds + event.idle_seconds)
                await self._sessions.open_session(
                    WorkSession(
                        company_id=company_id,
                        employee_id=ctx.employee.id,
                        device_id=device.id,
                        client_session_id=session_id,
                        started_at=started,
                        **changes,
                    )
                )
            if device.current_session_id == session_id:
                await self._update_device(
                    ctx, {"current_session_id": None, "presence": None, "presence_since": event.occurred_at}
                )
            minutes = (event.active_seconds + event.idle_seconds) // 60
            await self._record_work(
                "work.session_stopped", ctx, session_id, {"duration_minutes": minutes}, event.occurred_at
            )
            await self._shift_event(ctx, event.occurred_at, started=False, minutes=minutes)
        elif isinstance(event, PresenceChangedEvent):
            await self._sessions.record_presence(
                company_id, device.id, str(event.session_id), event.occurred_at, event.status
            )
            is_current = device.current_session_id == str(event.session_id)
            newer = device.presence_since is None or event.occurred_at >= device.presence_since
            if is_current and newer:
                await self._update_device(
                    ctx, {"presence": PresenceState(event.status), "presence_since": event.occurred_at}
                )
        elif event.type == "agent.stopped":
            await self._update_device(
                ctx, {"presence": None, "current_session_id": None, "agent_stopped_at": event.occurred_at}
            )

    async def _update_device(self, ctx: DeviceContext, changes: dict[str, Any]) -> None:
        updated = await self._devices.update_by_id(ctx.company_id, ctx.device.id, changes)
        if updated:
            ctx.device = updated

    async def _record_work(
        self,
        action: str,
        ctx: DeviceContext,
        session_id: str,
        metadata: dict[str, Any],
        occurred_at: datetime,
    ) -> None:
        await self._audit.record(
            action,
            company_id=ctx.company_id,
            actor_user_id=ctx.employee.user_id,
            target_type="work_session",
            target_id=session_id,
            subject_employee_id=ctx.employee.id,
            metadata=metadata,
            occurred_at=occurred_at,
        )

    # ------------------------------------------------------------------ helpers
    async def _context_company(self, ctx: DeviceContext) -> Company:
        """The device's workspace, as loaded during authentication when available."""
        company = ctx.company
        if company is None:
            company = await self._active_company(ctx.company_id)
            ctx.company = company
        elif company.status == CompanyStatus.SUSPENDED:
            raise ForbiddenError("This workspace has been suspended.", code="company_suspended")
        return company

    async def _active_company(self, company_id: ObjectId) -> Company:
        company = await self._companies.get_by_id(company_id)
        if company is None:
            raise UnauthorizedError("Workspace no longer exists.", code="company_not_found")
        if company.status == CompanyStatus.SUSPENDED:
            raise ForbiddenError("This workspace has been suspended.", code="company_suspended")
        return company

    @staticmethod
    def _ensure_employee_active(employee: Employee) -> None:
        if employee.status == EmployeeStatus.TERMINATED:
            raise ForbiddenError("This employee is no longer active.", code="employee_terminated")

    def _identity(self, device: Device, employee: Employee, company: Company) -> AgentIdentity:
        return AgentIdentity(
            device_id=str(device.id),
            employee=AgentEmployee(id=str(employee.id), full_name=employee.full_name, email=employee.email),
            company=AgentCompany(id=str(company.id), name=company.name),
            policy=self.policy(company, employee),
        )


def split_by_local_day(segment: ActivitySegment, tz: ZoneInfo) -> list[DailyIncrement]:
    """Attribute a segment to company-local days, splitting it at midnight proportionally."""
    total = (segment.ended_at - segment.started_at).total_seconds()
    pieces: list[DailyIncrement] = []
    cursor = segment.started_at.astimezone(tz)
    end = segment.ended_at.astimezone(tz)
    while True:
        next_midnight = datetime.combine(cursor.date() + timedelta(days=1), time.min, tzinfo=tz)
        piece_end = min(end, next_midnight)
        seconds = (piece_end - cursor).total_seconds()
        if seconds > 0 or total == 0:
            share = seconds / total if total else 1.0
            pieces.append(
                DailyIncrement(
                    company_id=segment.company_id,
                    employee_id=segment.employee_id,
                    day=cursor.date(),
                    app_id=segment.app_id,
                    app_name=segment.app_name,
                    seconds=seconds if total else 0.0,
                    active_seconds=segment.active_seconds * share,
                )
            )
        if piece_end >= end:
            return pieces
        cursor = piece_end
