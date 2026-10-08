from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from app.models.company import Company, CompanyPlan, CompanyStatus
from app.schemas.common import APIModel, Timezone

CompanySize = Literal["1-10", "11-50", "51-200", "201-1000", "1000+"]


class CompanyOut(APIModel):
    id: str
    name: str
    slug: str
    status: CompanyStatus
    plan: CompanyPlan
    timezone: str
    industry: str | None
    size: str | None
    trial_ends_at: datetime | None
    created_at: datetime

    @classmethod
    def from_model(cls, company: Company) -> CompanyOut:
        return cls(
            id=str(company.id),
            name=company.name,
            slug=company.slug,
            status=company.status,
            plan=company.plan,
            timezone=company.timezone,
            industry=company.industry,
            size=company.size,
            trial_ends_at=company.trial_ends_at,
            created_at=company.created_at,
        )


class CompanyUpdate(APIModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    timezone: Timezone | None = None
    industry: str | None = Field(default=None, max_length=80)
    size: CompanySize | None = None
