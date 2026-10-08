"""Screenshot monitoring: policy, agent uploads, the manager gallery, private file access and retention.

Security model:
* Only users with SCREENSHOT_VIEW see screenshots, and only for employees in their access scope.
  Out-of-scope and foreign-tenant ids return 404.
* Images are never public. The API issues short-lived URLs bound to the viewer (see `core.signed_urls`),
  and every file fetch re-checks the signature, the viewer's account and permission, and the scope.
* Every access is audited: each gallery page (with the ids shown), each full-size view, and each deletion.
* An upload is stored only when the employee's effective policy allows a capture at that moment and
  a work session is known for the device.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.auth.permissions import Permission, permissions_for_role
from app.auth.principal import Principal
from app.core.config import Settings
from app.core.exceptions import BadRequestError, ConflictError, ForbiddenError, NotFoundError
from app.core.images import InvalidImageError, process_screenshot
from app.core.object_storage import ObjectNotFoundError, ObjectStorage
from app.core.signed_urls import UrlSigner
from app.models.company import Company
from app.models.live import LiveStatus
from app.models.notification import NotificationType
from app.models.organization import Employee, PresenceState, ScreenshotMode, ScreenshotOverride
from app.models.screenshot import Screenshot
from app.models.user import UserStatus
from app.repositories.activity import ActivitySegmentRepository
from app.repositories.agent import WorkSessionRepository
from app.repositories.company import CompanyRepository
from app.repositories.live import LiveSessionRepository
from app.repositories.organization import DeviceRepository, EmployeeRepository
from app.repositories.screenshot import ScreenshotRepository
from app.repositories.user import UserRepository
from app.schemas.screenshots import (
    AgentScreenshotPolicy,
    EffectiveScreenshotPolicyOut,
    EmployeeScreenshotSettings,
    EmployeeScreenshotSettingsUpdate,
    MonitoringScreenshots,
    MonitoringStatus,
    ScreenshotDetail,
    ScreenshotItem,
    ScreenshotPage,
    ScreenshotPolicyOut,
    ScreenshotPolicyUpdate,
    ScreenshotPolicyValidated,
    ScreenshotTimeline,
    ScreenshotUploadResult,
    TimelineBucket,
    TimelineCapture,
)
from app.services.access_scope import AccessScopeService
from app.services.audit_service import AuditService
from app.services.context import RequestMeta
from app.services.employee_service import employee_ref
from app.services.helpers import parse_id, parse_ref
from app.services.notifications.notifier import AlertEvent, Notifier, NullNotifier
from app.services.retention import purge_expired_screenshots
from app.services.screenshot_policy import EffectiveScreenshotPolicy, capture_allowed, effective_policy
from app.utils.time import utcnow

logger = logging.getLogger(__name__)

PAGE_LIMIT_MAX = 60
TIMELINE_CAPTURES_MAX = 2000
MIN_SECONDS_BETWEEN_CAPTURES = 10
MAX_UPLOAD_AGE = timedelta(days=7)
MAX_FUTURE_SKEW = timedelta(minutes=5)
SESSION_GRACE = timedelta(minutes=2)
VARIANTS = ("full", "thumb")
_NOT_FOUND = "Screenshot not found."


def policy_out(company: Company) -> ScreenshotPolicyOut:
    return ScreenshotPolicyOut(**company.screenshot_policy.model_dump())


def effective_out(policy: EffectiveScreenshotPolicy) -> EffectiveScreenshotPolicyOut:
    return EffectiveScreenshotPolicyOut(
        enabled=policy.enabled,
        interval_minutes=policy.interval_minutes,
        work_hours_only=policy.work_hours_only,
        work_start=policy.work_start,
        work_end=policy.work_end,
        work_days=list(policy.work_days),
        retention_days=policy.retention_days,
        timezone=policy.timezone,
        source="employee" if policy.source == "employee" else "workspace",
    )


def agent_policy(company: Company, employee: Employee) -> AgentScreenshotPolicy:
    policy = effective_policy(company, employee)
    return AgentScreenshotPolicy(
        enabled=policy.enabled,
        interval_seconds=policy.interval_minutes * 60,
        work_hours_only=policy.work_hours_only,
        work_start=policy.work_start,
        work_end=policy.work_end,
        work_days=list(policy.work_days),
        timezone=policy.timezone,
    )


def object_keys(
    company_id: ObjectId, employee_id: ObjectId, captured_at: datetime, shot_id: ObjectId
) -> tuple[str, str]:
    prefix = f"screenshots/{company_id}/{employee_id}/{captured_at:%Y/%m/%d}/{shot_id}"
    return f"{prefix}.webp", f"{prefix}_thumb.webp"


class ScreenshotService:
    def __init__(
        self,
        *,
        settings: Settings,
        companies: CompanyRepository,
        employees: EmployeeRepository,
        devices: DeviceRepository,
        users: UserRepository,
        sessions: WorkSessionRepository,
        segments: ActivitySegmentRepository,
        screenshots: ScreenshotRepository,
        scopes: AccessScopeService,
        audit: AuditService,
        storage: ObjectStorage,
        signer: UrlSigner,
        live_sessions: LiveSessionRepository | None = None,
        notifier: Notifier | None = None,
    ) -> None:
        self._notifier = notifier or NullNotifier()
        self._settings = settings
        self._companies = companies
        self._employees = employees
        self._devices = devices
        self._users = users
        self._sessions = sessions
        self._segments = segments
        self._screenshots = screenshots
        self._scopes = scopes
        self._audit = audit
        self._storage = storage
        self._signer = signer
        self._live = live_sessions

    async def _company(self, company_id: ObjectId) -> Company:
        company = await self._companies.get_by_id(company_id)
        if company is None:
            raise NotFoundError("Workspace not found.")
        return company

    # ------------------------------------------------------------------ workspace policy
    async def get_policy(self, principal: Principal) -> ScreenshotPolicyOut:
        """Every member may read it: employees can always see how they are monitored."""
        return policy_out(await self._company(principal.company_id))

    async def update_policy(
        self, principal: Principal, data: ScreenshotPolicyUpdate, meta: RequestMeta
    ) -> ScreenshotPolicyOut:
        company = await self._company(principal.company_id)
        changes = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}
        if not changes:
            return policy_out(company)
        merged = company.screenshot_policy.model_copy(update=changes)
        try:
            ScreenshotPolicyValidated(**merged.model_dump())
        except ValueError as exc:
            raise BadRequestError(
                "Working hours must start and end at different times.", code="invalid_work_hours"
            ) from exc
        updated = await self._companies.update_by_id(company.id, {"screenshot_policy": merged.model_dump()})
        if (
            "retention_days" in changes
            and changes["retention_days"] != company.screenshot_policy.retention_days
        ):
            await self._screenshots.reset_expiry(company.id, timedelta(days=merged.retention_days))
        await self._audit.record(
            "policy.screenshots_updated",
            company_id=company.id,
            actor_user_id=principal.user_id,
            target_type="company",
            target_id=str(company.id),
            meta=meta,
            metadata={"fields": sorted(changes), "enabled": merged.enabled},
        )
        if "enabled" in changes and changes["enabled"] != company.screenshot_policy.enabled:
            title = "Screenshot monitoring was turned " + ("on" if merged.enabled else "off")
        else:
            title = "Screenshot settings changed"
        self._notifier.emit(
            AlertEvent(
                company_id=company.id,
                type=NotificationType.SCREENSHOT_POLICY,
                title=title,
                body=f"{principal.user.full_name} updated the workspace screenshot policy "
                f"({', '.join(sorted(changes)).replace('_', ' ')}). Your current monitoring status is always shown "
                "in WorkPulse and on the desktop agent.",
                subject="screenshot-policy",
                everyone=True,
                exclude_user_ids=[principal.user_id],
            )
        )
        return policy_out(updated or company)

    # ------------------------------------------------------------------ per-employee override
    async def _employee_in_scope(self, principal: Principal, employee_id: str) -> Employee:
        oid = parse_id(employee_id, not_found="Employee not found.", code="employee_not_found")
        scope = await self._scopes.employee_scope(principal)
        employee = await self._employees.get_in_scope(principal.company_id, oid, scope.filter)
        if employee is None:
            raise NotFoundError("Employee not found.", code="employee_not_found")
        return employee

    async def employee_settings(self, principal: Principal, employee_id: str) -> EmployeeScreenshotSettings:
        oid = parse_id(employee_id, not_found="Employee not found.", code="employee_not_found")
        is_self = principal.user.employee_id == oid
        if not is_self and not (
            principal.has(Permission.SCREENSHOT_VIEW) or principal.has(Permission.POLICY_MANAGE)
        ):
            raise NotFoundError("Employee not found.", code="employee_not_found")
        employee = await self._employee_in_scope(principal, employee_id)
        company = await self._company(principal.company_id)
        return self._settings_out(company, employee)

    async def update_employee_settings(
        self,
        principal: Principal,
        employee_id: str,
        data: EmployeeScreenshotSettingsUpdate,
        meta: RequestMeta,
    ) -> EmployeeScreenshotSettings:
        employee = await self._employee_in_scope(principal, employee_id)
        override = ScreenshotOverride(
            mode=data.mode,
            interval_minutes=data.interval_minutes if data.mode != ScreenshotMode.DISABLED else None,
        )
        updated = await self._employees.update_by_id(
            principal.company_id, employee.id, {"screenshot_override": override.model_dump()}
        )
        await self._audit.record(
            "employee.screenshot_policy_updated",
            company_id=principal.company_id,
            actor_user_id=principal.user_id,
            target_type="employee",
            target_id=str(employee.id),
            subject_employee_id=employee.id,
            meta=meta,
            metadata={"from": employee.screenshot_override.mode.value, "to": override.mode.value},
        )
        if employee.screenshot_override.mode != override.mode:
            self._notifier.emit(
                AlertEvent(
                    company_id=principal.company_id,
                    type=NotificationType.SCREENSHOT_POLICY,
                    title="Screenshot setting changed for {employee}",
                    body=f"{principal.user.full_name} changed it from "
                    f"“{employee.screenshot_override.mode.value.replace('_', ' ')}” to “{override.mode.value.replace('_', ' ')}”.",
                    employee_id=employee.id,
                    subject=f"screenshot-policy:{employee.id}",
                    include_employee=True,
                    permission=Permission.POLICY_MANAGE,
                    exclude_user_ids=[principal.user_id],
                )
            )
        company = await self._company(principal.company_id)
        return self._settings_out(company, updated or employee)

    @staticmethod
    def _settings_out(company: Company, employee: Employee) -> EmployeeScreenshotSettings:
        return EmployeeScreenshotSettings(
            employee_id=str(employee.id),
            mode=employee.screenshot_override.mode,
            interval_minutes=employee.screenshot_override.interval_minutes,
            effective=effective_out(effective_policy(company, employee)),
        )

    # ------------------------------------------------------------------ transparency
    async def my_monitoring(self, principal: Principal) -> MonitoringStatus:
        company = await self._company(principal.company_id)
        activity = company.activity_policy
        employee_id = principal.user.employee_id
        employee = await self._employees.get_by_id(principal.company_id, employee_id) if employee_id else None
        if employee is None:
            return MonitoringStatus(
                has_employee_record=False,
                agent_connected=False,
                session_active=False,
                track_applications=activity.track_applications,
                capture_window_titles=activity.capture_window_titles,
                screenshots=None,
                monitoring_active=False,
            )
        now = utcnow()
        offline_after = timedelta(seconds=self._settings.agent_offline_after_seconds)
        devices = await self._devices.find_many(
            principal.company_id, {"employee_id": employee.id, "status": "active"}
        )
        connected = [
            d
            for d in devices
            if d.last_seen_at and now - d.last_seen_at <= offline_after and d.agent_stopped_at is None
        ]
        session_active = any(d.current_session_id and d.presence == PresenceState.ACTIVE for d in connected)
        policy = effective_policy(company, employee)
        last = await self._screenshots.last_for_employee(principal.company_id, employee.id)
        in_schedule = capture_allowed(policy, now)
        watching = (
            await self._live.active_for_employee(principal.company_id, employee.id) if self._live else None
        )
        live_viewer = watching.viewer_name if watching and watching.status == LiveStatus.LIVE else None
        return MonitoringStatus(
            has_employee_record=True,
            agent_connected=bool(connected),
            session_active=session_active,
            track_applications=activity.track_applications,
            capture_window_titles=activity.capture_window_titles,
            screenshots=MonitoringScreenshots(
                enabled=policy.enabled,
                interval_minutes=policy.interval_minutes,
                work_hours_only=policy.work_hours_only,
                work_start=policy.work_start,
                work_end=policy.work_end,
                work_days=list(policy.work_days),
                timezone=policy.timezone,
                retention_days=policy.retention_days,
                in_schedule_now=in_schedule,
                last_captured_at=last.captured_at if last else None,
            ),
            monitoring_active=bool(live_viewer)
            or (session_active and (activity.track_applications or in_schedule)),
            live_view_enabled=company.live_policy.enabled,
            live_viewer=live_viewer,
        )

    # ------------------------------------------------------------------ agent upload
    async def upload(
        self,
        *,
        company: Company,
        employee: Employee,
        device_id: ObjectId,
        client_id: str,
        session_id: str,
        captured_at: datetime,
        data: bytes,
    ) -> ScreenshotUploadResult:
        try:
            client_uuid = str(uuid.UUID(client_id))
        except ValueError as exc:
            raise BadRequestError("Invalid screenshot id.", code="invalid_id") from exc
        existing = await self._screenshots.get_by_client_id(company.id, device_id, client_uuid)
        if existing:
            return ScreenshotUploadResult(id=str(existing.id), duplicate=True)

        now = utcnow()
        if captured_at > now + MAX_FUTURE_SKEW or captured_at < now - MAX_UPLOAD_AGE:
            raise BadRequestError("Capture time is out of range.", code="stale_capture")
        policy = effective_policy(company, employee)
        if not policy.enabled:
            raise ForbiddenError("Screenshots are disabled for this employee.", code="screenshots_disabled")
        if not capture_allowed(policy, captured_at):
            raise ForbiddenError("Captured outside working hours.", code="outside_work_hours")
        if captured_at < now - policy.retention:
            raise BadRequestError("Capture is older than the retention period.", code="stale_capture")

        session = await self._sessions.get_by_client_id(company.id, device_id, session_id)
        if session is None:
            # The session.started event may still be queued on the device: retry later.
            raise ConflictError("Unknown work session.", code="unknown_session")
        if captured_at < session.started_at - SESSION_GRACE or (
            session.ended_at is not None and captured_at > session.ended_at + SESSION_GRACE
        ):
            raise ForbiddenError("Captured outside a work session.", code="outside_session")

        last = await self._screenshots.last_for_device(company.id, device_id)
        if last and abs((captured_at - last.captured_at).total_seconds()) < MIN_SECONDS_BETWEEN_CAPTURES:
            raise ForbiddenError("Screenshots are arriving too frequently.", code="too_frequent")

        try:
            image = await asyncio.to_thread(process_screenshot, data)
        except InvalidImageError as exc:
            raise BadRequestError(str(exc), code="invalid_image") from exc

        shot_id = ObjectId()
        object_key, thumb_key = object_keys(company.id, employee.id, captured_at, shot_id)
        size = await self._storage.put(object_key, image.data)
        thumb_size = await self._storage.put(thumb_key, image.thumbnail)
        shot = Screenshot(
            id=shot_id,
            company_id=company.id,
            employee_id=employee.id,
            device_id=device_id,
            client_id=client_uuid,
            session_id=session_id,
            captured_at=captured_at,
            width=image.width,
            height=image.height,
            object_key=object_key,
            thumb_key=thumb_key,
            size_bytes=size,
            thumb_size_bytes=thumb_size,
            expires_at=captured_at + policy.retention,
        )
        try:
            await self._screenshots.create(company.id, shot)
        except DuplicateKeyError:
            # A concurrent retry won the race: keep its copy, drop ours.
            await self._storage.delete(object_key, thumb_key)
            winner = await self._screenshots.get_by_client_id(company.id, device_id, client_uuid)
            return ScreenshotUploadResult(id=str(winner.id) if winner else "", duplicate=True)
        return ScreenshotUploadResult(id=str(shot_id), duplicate=False)

    # ------------------------------------------------------------------ gallery
    async def _visible_employees(
        self, principal: Principal, team_id: str | None, employee_id: str | None
    ) -> dict[ObjectId, Employee]:
        scope = await self._scopes.employee_scope(principal)
        clauses: list[dict[str, Any]] = [c for c in (scope.filter,) if c]
        if team := parse_ref(team_id, "team_id"):
            clauses.append({"team_id": team})
        if employee := parse_ref(employee_id, "employee_id"):
            clauses.append({"_id": employee})
        query = {"$and": clauses} if len(clauses) > 1 else (clauses[0] if clauses else None)
        ids = await self._employees.ids_matching(principal.company_id, query)
        return await self._employees.find_by_ids(principal.company_id, ids)

    @staticmethod
    def _day_bounds(company: Company, day: date) -> tuple[datetime, datetime]:
        start = datetime.combine(day, time.min, tzinfo=ZoneInfo(company.timezone))
        return start, start + timedelta(days=1)

    def _url(self, principal: Principal, shot: Screenshot, variant: str) -> str:
        return self._signer.sign(
            f"{self._settings.api_prefix}/screenshot-files/{shot.id}/{variant}",
            company_id=str(principal.company_id),
            user_id=str(principal.user_id),
            object_id=str(shot.id),
            variant=variant,
        )

    def _item(self, principal: Principal, shot: Screenshot, employee: Employee) -> ScreenshotItem:
        return ScreenshotItem(
            id=str(shot.id),
            employee=employee_ref(employee),
            captured_at=shot.captured_at,
            width=shot.width,
            height=shot.height,
            thumbnail_url=self._url(principal, shot, "thumb"),
        )

    async def list(
        self,
        principal: Principal,
        *,
        day: date,
        team_id: str | None,
        employee_id: str | None,
        hour: int | None,
        before: datetime | None,
        limit: int,
        meta: RequestMeta,
    ) -> ScreenshotPage:
        company = await self._company(principal.company_id)
        start, end = self._day_bounds(company, day)
        if hour is not None:
            start = start + timedelta(hours=hour)
            end = start + timedelta(hours=1)
        employees = await self._visible_employees(principal, team_id, employee_id)
        limit = max(1, min(limit, PAGE_LIMIT_MAX))
        shots = (
            await self._screenshots.page(
                principal.company_id, list(employees), start, end, before=before, limit=limit + 1
            )
            if employees
            else []
        )
        more = len(shots) > limit
        shots = shots[:limit]
        if shots:
            await self._audit.record(
                "screenshots.listed",
                company_id=principal.company_id,
                actor_user_id=principal.user_id,
                target_type="screenshot",
                subject_employee_id=parse_ref(employee_id, "employee_id"),
                meta=meta,
                metadata={"day": day.isoformat(), "count": len(shots), "ids": [str(s.id) for s in shots]},
            )
        return ScreenshotPage(
            items=[self._item(principal, s, employees[s.employee_id]) for s in shots],
            next_before=shots[-1].captured_at if more else None,
            day=day,
            timezone=company.timezone,
        )

    async def timeline(
        self, principal: Principal, *, day: date, team_id: str | None, employee_id: str | None
    ) -> ScreenshotTimeline:
        """Capture counts per local hour (no images, so nothing to audit)."""
        company = await self._company(principal.company_id)
        start, end = self._day_bounds(company, day)
        employees = await self._visible_employees(principal, team_id, employee_id)
        rows = (
            await self._screenshots.capture_times(
                principal.company_id, list(employees), start, end, TIMELINE_CAPTURES_MAX
            )
            if employees
            else []
        )
        tz = ZoneInfo(company.timezone)
        counts = [0] * 24
        for row in rows:
            captured: datetime = row["captured_at"]
            if captured.tzinfo is None:
                captured = captured.replace(tzinfo=UTC)
            counts[captured.astimezone(tz).hour] += 1
        single = employee_id is not None and len(employees) == 1
        return ScreenshotTimeline(
            day=day,
            timezone=company.timezone,
            total=len(rows),
            buckets=[TimelineBucket(hour=h, count=c) for h, c in enumerate(counts)],
            captures=[TimelineCapture(id=str(r["_id"]), captured_at=r["captured_at"]) for r in rows]
            if single
            else None,
        )

    async def _shot_in_scope(self, principal: Principal, screenshot_id: str) -> tuple[Screenshot, Employee]:
        oid = parse_id(screenshot_id, not_found=_NOT_FOUND, code="screenshot_not_found")
        shot = await self._screenshots.get_by_id(principal.company_id, oid)
        if shot is None:
            raise NotFoundError(_NOT_FOUND, code="screenshot_not_found")
        scope = await self._scopes.employee_scope(principal)
        employee = await self._employees.get_in_scope(principal.company_id, shot.employee_id, scope.filter)
        if employee is None:
            raise NotFoundError(_NOT_FOUND, code="screenshot_not_found")
        return shot, employee

    async def detail(self, principal: Principal, screenshot_id: str, meta: RequestMeta) -> ScreenshotDetail:
        shot, employee = await self._shot_in_scope(principal, screenshot_id)
        device = await self._devices.get_by_id(principal.company_id, shot.device_id)
        around = await self._segments.for_employee(
            principal.company_id,
            shot.employee_id,
            shot.captured_at - timedelta(seconds=1),
            shot.captured_at,
            limit=3,
        )
        application = next(
            (
                s.app_name
                for s in around
                if s.started_at <= shot.captured_at <= s.ended_at + timedelta(seconds=5)
            ),
            None,
        )
        await self._audit.record(
            "screenshot.viewed",
            company_id=principal.company_id,
            actor_user_id=principal.user_id,
            target_type="screenshot",
            target_id=str(shot.id),
            subject_employee_id=shot.employee_id,
            meta=meta,
            metadata={"captured_at": shot.captured_at.isoformat()},
        )
        return ScreenshotDetail(
            **self._item(principal, shot, employee).model_dump(),
            image_url=self._url(principal, shot, "full"),
            device_name=device.name if device else None,
            application=application,
            size_bytes=shot.size_bytes,
            expires_at=shot.expires_at,
            url_expires_in=self._settings.screenshot_url_ttl_seconds,
        )

    async def delete(self, principal: Principal, screenshot_id: str, meta: RequestMeta) -> None:
        shot, _ = await self._shot_in_scope(principal, screenshot_id)
        await self._storage.delete(shot.object_key, shot.thumb_key)
        await self._screenshots.delete_by_id(principal.company_id, shot.id)
        await self._audit.record(
            "screenshot.deleted",
            company_id=principal.company_id,
            actor_user_id=principal.user_id,
            target_type="screenshot",
            target_id=str(shot.id),
            subject_employee_id=shot.employee_id,
            meta=meta,
            metadata={"captured_at": shot.captured_at.isoformat()},
        )

    # ------------------------------------------------------------------ private file access
    async def read_file(
        self, *, screenshot_id: str, variant: str, company_id: str, user_id: str, expires: int, signature: str
    ) -> bytes:
        """Serve one image for a signed URL. Every failure is the same 404 (no oracle)."""
        not_found = NotFoundError(_NOT_FOUND, code="screenshot_not_found")
        if variant not in VARIANTS or not self._signer.verify(
            company_id=company_id,
            user_id=user_id,
            object_id=screenshot_id,
            variant=variant,
            expires=expires,
            signature=signature,
        ):
            raise not_found
        company_oid = parse_id(company_id, not_found=_NOT_FOUND)
        user = await self._users.get_by_id(company_oid, parse_id(user_id, not_found=_NOT_FOUND))
        if user is None or user.status != UserStatus.ACTIVE:
            raise not_found
        permissions = permissions_for_role(user.role)
        if Permission.SCREENSHOT_VIEW not in permissions:
            raise not_found
        principal = Principal(user=user, permissions=permissions)
        shot, _ = await self._shot_in_scope(principal, screenshot_id)
        try:
            return await self._storage.get(shot.object_key if variant == "full" else shot.thumb_key)
        except ObjectNotFoundError:
            logger.error("Screenshot %s has no stored object", shot.id)
            raise not_found from None

    # ------------------------------------------------------------------ retention
    async def purge_expired(self) -> int:
        return await purge_expired_screenshots(self._screenshots, self._storage)
