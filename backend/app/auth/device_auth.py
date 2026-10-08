"""Authentication for desktop-agent requests (device tokens, not user tokens)."""

from __future__ import annotations

from typing import Annotated, Any

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pymongo.asynchronous.database import AsyncDatabase

from app.core.config import Settings
from app.core.dependencies import DbDep, SettingsDep
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import decode_device_token
from app.models.company import Company
from app.models.organization import Device, DeviceStatus, Employee, EmployeeStatus
from app.models.user import UserStatus
from app.repositories.company import CompanyRepository
from app.repositories.organization import DeviceRepository, EmployeeRepository
from app.repositories.user import UserRepository
from app.services.agent_service import DeviceContext

_bearer = HTTPBearer(auto_error=False, description="Device access token from POST /agent/token")


async def resolve_device(token: str, settings: Settings, db: AsyncDatabase[dict[str, Any]]) -> DeviceContext:
    """Validate a device token and load the device and employee (shared by HTTP and WebSocket)."""
    claims = decode_device_token(token, settings)
    try:
        company_id, device_id = ObjectId(claims.company_id), ObjectId(claims.device_id)
    except (InvalidId, TypeError) as exc:
        raise UnauthorizedError("Invalid device token.", code="invalid_token") from exc

    # Re-checked on every request: revoking a device or terminating an employee takes effect immediately.
    # One round trip: the device with its employee, the employee's account status and the workspace.
    rows = await (
        await db[DeviceRepository.collection_name].aggregate(
            [
                {"$match": {"_id": device_id, "company_id": company_id}},
                {"$limit": 1},
                {
                    "$lookup": {
                        "from": EmployeeRepository.collection_name,
                        "localField": "employee_id",
                        "foreignField": "_id",
                        "as": "_employee",
                    }
                },
                {
                    "$lookup": {
                        "from": UserRepository.collection_name,
                        "localField": "_employee.user_id",
                        "foreignField": "_id",
                        "pipeline": [{"$project": {"status": 1, "company_id": 1}}],
                        "as": "_user",
                    }
                },
                {
                    "$lookup": {
                        "from": CompanyRepository.collection_name,
                        "localField": "company_id",
                        "foreignField": "_id",
                        "as": "_company",
                    }
                },
            ]
        )
    ).to_list()
    if not rows:
        raise UnauthorizedError("This device has been revoked.", code="device_revoked")
    row = rows[0]
    employees, users, companies = row.pop("_employee"), row.pop("_user"), row.pop("_company")
    device = Device.from_document(row)
    if device.status != DeviceStatus.ACTIVE:
        raise UnauthorizedError("This device has been revoked.", code="device_revoked")
    employee = Employee.from_document(employees[0]) if employees else None
    if employee is None or employee.company_id != company_id or employee.status == EmployeeStatus.TERMINATED:
        raise ForbiddenError("This employee is no longer active.", code="employee_terminated")
    if employee.user_id:
        user = users[0] if users else None
        if (
            user is None
            or user.get("company_id") != company_id
            or user.get("status") in (UserStatus.SUSPENDED, UserStatus.DEACTIVATED)
        ):
            raise ForbiddenError("This account is not active.", code="account_not_active")
    company = Company.from_document(companies[0]) if companies else None
    if company is None:
        raise UnauthorizedError("Workspace no longer exists.", code="company_not_found")
    return DeviceContext(device=device, employee=employee, company=company)


async def get_current_device(
    settings: SettingsDep,
    db: DbDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> DeviceContext:
    if credentials is None:
        raise UnauthorizedError("Device authentication required.", code="not_authenticated")
    return await resolve_device(credentials.credentials, settings, db)


CurrentDevice = Annotated[DeviceContext, Depends(get_current_device)]
