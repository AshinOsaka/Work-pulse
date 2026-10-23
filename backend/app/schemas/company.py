from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import Field, field_validator

from app.models.company import Company, CompanyPlan, CompanyStatus
from app.schemas.common import APIModel, Timezone

CompanySize = Literal["1-10", "11-50", "51-200", "201-1000", "1000+"]


class CustomerSystemIO(APIModel):
    """A customer-facing system (CRM, ticketing, telephony): an application or a website domain."""

    label: str = Field(min_length=1, max_length=60)
    kind: Literal["app", "website"] = "website"
    pattern: str = Field(min_length=1, max_length=120)


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
    #: ISO weekdays that count as working days (Monday = 1 … Sunday = 7).
    work_days: list[int]
    #: Holiday dates ("YYYY-MM-DD") on top of the weekly non-working days.
    holidays: list[str]
    #: Customer-facing systems (CRM, ticketing, telephony); foreground time in them is reported as customer time.
    customer_systems: list[CustomerSystemIO]

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
            work_days=company.work_days,
            holidays=company.holidays,
            customer_systems=[
                CustomerSystemIO(label=s.label, kind=s.kind, pattern=s.pattern)
                for s in company.customer_systems
            ],
        )


class CompanyUpdate(APIModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    timezone: Timezone | None = None
    industry: str | None = Field(default=None, max_length=80)
    size: CompanySize | None = None
    #: ISO weekdays (Monday = 1 … Sunday = 7); at least one. For a 6-day week with Sunday off: [1, 2, 3, 4, 5, 6].
    work_days: list[int] | None = Field(default=None, max_length=7)
    holidays: list[str] | None = Field(default=None, max_length=200)
    #: Customer-facing systems (CRM, ticketing, telephony). Patterns are normalised and de-duplicated.
    customer_systems: list[CustomerSystemIO] | None = Field(default=None, max_length=50)

    @field_validator("work_days")
    @classmethod
    def _validate_work_days(cls, value: list[int] | None) -> list[int] | None:
        if value is None:
            return None
        days = sorted(set(value))
        if not days or any(d < 1 or d > 7 for d in days):
            raise ValueError(
                "work_days must be ISO weekdays from 1 (Monday) to 7 (Sunday), and at least one."
            )
        return days

    @field_validator("holidays")
    @classmethod
    def _validate_holidays(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        parsed: set[str] = set()
        for item in value:
            try:
                parsed.add(date.fromisoformat(item).isoformat())
            except ValueError as exc:
                raise ValueError(f"Invalid holiday date {item!r}; use YYYY-MM-DD.") from exc
        return sorted(parsed)

    @field_validator("customer_systems")
    @classmethod
    def _validate_customer_systems(
        cls, value: list[CustomerSystemIO] | None
    ) -> list[CustomerSystemIO] | None:
        if value is None:
            return None
        seen: set[tuple[str, str]] = set()
        cleaned: list[CustomerSystemIO] = []
        for system in value:
            pattern = _normalise_pattern(system.kind, system.pattern)
            if not pattern:
                raise ValueError(f"Invalid {system.kind} pattern {system.pattern!r}.")
            key = (system.kind, pattern)
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(CustomerSystemIO(label=system.label.strip(), kind=system.kind, pattern=pattern))
        return cleaned


def _normalise_pattern(kind: str, pattern: str) -> str:
    """App: lower-cased executable/display name. Website: bare host (no scheme, path, port or leading www.)."""
    text = pattern.strip().lower()
    if kind == "app":
        return text
    text = text.split("//")[-1].split("/")[0].split("?")[0].split(":")[0]
    return text[4:] if text.startswith("www.") else text
