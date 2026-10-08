"""Idempotent start-up tasks: index creation and system role/permission seeding."""

from __future__ import annotations

import logging
from typing import Any

from pymongo.asynchronous.database import AsyncDatabase

from app.auth.permissions import PERMISSION_CATALOG, ROLE_CATALOG
from app.models.organization import Employee
from app.models.role import PermissionDocument, RoleDocument
from app.repositories import ALL_REPOSITORIES
from app.repositories.organization import EmployeeRepository
from app.repositories.role import PermissionRepository, RoleRepository

logger = logging.getLogger(__name__)


class BootstrapService:
    def __init__(self, db: AsyncDatabase[dict[str, Any]]) -> None:
        self._db = db

    async def run(self) -> None:
        for repository in ALL_REPOSITORIES:
            await repository.ensure_indexes(self._db)
        await self._seed_permissions()
        await self._seed_system_roles()
        await self._backfill_employee_records()
        logger.info("Database bootstrap complete (%d collections indexed)", len(ALL_REPOSITORIES))

    async def _seed_permissions(self) -> None:
        repository = PermissionRepository(self._db)
        for info in PERMISSION_CATALOG.values():
            await repository.upsert(
                PermissionDocument(
                    key=info.key.value,
                    name=info.name,
                    description=info.description,
                    category=info.category,
                )
            )

    async def _seed_system_roles(self) -> None:
        repository = RoleRepository(self._db)
        for info in ROLE_CATALOG.values():
            await repository.upsert_system_role(
                RoleDocument(
                    key=info.key.value,
                    name=info.name,
                    description=info.description,
                    level=info.level,
                    permissions=sorted(p.value for p in info.permissions),
                    is_system=True,
                )
            )

    async def _backfill_employee_records(self) -> None:
        """Phase 2 migration: every user gets an employee record (idempotent)."""
        employees = EmployeeRepository(self._db)
        linked = 0
        async for user in self._db["users"].find(
            {"employee_id": None}, {"company_id": 1, "email": 1, "full_name": 1}
        ):
            company_id = user["company_id"]
            existing = await employees.get_by_email(company_id, user["email"])
            if existing is None:
                existing = Employee(
                    company_id=company_id,
                    full_name=user["full_name"],
                    email=user["email"],
                    user_id=user["_id"],
                )
                await employees.create(company_id, existing)
            elif existing.user_id is None:
                await employees.update_by_id(company_id, existing.id, {"user_id": user["_id"]})
            await self._db["users"].update_one({"_id": user["_id"]}, {"$set": {"employee_id": existing.id}})
            linked += 1
        if linked:
            logger.info("Linked %d user(s) to new employee records", linked)
