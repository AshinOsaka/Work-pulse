"""Background report generation.

Requests are stored as jobs (`report_jobs`). This worker claims the oldest queued job atomically, so several API
processes can share the queue safely, and moves it through *preparing* (checking access, collecting data) and
*generating* (writing the file) to *ready*. Files are encrypted in object storage and removed after the retention
period. Jobs interrupted by a restart start again; failures are recorded with a message safe to show the requester.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import date
from typing import Any

from pymongo.asynchronous.database import AsyncDatabase

from app.auth.permissions import Permission, permissions_for_role
from app.auth.principal import Principal
from app.core.config import Settings
from app.core.object_storage import ObjectStorage
from app.models.report import ReportFormat, ReportJob, ReportStatus
from app.models.user import UserStatus
from app.repositories.audit_log import AuditLogRepository
from app.repositories.report import ReportJobRepository
from app.repositories.user import UserRepository
from app.services.audit_service import AuditService
from app.services.reports.builders import REPORT_TYPES, ReportData
from app.services.reports.service import ReportEngine, allowed, expires_from
from app.services.reports.writers import FORMATS, ReportMeta, to_csv, to_pdf, to_xlsx
from app.utils.time import utcnow

logger = logging.getLogger(__name__)

IDLE_POLL_SECONDS = 5.0
PURGE_EVERY_SECONDS = 600.0


class ReportFailed(Exception):
    """A failure whose message can be shown to the requester."""


class ReportWorker:
    def __init__(
        self,
        db: AsyncDatabase[dict[str, Any]],
        storage: ObjectStorage,
        settings: Settings,
        engine_factory: Any,
    ) -> None:
        self._db = db
        self._storage = storage
        self._settings = settings
        self._engine_factory = engine_factory  # () -> ReportEngine
        self._jobs = ReportJobRepository(db)
        self._wake = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._last_purge = 0.0

    def wake(self) -> None:
        self._wake.set()

    async def start(self) -> None:
        resumed = await self._jobs.requeue_interrupted()
        if resumed:
            logger.info("Reports: %d interrupted report(s) queued again", resumed)
        self._task = asyncio.create_task(self._loop(), name="report-worker")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _loop(self) -> None:
        while True:
            try:
                job = await self._jobs.claim_next()
                if job is not None:
                    await self._run(job)
                    continue
                await self._purge_if_due()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Report worker iteration failed; will retry")
            self._wake.clear()
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._wake.wait(), timeout=IDLE_POLL_SECONDS)

    async def _purge_if_due(self) -> None:
        loop = asyncio.get_running_loop()
        if loop.time() - self._last_purge < PURGE_EVERY_SECONDS:
            return
        self._last_purge = loop.time()
        for job in await self._jobs.expired(utcnow()):
            if job.object_key:
                await self._storage.delete(job.object_key)
            await self._jobs.progress(job.id, {"status": ReportStatus.EXPIRED, "object_key": None})
        # (expired jobs stay listed, without a file, so the history remains visible)

    async def _principal(self, job: ReportJob) -> Principal:
        user = await UserRepository(self._db).get_by_id(job.company_id, job.requested_by)
        if user is None or user.status != UserStatus.ACTIVE:
            raise ReportFailed("The account that requested this report is no longer active.")
        principal = Principal(user=user, permissions=permissions_for_role(user.role))
        if not principal.has(Permission.REPORT_EXPORT) or not allowed(principal, job.report_type):
            raise ReportFailed("You no longer have permission to generate this report.")
        return principal

    async def _run(self, job: ReportJob) -> None:
        audit = AuditService(AuditLogRepository(self._db))
        try:
            principal = await self._principal(job)
            engine: ReportEngine = self._engine_factory()
            start, end = date.fromisoformat(job.start), date.fromisoformat(job.end)
            await self._jobs.progress(job.id, {"status": ReportStatus.PREPARING, "progress": 15})
            data, ctx = await engine.build(principal, job.report_type, start, end, job.filters)
            await self._jobs.progress(
                job.id, {"status": ReportStatus.GENERATING, "progress": 60, "row_count": len(data.rows)}
            )
            lines = [
                f"Generated {utcnow().astimezone(ctx.tz).strftime('%d %b %Y %H:%M')} ({ctx.company.timezone}) by {job.requested_by_name}",
                *await engine.describe_filters(principal, job.filters),
                f"People in scope: {len(ctx.employees)} · Rows: {len(data.rows):,}",
            ]
            meta = ReportMeta(
                title=f"{REPORT_TYPES[job.report_type].label} report",
                subtitle=f"{start.strftime('%d %b %Y')} – {end.strftime('%d %b %Y')} · {job.period.value.title()} · {ctx.company.name}",  # noqa: RUF001 - shown to people
                lines=lines,
                notes=data.notes,
            )
            content, notes = await asyncio.to_thread(self._write, job.format, data, meta)
            content_type, ext = FORMATS[job.format.value]
            key = f"reports/{job.company_id}/{job.id}.{ext}"
            await self._jobs.progress(job.id, {"progress": 90})
            size = await self._storage.put(key, content)
            now = utcnow()
            await self._jobs.progress(
                job.id,
                {
                    "status": ReportStatus.READY,
                    "progress": 100,
                    "object_key": key,
                    "filename": f"workpulse-{job.report_type.value.replace('_', '-')}-{job.start}-to-{job.end}.{ext}",
                    "content_type": content_type,
                    "size_bytes": size,
                    "row_count": len(data.rows),
                    "notes": [*data.notes, *notes],
                    "finished_at": now,
                    "expires_at": expires_from(now, self._settings),
                },
            )
            await audit.record(
                "report.generated",
                company_id=job.company_id,
                actor_user_id=job.requested_by,
                target_type="report",
                target_id=str(job.id),
                metadata={
                    "type": job.report_type.value,
                    "format": job.format.value,
                    "rows": len(data.rows),
                    "bytes": size,
                },
            )
            logger.info("Report %s ready (%s, %d rows)", job.id, job.report_type.value, len(data.rows))
        except ReportFailed as exc:
            await self._fail(job, str(exc), audit)
        except Exception:
            logger.exception("Report %s failed", job.id)
            await self._fail(
                job, "The report could not be generated. Try a shorter period, or try again later.", audit
            )

    def _write(self, fmt: ReportFormat, data: ReportData, meta: ReportMeta) -> tuple[bytes, list[str]]:
        if fmt == ReportFormat.CSV:
            return to_csv(data, meta), []
        if fmt == ReportFormat.XLSX:
            return to_xlsx(data, meta), []
        return to_pdf(
            data, meta, max_rows=self._settings.report_pdf_max_rows, font=self._settings.report_pdf_font
        )

    async def _fail(self, job: ReportJob, message: str, audit: AuditService) -> None:
        await self._jobs.progress(
            job.id,
            {"status": ReportStatus.FAILED, "error": message, "finished_at": utcnow(), "progress": 100},
        )
        await audit.record(
            "report.failed",
            company_id=job.company_id,
            actor_user_id=job.requested_by,
            target_type="report",
            target_id=str(job.id),
            metadata={"type": job.report_type.value, "reason": message},
        )
