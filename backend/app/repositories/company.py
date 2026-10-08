from __future__ import annotations

from pymongo import ASCENDING, DESCENDING, IndexModel

from app.models.company import Company
from app.repositories.base import GlobalRepository


class CompanyRepository(GlobalRepository[Company]):
    collection_name = "companies"
    model = Company
    indexes = (
        IndexModel([("slug", ASCENDING)], name="uniq_slug", unique=True),
        IndexModel([("status", ASCENDING)], name="status"),
        IndexModel([("created_at", DESCENDING)], name="created_at"),
    )

    async def get_by_slug(self, slug: str) -> Company | None:
        return await self._find_one({"slug": slug})

    async def slug_exists(self, slug: str) -> bool:
        return await self._count({"slug": slug}) > 0

    async def active_companies(self) -> list[Company]:
        """Workspaces that aren't suspended (for background jobs that serve every tenant)."""
        return await self._find_many(
            {"status": {"$ne": "suspended"}}, sort=[("created_at", ASCENDING)], limit=100_000
        )
