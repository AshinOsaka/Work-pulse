from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from app.models.company import Company, CompanyPlan, CompanyStatus
from app.schemas.common import APIModel, Timezone

CompanySize = Literal["1-10", "11-50", "51-200", "201-1000", "1000+"]
ServiceType = Literal["visa", "ticketing", "insurance", "forex"]


class CustomerSystemIO(APIModel):
    """A customer-facing system (CRM, ticketing, telephony): an application or a website domain."""

    label: str = Field(min_length=1, max_length=60)
    kind: Literal["app", "website"] = "website"
    pattern: str = Field(min_length=1, max_length=120)
    #: Departments (id strings) for grouping and filtering; empty means "All departments". It does not affect
    #: customer-time crediting.
    department_ids: list[str] = Field(default_factory=list, max_length=50)
    #: Line of business (visa, ticketing, insurance, forex) for grouping and filtering; optional.
    service_type: ServiceType | None = None

    @model_validator(mode="before")
    @classmethod
    def _accept_single_department(cls, data: Any) -> Any:
        """Accept the older single ``department_id`` field from clients that still send it."""
        if isinstance(data, dict) and "department_id" in data:
            data = dict(data)
            legacy = data.pop("department_id")
            if legacy and not data.get("department_ids"):
                data["department_ids"] = [legacy]
        return data


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
    #: Required working minutes per weekday, Monday first (7 values; 0 = no requirement). Attendance only.
    required_minutes: list[int]
    #: Logged meeting time per person per day that counts without approval (0 = always ask).
    time_claim_auto_minutes: int
    #: Start-of-day check: alert when a computer hasn't reported by the start time plus the grace minutes.
    start_check_enabled: bool
    start_check_time: str
    start_check_grace_minutes: int
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
            required_minutes=_seven(company.required_minutes),
            time_claim_auto_minutes=company.time_claim_auto_minutes,
            start_check_enabled=company.start_check_enabled,
            start_check_time=company.start_check_time,
            start_check_grace_minutes=company.start_check_grace_minutes,
            customer_systems=[
                CustomerSystemIO(
                    label=s.label,
                    kind=s.kind,
                    pattern=s.pattern,
                    department_ids=list(s.department_ids),
                    service_type=s.service_type,
                )
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
    #: Required working minutes per weekday, Monday first: exactly 7 values from 0 to 1440.
    required_minutes: list[int] | None = Field(default=None, min_length=7, max_length=7)
    #: Logged meeting time per person per day that counts without approval: 0 to 12 hours, in minutes.
    time_claim_auto_minutes: int | None = Field(default=None, ge=0, le=720)
    start_check_enabled: bool | None = None
    #: The workday start, "HH:MM" in the company's time zone.
    start_check_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    start_check_grace_minutes: int | None = Field(default=None, ge=5, le=240)
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

    @field_validator("required_minutes")
    @classmethod
    def _validate_required_minutes(cls, value: list[int] | None) -> list[int] | None:
        if value is not None and any(m < 0 or m > 1440 for m in value):
            raise ValueError("required_minutes must be 7 values from 0 to 1440 minutes.")
        return value

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
            cleaned.append(
                CustomerSystemIO(
                    label=system.label.strip(),
                    kind=system.kind,
                    pattern=pattern,
                    # De-duplicated, order kept; empty = all departments.
                    department_ids=list(dict.fromkeys(d for d in system.department_ids if d)),
                    service_type=system.service_type,
                )
            )
        return cleaned


def _seven(values: list[int]) -> list[int]:
    """Exactly seven weekday values (older records may be shorter or missing)."""
    return (list(values) + [0] * 7)[:7]


def _normalise_pattern(kind: str, pattern: str) -> str:
    """App: lower-cased executable/display name. Website: bare host (no scheme, path, port or leading www.)."""
    text = pattern.strip().lower()
    if kind == "app":
        return text
    text = text.split("//")[-1].split("/")[0].split("?")[0].split(":")[0]
    return text[4:] if text.startswith("www.") else text
