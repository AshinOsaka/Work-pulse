"""Productivity rules: how applications and websites are categorised, per company, role, department, team or work profile."""

from __future__ import annotations

from enum import StrEnum

from app.models.base import PyObjectId, TenantModel


class Category(StrEnum):
    PRODUCTIVE = "productive"
    NEUTRAL = "neutral"
    UNPRODUCTIVE = "unproductive"


class RuleKind(StrEnum):
    APP = "app"
    WEBSITE = "website"


class RuleScope(StrEnum):
    COMPANY = "company"
    ROLE = "role"
    DEPARTMENT = "department"
    TEAM = "team"
    #: A work profile (job role such as Developer or Accountant) assigned to employees.
    PROFILE = "profile"


#: More specific scopes win. A work profile describes the person's own job, so it is the most specific:
#: profile > team > department > permission role > company.
SCOPE_PRECEDENCE = {
    RuleScope.COMPANY: 1,
    RuleScope.ROLE: 2,
    RuleScope.DEPARTMENT: 3,
    RuleScope.TEAM: 4,
    RuleScope.PROFILE: 5,
}


class ProductivityRule(TenantModel):
    kind: RuleKind
    #: App: executable ("code.exe") or display name, lower case. Website: a domain; it also matches subdomains.
    pattern: str
    category: Category
    scope: RuleScope = RuleScope.COMPANY
    #: Department or team id for those scopes.
    scope_id: PyObjectId | None = None
    #: Permission role key for the role scope (e.g. "MANAGER").
    role: str | None = None
    note: str | None = None
    created_by: PyObjectId | None = None


class WorkProfile(TenantModel):
    """A job role with its own activity context (e.g. Developer, Designer, Accountant).

    Employees are assigned to at most one profile; rules scoped to the profile apply to them. This is
    separate from permission roles (Employee, Manager, …), which say what someone may do in WorkPulse.
    """

    name: str
    description: str | None = None
    #: The template it was created from, if any (informational).
    template: str | None = None
    created_by: PyObjectId | None = None
