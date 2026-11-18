"""Devices plugged into employees' computers, files copied with USB drives, and possible automated input.

Fed by the desktop agent (1.0.2+) through the event intake:

* ``device.connected`` / ``device.disconnected`` → one record per connection (who, which computer, which device,
  from when to when), and an alert for the device types the workspace chose (unless the device is on the allowed
  list);
* ``usb.files`` → the file names and sizes copied to, deleted from or copied from a USB drive (never contents),
  linked to that drive's connection, and an alert;
* ``automation.check`` → one record per occurrence of possible automated input, updated as it develops (asked,
  answered or not, ended), with an alert when it is reported.

Records are kept for 90 days. Alerts go to the people who can view that employee's activity, and only for events
that just happened (not ones uploaded late from an offline computer).
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from bson import ObjectId
from pymongo import ASCENDING, DESCENDING, IndexModel

from app.auth.permissions import Permission
from app.auth.principal import Principal
from app.core.exceptions import BadRequestError, NotFoundError
from app.models.company import Company
from app.models.notification import NotificationType
from app.repositories.base import sync_indexes
from app.repositories.organization import DepartmentRepository, EmployeeRepository, TeamRepository
from app.schemas.agent import (
    AutomationCheckEvent,
    DeviceConnectedEvent,
    DeviceDisconnectedEvent,
    UsbFilesEvent,
)
from app.services.access_scope import AccessScopeService
from app.services.helpers import parse_id, parse_ref
from app.services.notifications.notifier import AlertEvent, NullNotifier
from app.utils.time import utcnow

logger = logging.getLogger(__name__)

CONNECTIONS = "device_connections"
FILE_REPORTS = "usb_file_reports"
CHECKS = "automation_checks"
KEEP_SECONDS = 90 * 86_400
MAX_DAYS = 93
MAX_ROWS = 2000

KIND_LABEL = {
    "storage": "USB drive",
    "phone": "phone",
    "mouse": "mouse",
    "keyboard": "keyboard",
    "camera": "camera",
    "audio": "headset or audio device",
}

#: Common USB makers, so a generic name like "HID-compliant mouse" still says something.
VENDORS = {
    "046D": "Logitech", "045E": "Microsoft", "413C": "Dell", "03F0": "HP", "17EF": "Lenovo", "1532": "Razer",
    "0781": "SanDisk", "0951": "Kingston", "090C": "Silicon Motion", "04E8": "Samsung", "05AC": "Apple",
    "18D1": "Google", "2717": "Xiaomi", "22B8": "Motorola", "12D1": "Huawei", "2A70": "OnePlus", "0BDA": "Realtek",
    "04F2": "Chicony", "1A86": "QinHeng (CH340, common in cheap USB gadgets)", "1C4F": "SiGma Micro",
    "093A": "PixArt", "248A": "Maxxter", "0E8F": "GreenAsia", "1EA7": "SHARKOON", "258A": "SINO WEALTH",
    "13FE": "Phison", "058F": "Alcor Micro", "0BC2": "Seagate", "1058": "Western Digital", "0480": "Toshiba",
    "152D": "JMicron", "174C": "ASMedia", "05E3": "Genesys Logic", "8564": "Transcend", "1F75": "Innostor",
}  # fmt: skip


def size_text(size: int | None) -> str:
    if not size:
        return ""
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1000 or unit == "TB":
            return f"{value:.0f} {unit}" if unit in ("B", "KB") or value >= 10 else f"{value:.1f} {unit}"
        value /= 1000
    return ""


def device_title(
    name: str, hardware_id: str | None, size: int | None = None, label: str | None = None
) -> str:
    """'SanDisk Cruzer Blade (32 GB, "DATA")' / 'HID-compliant mouse (Logitech 046D:C542)'."""
    extra = []
    if size:
        extra.append(size_text(size))
    if label:
        extra.append(f"“{label}”")
    if hardware_id:
        vendor = VENDORS.get(hardware_id.split(":")[0])
        extra.append(
            f"{vendor} {hardware_id}" if vendor and vendor.split(" ")[0] not in name else hardware_id
        )
    return f"{name} ({', '.join(extra)})" if extra else name


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


class DeviceWatchService:
    _indexed = False

    def __init__(
        self,
        db: Any,
        *,
        notifier: Any = None,
        freshness_seconds: int = 900,
        scopes: AccessScopeService | None = None,
    ) -> None:
        self._db = db
        self._notifier = notifier or NullNotifier()
        self._freshness = timedelta(seconds=freshness_seconds)
        self._scopes = scopes
        self._employees = EmployeeRepository(db)

    async def ensure_indexes(self) -> None:
        if DeviceWatchService._indexed:
            return
        ttl = IndexModel([("created_at", ASCENDING)], name="ttl", expireAfterSeconds=KEEP_SECONDS)
        await sync_indexes(
            self._db[CONNECTIONS],
            [
                IndexModel([("company_id", ASCENDING), ("connected_at", DESCENDING)], name="company_time"),
                IndexModel(
                    [
                        ("company_id", ASCENDING),
                        ("device_id", ASCENDING),
                        ("device_key", ASCENDING),
                        ("connected_at", DESCENDING),
                    ],
                    name="device_key",
                ),
                ttl,
            ],
        )
        await sync_indexes(
            self._db[FILE_REPORTS],
            [
                IndexModel([("company_id", ASCENDING), ("started_at", DESCENDING)], name="company_time"),
                IndexModel([("company_id", ASCENDING), ("connection_id", ASCENDING)], name="connection"),
                ttl,
            ],
        )
        await sync_indexes(
            self._db[CHECKS],
            [
                IndexModel([("company_id", ASCENDING), ("check_id", ASCENDING)], name="check", unique=True),
                IndexModel([("company_id", ASCENDING), ("started_at", DESCENDING)], name="company_time"),
                ttl,
            ],
        )
        DeviceWatchService._indexed = True

    def _fresh(self, at: datetime) -> bool:
        return utcnow() - _aware(at) <= self._freshness

    @staticmethod
    def _local(company: Company, at: datetime) -> str:
        return _aware(at).astimezone(ZoneInfo(company.timezone)).strftime("%H:%M")

    # ------------------------------------------------------------------ intake
    async def handle(self, ctx: Any, company: Company, event: Any) -> None:
        await self.ensure_indexes()
        if isinstance(event, DeviceConnectedEvent):
            await self._connected(ctx, company, event)
        elif isinstance(event, DeviceDisconnectedEvent):
            await self._disconnected(ctx, event)
        elif isinstance(event, UsbFilesEvent):
            await self._files(ctx, company, event)
        elif isinstance(event, AutomationCheckEvent):
            await self._check(ctx, company, event)

    def _base(self, ctx: Any) -> dict[str, Any]:
        return {"company_id": ctx.company_id, "employee_id": ctx.employee.id, "device_id": ctx.device.id}

    async def _open_connection(self, ctx: Any, key: str) -> dict[str, Any] | None:
        doc: dict[str, Any] | None = await self._db[CONNECTIONS].find_one(
            {
                "company_id": ctx.company_id,
                "device_id": ctx.device.id,
                "device_key": key,
                "disconnected_at": None,
            },
            sort=[("connected_at", DESCENDING)],
        )
        return doc

    async def _connected(self, ctx: Any, company: Company, event: DeviceConnectedEvent) -> None:
        if not company.activity_policy.track_devices:
            return
        if await self._open_connection(ctx, event.device_key) is not None:
            return  # already open (the agent restarted)
        doc = {
            **self._base(ctx),
            "laptop": ctx.device.name,
            "device_key": event.device_key,
            "kind": event.kind,
            "name": event.name,
            "hardware_id": event.hardware_id,
            "size_bytes": event.size_bytes,
            "label": event.label,
            "connected_at": event.occurred_at,
            "disconnected_at": None,
            "at_start": event.at_start,
            "file_counts": {},
            "bytes_to_usb": 0,
            "bytes_from_usb": 0,
            "created_at": utcnow(),
        }
        await self._db[CONNECTIONS].insert_one(doc)
        policy = company.activity_policy
        allowed = {d.key for d in policy.allowed_devices}
        if (
            event.kind not in policy.device_alert_kinds
            or event.device_key in allowed
            or not self._fresh(event.occurred_at)
        ):
            return
        what = KIND_LABEL.get(event.kind, "device")
        title = device_title(event.name, event.hardware_id, event.size_bytes, event.label)
        when = self._local(company, event.occurred_at)
        body = (
            f"{title} was found connected to {ctx.device.name} when WorkPulse started at {when} (it was plugged "
            "in while WorkPulse wasn't running)."
            if event.at_start
            else f"{title} was plugged into {ctx.device.name} at {when}."
        )
        if event.kind == "mouse":
            body += " An extra mouse can also be a mouse-jiggler device."
        self._notifier.emit(
            AlertEvent(
                company_id=ctx.company_id,
                type=NotificationType.DEVICE_CONNECTED,
                title=f"{what[0].upper()}{what[1:]} connected — {{employee}}",
                body=body,
                employee_id=ctx.employee.id,
                link="/alerts?tab=devices",
                subject=f"device:{event.device_key}:{event.occurred_at.isoformat()}",
                permission=Permission.ACTIVITY_VIEW,
                data={"device_key": event.device_key, "kind": event.kind, "laptop": ctx.device.name},
            )
        )

    async def _disconnected(self, ctx: Any, event: DeviceDisconnectedEvent) -> None:
        doc = await self._open_connection(ctx, event.device_key)
        if doc is not None:
            await self._db[CONNECTIONS].update_one(
                {"_id": doc["_id"]}, {"$set": {"disconnected_at": event.occurred_at}}
            )

    async def _files(self, ctx: Any, company: Company, event: UsbFilesEvent) -> None:
        policy = company.activity_policy
        if not (policy.track_devices and policy.track_usb_files):
            return
        connection = await self._open_connection(ctx, event.device_key) or await self._db[
            CONNECTIONS
        ].find_one(
            {"company_id": ctx.company_id, "device_id": ctx.device.id, "device_key": event.device_key},
            sort=[("connected_at", DESCENDING)],
        )
        report = {
            **self._base(ctx),
            "laptop": ctx.device.name,
            "connection_id": connection["_id"] if connection else None,
            "device_key": event.device_key,
            "name": event.name,
            "hardware_id": event.hardware_id,
            "size_bytes": event.size_bytes,
            "label": event.label,
            "started_at": event.started_at,
            "ended_at": event.ended_at,
            "counts": event.counts,
            "bytes_to_usb": event.bytes_to_usb,
            "bytes_from_usb": event.bytes_from_usb,
            "files": [f.model_dump(mode="python") for f in event.files],
            "truncated": event.truncated,
            "created_at": utcnow(),
        }
        await self._db[FILE_REPORTS].insert_one(report)
        if connection is not None:
            await self._db[CONNECTIONS].update_one(
                {"_id": connection["_id"]},
                {
                    "$inc": {
                        **{f"file_counts.{k}": v for k, v in event.counts.items() if k.isidentifier()},
                        "bytes_to_usb": event.bytes_to_usb,
                        "bytes_from_usb": event.bytes_from_usb,
                    }
                },
            )
        if not policy.usb_file_alerts or not self._fresh(event.occurred_at):
            return
        counts = event.counts
        to_usb = counts.get("added", 0) + counts.get("changed", 0)
        parts = []
        if to_usb:
            parts.append(
                f"{to_usb} file{'s' if to_usb != 1 else ''} copied to it ({size_text(event.bytes_to_usb) or '0 B'})"
            )
        if counts.get("copied_to_computer"):
            n = counts["copied_to_computer"]
            parts.append(f"{n} copied from it to the computer ({size_text(event.bytes_from_usb) or '0 B'})")
        if counts.get("deleted"):
            parts.append(f"{counts['deleted']} deleted from it")
        if counts.get("renamed"):
            parts.append(f"{counts['renamed']} renamed")
        names = [f.path.rsplit("/", 1)[-1] for f in event.files[:5]]
        more = sum(counts.values()) - len(names)
        listing = ", ".join(names) + (f" and {more} more" if more > 0 else "")
        span = f"{self._local(company, event.started_at)} to {self._local(company, event.ended_at)}"
        title = (
            "Files copied with USB — {employee}"
            if to_usb or counts.get("copied_to_computer")
            else "Files changed on USB — {employee}"
        )
        self._notifier.emit(
            AlertEvent(
                company_id=ctx.company_id,
                type=NotificationType.USB_FILES,
                title=title,
                body=f"{device_title(event.name, None, event.size_bytes, event.label)} on {ctx.device.name}, {span}: "
                f"{'; '.join(parts) or 'files changed'}. Files: {listing}.",
                employee_id=ctx.employee.id,
                link="/alerts?tab=devices",
                subject=f"usb:{event.device_key}",
                permission=Permission.ACTIVITY_VIEW,
                data={"device_key": event.device_key, "laptop": ctx.device.name},
            )
        )

    async def _check(self, ctx: Any, company: Company, event: AutomationCheckEvent) -> None:
        check_id = str(event.check_id)
        changes: dict[str, Any] = {
            "laptop": ctx.device.name,
            "kind": event.kind,
            "outcome": event.outcome,
            "started_at": event.started_at,
            "minutes": event.minutes,
            "move_minutes": event.move_minutes,
            "max_span_px": event.max_span_px,
            "apps": event.apps,
            "updated_at": utcnow(),
        }
        if event.asked_at:
            changes["asked_at"] = event.asked_at
        if event.ended_at:
            changes["ended_at"] = event.ended_at
        if event.outcome == "confirmed":
            changes["answered"] = True
        if event.outcome in ("unanswered", "detected"):
            changes["reported"] = True
        await self._db[CHECKS].update_one(
            {"company_id": ctx.company_id, "check_id": check_id},
            {
                "$set": changes,
                "$setOnInsert": {
                    **self._base(ctx),
                    "check_id": check_id,
                    "created_at": utcnow(),
                    **{k: False for k in ("answered", "reported") if k not in changes},
                },
            },
            upsert=True,
        )
        if event.outcome not in ("unanswered", "detected") or not self._fresh(event.occurred_at):
            return
        start = self._local(company, event.started_at)
        apps = f" ({', '.join(event.apps)})" if event.apps else ""
        if event.kind == "hardware":
            asked = self._local(company, event.asked_at) if event.asked_at else "the check"
            body = (
                f"Since {start} the mouse on {ctx.device.name} has been moving non-stop with no click, scroll or "
                f"typing ({event.minutes} min so far, within an area of {event.max_span_px} px){apps}. The "
                f'"Are you still working?" question at {asked} wasn\'t answered. This can be a mouse-jiggler '
                "device or the mouse resting on something that moves (a watch, a fan). A screenshot was taken "
                "if screenshots are on."
            )
            title = "Possible automated mouse movement — {employee}"
        else:
            body = (
                f"Since {start}, input on {ctx.device.name} has come only from software ({event.minutes} min, no "
                f"real keyboard or mouse use){apps}: a mouse-mover app, or someone controlling the computer "
                "remotely (AnyDesk, TeamViewer). This time already counts as idle."
            )
            title = "Software-generated input — {employee}"
        self._notifier.emit(
            AlertEvent(
                company_id=ctx.company_id,
                type=NotificationType.AUTOMATION_SUSPECTED,
                title=title,
                body=body,
                employee_id=ctx.employee.id,
                link="/alerts?tab=automation",
                subject=f"automation:{check_id}",
                dedupe_key=f"automation:{check_id}",
                permission=Permission.ACTIVITY_VIEW,
                data={"check_id": check_id, "kind": event.kind, "laptop": ctx.device.name},
            )
        )

    # ------------------------------------------------------------------ reading
    async def _visible(self, principal: Principal, employee_id: str | None) -> list[ObjectId]:
        assert self._scopes is not None
        scope = await self._scopes.employee_scope(principal)
        clauses: list[dict[str, Any]] = [c for c in (scope.filter,) if c]
        if employee := parse_ref(employee_id, "employee_id"):
            clauses.append({"_id": employee})
        query = {"$and": clauses} if len(clauses) > 1 else (clauses[0] if clauses else None)
        return list(await self._employees.ids_matching(principal.company_id, query))

    @staticmethod
    def _range(company: Company, start: date, end: date) -> tuple[datetime, datetime]:
        if end < start:
            raise BadRequestError("The end date must not be before the start date.", code="invalid_range")
        if (end - start).days >= MAX_DAYS:
            raise BadRequestError(f"At most {MAX_DAYS} days at a time.", code="range_too_long")
        zone = ZoneInfo(company.timezone)
        return (
            datetime.combine(start, time.min, zone).astimezone(UTC),
            datetime.combine(end + timedelta(days=1), time.min, zone).astimezone(UTC),
        )

    async def _people(self, company_id: ObjectId, ids: set[ObjectId]) -> dict[ObjectId, dict[str, str]]:
        people = await self._employees.find_by_ids(company_id, ids)
        departments = await DepartmentRepository(self._db).find_by_ids(
            company_id, {e.department_id for e in people.values() if e.department_id}
        )
        teams = await TeamRepository(self._db).find_by_ids(
            company_id, {e.team_id for e in people.values() if e.team_id}
        )
        out = {}
        for i, e in people.items():
            dept = departments.get(e.department_id) if e.department_id else None
            team = teams.get(e.team_id) if e.team_id else None
            out[i] = {
                "employee": e.full_name,
                "department": dept.name if dept else "",
                "team": team.name if team else "",
            }
        return out

    async def connections(
        self, principal: Principal, company: Company, start: date, end: date, employee_id: str | None = None
    ) -> list[dict[str, Any]]:
        await self.ensure_indexes()
        lo, hi = self._range(company, start, end)
        ids = await self._visible(principal, employee_id)
        if not ids:
            return []
        docs = [
            d
            async for d in self._db[CONNECTIONS]
            .find(
                {
                    "company_id": company.id,
                    "employee_id": {"$in": ids},
                    "connected_at": {"$gte": lo, "$lt": hi},
                }
            )
            .sort("connected_at", DESCENDING)
            .limit(MAX_ROWS)
        ]
        people = await self._people(company.id, {d["employee_id"] for d in docs})
        allowed = {d.key for d in company.activity_policy.allowed_devices}
        rows = []
        for d in docs:
            who = people.get(d["employee_id"], {"employee": "Removed employee", "department": "", "team": ""})
            connected, gone = _aware(d["connected_at"]), d.get("disconnected_at")
            rows.append(
                {
                    "id": str(d["_id"]),
                    "employee_id": str(d["employee_id"]),
                    **who,
                    "laptop": d.get("laptop") or "",
                    "device_key": d["device_key"],
                    "kind": d["kind"],
                    "name": d["name"],
                    "title": device_title(
                        d["name"], d.get("hardware_id"), d.get("size_bytes"), d.get("label")
                    ),
                    "hardware_id": d.get("hardware_id"),
                    "size_bytes": d.get("size_bytes"),
                    "connected_at": connected,
                    "disconnected_at": _aware(gone) if gone else None,
                    "at_start": bool(d.get("at_start")),
                    "allowed": d["device_key"] in allowed,
                    "file_counts": d.get("file_counts") or {},
                    "bytes_to_usb": d.get("bytes_to_usb") or 0,
                    "bytes_from_usb": d.get("bytes_from_usb") or 0,
                }
            )
        return rows

    async def connection_files(
        self, principal: Principal, company: Company, connection_id: str
    ) -> list[dict[str, Any]]:
        await self.ensure_indexes()
        oid = parse_id(connection_id)
        connection = await self._db[CONNECTIONS].find_one({"_id": oid, "company_id": company.id})
        if connection is None or connection["employee_id"] not in await self._visible(principal, None):
            raise NotFoundError("Connection not found.")
        files: list[dict[str, Any]] = []
        async for report in (
            self._db[FILE_REPORTS]
            .find({"company_id": company.id, "connection_id": oid})
            .sort("started_at", ASCENDING)
        ):
            for f in report.get("files", []):
                files.append({**f, "at": _aware(f["at"])})
            if report.get("truncated"):
                files.append(
                    {
                        "action": "more",
                        "path": "More files were changed than one report can list.",
                        "at": _aware(report["ended_at"]),
                    }
                )
        return files

    async def checks(
        self, principal: Principal, company: Company, start: date, end: date, employee_id: str | None = None
    ) -> list[dict[str, Any]]:
        await self.ensure_indexes()
        lo, hi = self._range(company, start, end)
        ids = await self._visible(principal, employee_id)
        if not ids:
            return []
        docs = [
            d
            async for d in self._db[CHECKS]
            .find(
                {"company_id": company.id, "employee_id": {"$in": ids}, "started_at": {"$gte": lo, "$lt": hi}}
            )
            .sort("started_at", DESCENDING)
            .limit(MAX_ROWS)
        ]
        people = await self._people(company.id, {d["employee_id"] for d in docs})
        rows = []
        for d in docs:
            who = people.get(d["employee_id"], {"employee": "Removed employee", "department": "", "team": ""})
            ended = d.get("ended_at")
            if d["kind"] == "software":
                status = "software"
            elif d.get("answered"):
                status = "answered"
            elif d.get("reported"):
                status = "unanswered"
            else:
                status = "stopped" if ended else "asking"
            rows.append(
                {
                    "id": d["check_id"],
                    "employee_id": str(d["employee_id"]),
                    **who,
                    "laptop": d.get("laptop") or "",
                    "kind": d["kind"],
                    "status": status,
                    "started_at": _aware(d["started_at"]),
                    "asked_at": _aware(d["asked_at"]) if d.get("asked_at") else None,
                    "ended_at": _aware(ended) if ended else None,
                    "minutes": d.get("minutes") or 0,
                    "max_span_px": d.get("max_span_px") or 0,
                    "apps": d.get("apps") or [],
                }
            )
        return rows
