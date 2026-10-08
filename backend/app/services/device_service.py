"""Device registration foundation.

Phase 2 records devices against employees and issues a one-time enrolment
code (stored hashed, time-limited). The Windows agent (Phase 4) will exchange
that code for device credentials and report heartbeats.
"""

from __future__ import annotations

from datetime import timedelta

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.auth.principal import Principal
from app.core.config import Settings
from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.core.security import generate_enrollment_code, hash_token, normalise_enrollment_code
from app.models.organization import Device, DeviceStatus, EmployeeStatus
from app.repositories.organization import DeviceRepository, EmployeeRepository
from app.schemas.organization import DeviceCreate, DeviceOut, DeviceRegistered
from app.services.access_scope import AccessScopeService
from app.services.audit_service import AuditService
from app.services.context import RequestMeta
from app.services.helpers import parse_id
from app.utils.time import utcnow


def device_out(device: Device) -> DeviceOut:
    return DeviceOut(
        id=str(device.id),
        employee_id=str(device.employee_id),
        name=device.name,
        hostname=device.hostname,
        os=device.os,
        os_version=device.os_version,
        agent_version=device.agent_version,
        status=device.status,
        enrollment_expires_at=device.enrollment_expires_at if device.status == DeviceStatus.PENDING else None,
        enrolled_at=device.enrolled_at,
        last_seen_at=device.last_seen_at,
        revoked_at=device.revoked_at,
        created_at=device.created_at,
    )


class DeviceService:
    def __init__(
        self,
        *,
        settings: Settings,
        devices: DeviceRepository,
        employees: EmployeeRepository,
        scopes: AccessScopeService,
        audit: AuditService,
    ) -> None:
        self._settings = settings
        self._devices = devices
        self._employees = employees
        self._scopes = scopes
        self._audit = audit

    async def list_for_employee(self, principal: Principal, employee_id: str) -> list[DeviceOut]:
        oid = await self._visible_employee_id(principal, employee_id)
        return [device_out(d) for d in await self._devices.list_for_employee(principal.company_id, oid)]

    async def register(
        self, principal: Principal, employee_id: str, data: DeviceCreate, meta: RequestMeta
    ) -> DeviceRegistered:
        company_id = principal.company_id
        oid = await self._visible_employee_id(principal, employee_id)
        employee = await self._employees.get_by_id(company_id, oid)
        if employee is None or employee.status == EmployeeStatus.TERMINATED:
            raise BadRequestError(
                "Devices cannot be registered for terminated employees.", code="employee_terminated"
            )

        code = generate_enrollment_code()
        device = Device(
            company_id=company_id,
            employee_id=oid,
            name=data.name,
            hostname=data.hostname or None,
            os=data.os,
            os_version=data.os_version or None,
            status=DeviceStatus.PENDING,
            enrollment_code_hash=hash_token(normalise_enrollment_code(code)),
            enrollment_expires_at=utcnow() + timedelta(hours=self._settings.device_enrollment_expire_hours),
            registered_by_user_id=principal.user_id,
        )
        try:
            await self._devices.create(company_id, device)
        except DuplicateKeyError as exc:  # astronomically unlikely code collision
            raise ConflictError(
                "Could not allocate an enrolment code; please retry.", code="enrollment_conflict"
            ) from exc

        await self._audit.record(
            "device.registered",
            company_id=company_id,
            actor_user_id=principal.user_id,
            target_type="device",
            target_id=str(device.id),
            subject_employee_id=oid,
            meta=meta,
            metadata={"employee_id": str(oid), "os": data.os.value},
        )
        return DeviceRegistered(**device_out(device).model_dump(), enrollment_code=code)

    async def revoke(self, principal: Principal, device_id: str, meta: RequestMeta) -> DeviceOut:
        company_id = principal.company_id
        oid = parse_id(device_id, not_found="Device not found.", code="device_not_found")
        device = await self._devices.get_by_id(company_id, oid)
        if device is None or not await self._scopes.can_access(principal, device.employee_id):
            raise NotFoundError("Device not found.", code="device_not_found")
        if device.status == DeviceStatus.REVOKED:
            return device_out(device)
        updated = await self._devices.update_by_id(
            company_id,
            device.id,
            {"status": DeviceStatus.REVOKED, "revoked_at": utcnow(), "enrollment_code_hash": None},
        )
        await self._audit.record(
            "device.revoked",
            company_id=company_id,
            actor_user_id=principal.user_id,
            target_type="device",
            target_id=str(device.id),
            subject_employee_id=device.employee_id,
            meta=meta,
        )
        return device_out(updated or device)

    async def _visible_employee_id(self, principal: Principal, employee_id: str) -> ObjectId:
        oid = parse_id(employee_id, not_found="Employee not found.", code="employee_not_found")
        if not await self._scopes.can_access(principal, oid):
            raise NotFoundError("Employee not found.", code="employee_not_found")
        return oid
