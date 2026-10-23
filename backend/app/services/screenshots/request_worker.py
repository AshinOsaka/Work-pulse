"""Background packaging of screenshot download requests.

Requests are stored as jobs (`screenshot_requests`). This worker claims the oldest queued request atomically,
re-checks the requester's account, permission and access scope, gathers that employee's screenshots for the
requested day from encrypted object storage, bundles them into one encrypted ZIP, and marks the request ready.
ZIPs are removed after the retention period. Requests interrupted by a restart start again; failures are recorded
with a message safe to show the requester.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import logging
import re
import zipfile
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from pymongo.asynchronous.database import AsyncDatabase

from app.auth.permissions import Permission, permissions_for_role
from app.auth.principal import Principal
from app.core.config import Settings
from app.core.object_storage import ObjectNotFoundError, ObjectStorage
from app.models.company import Company
from app.models.screenshot_request import ScreenshotRequest, ScreenshotRequestStatus
from app.models.user import UserStatus
from app.repositories.audit_log import AuditLogRepository
from app.repositories.company import CompanyRepository
from app.repositories.organization import DepartmentRepository, EmployeeRepository, TeamRepository
from app.repositories.screenshot import ScreenshotRepository
from app.repositories.screenshot_request import ScreenshotRequestRepository
from app.repositories.user import UserRepository
from app.services.access_scope import AccessScopeService
from app.services.audit_service import AuditService
from app.utils.time import utcnow

logger = logging.getLogger(__name__)

IDLE_POLL_SECONDS = 5.0
PURGE_EVERY_SECONDS = 600.0


class RequestFailed(Exception):
    """A failure whose message can be shown to the requester."""


class ScreenshotRequestWorker:
    def __init__(
        self, db: AsyncDatabase[dict[str, Any]], storage: ObjectStorage, settings: Settings
    ) -> None:
        self._db = db
        self._storage = storage
        self._settings = settings
        self._requests = ScreenshotRequestRepository(db)
        self._wake = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._last_purge = 0.0

    def wake(self) -> None:
        self._wake.set()

    async def start(self) -> None:
        resumed = await self._requests.requeue_interrupted()
        if resumed:
            logger.info("Screenshot exports: %d interrupted request(s) queued again", resumed)
        self._task = asyncio.create_task(self._loop(), name="screenshot-request-worker")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def run_pending(self) -> int:
        """Package every queued request now (for one-off processing and tests). Returns how many were handled."""
        handled = 0
        while True:
            request = await self._requests.claim_next()
            if request is None:
                return handled
            await self._run(request)
            handled += 1

    async def _loop(self) -> None:
        while True:
            try:
                request = await self._requests.claim_next()
                if request is not None:
                    await self._run(request)
                    continue
                await self._purge_if_due()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Screenshot request worker iteration failed; will retry")
            self._wake.clear()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._wake.wait(), timeout=IDLE_POLL_SECONDS)

    async def _purge_if_due(self) -> None:
        loop = asyncio.get_running_loop()
        if loop.time() - self._last_purge < PURGE_EVERY_SECONDS:
            return
        self._last_purge = loop.time()
        for request in await self._requests.expired(utcnow()):
            if request.object_key:
                await self._storage.delete(request.object_key)
            await self._requests.progress(
                request.id, {"status": ScreenshotRequestStatus.EXPIRED, "object_key": None}
            )

    async def _resolve(self, request: ScreenshotRequest) -> Company:
        """Re-check the requester and that the employee is still in their scope, as scope may have changed."""
        user = await UserRepository(self._db).get_by_id(request.company_id, request.requested_by)
        if user is None or user.status != UserStatus.ACTIVE:
            raise RequestFailed("The account that requested this download is no longer active.")
        principal = Principal(user=user, permissions=permissions_for_role(user.role))
        if not principal.has(Permission.SCREENSHOT_VIEW):
            raise RequestFailed("You no longer have permission to view screenshots.")
        scopes = AccessScopeService(
            EmployeeRepository(self._db), TeamRepository(self._db), DepartmentRepository(self._db)
        )
        scope = await scopes.employee_scope(principal)
        employee = await EmployeeRepository(self._db).get_in_scope(
            request.company_id, request.employee_id, scope.filter
        )
        if employee is None:
            raise RequestFailed("This employee is no longer in your access scope.")
        company = await CompanyRepository(self._db).get_by_id(request.company_id)
        if company is None:
            raise RequestFailed("The workspace is no longer available.")
        return company

    async def _run(self, request: ScreenshotRequest) -> None:
        audit = AuditService(AuditLogRepository(self._db))
        try:
            company = await self._resolve(request)
            tz = ZoneInfo(company.timezone)
            day = date.fromisoformat(request.day)
            lo = datetime.combine(day, time.min, tzinfo=tz)
            hi = lo + timedelta(days=1)
            shots = await ScreenshotRepository(self._db).in_range(
                request.company_id, [request.employee_id], lo, hi, self._settings.screenshot_export_max_images
            )
            if not shots:
                await self._requests.progress(
                    request.id,
                    {
                        "status": ScreenshotRequestStatus.EMPTY,
                        "progress": 100,
                        "screenshot_count": 0,
                        "finished_at": utcnow(),
                        "error": "No screenshots were captured for this person on that day.",
                    },
                )
                return
            await self._requests.progress(
                request.id,
                {"status": ScreenshotRequestStatus.PACKAGING, "progress": 40, "screenshot_count": len(shots)},
            )
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as archive:
                manifest = [f"WorkPulse screenshots for {request.employee_name} on {request.day} ({company.timezone})"]
                for index, shot in enumerate(shots, start=1):
                    try:
                        image = await self._storage.get(shot.object_key)
                    except ObjectNotFoundError:
                        continue  # a capture expired between listing and packaging; skip it
                    local = shot.captured_at.astimezone(tz)
                    name = f"{index:04d}_{local:%H%M%S}.webp"
                    archive.writestr(name, image)
                    manifest.append(f"{name}  {local:%Y-%m-%d %H:%M:%S}")
                archive.writestr("manifest.txt", "\n".join(manifest) + "\n")
            content = buffer.getvalue()
            key = f"exports/{request.company_id}/screenshots/{request.id}.zip"
            await self._requests.progress(request.id, {"progress": 90})
            size = await self._storage.put(key, content)
            now = utcnow()
            await self._requests.progress(
                request.id,
                {
                    "status": ScreenshotRequestStatus.READY,
                    "progress": 100,
                    "object_key": key,
                    "filename": f"workpulse-screenshots-{_slug(request.employee_name)}-{request.day}.zip",
                    "content_type": "application/zip",
                    "size_bytes": size,
                    "finished_at": now,
                    "expires_at": now + timedelta(hours=self._settings.screenshot_export_retention_hours),
                },
            )
            await audit.record(
                "screenshot.export_generated",
                company_id=request.company_id,
                actor_user_id=request.requested_by,
                target_type="employee",
                target_id=str(request.employee_id),
                metadata={"day": request.day, "count": len(shots), "bytes": size},
            )
            logger.info("Screenshot export %s ready (%d image(s))", request.id, len(shots))
        except RequestFailed as exc:
            await self._fail(request, str(exc))
        except Exception:
            logger.exception("Screenshot export %s failed", request.id)
            await self._fail(request, "The download could not be prepared. Try again later.")

    async def _fail(self, request: ScreenshotRequest, message: str) -> None:
        await self._requests.progress(
            request.id,
            {
                "status": ScreenshotRequestStatus.FAILED,
                "error": message,
                "finished_at": utcnow(),
                "progress": 100,
            },
        )


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "employee"
