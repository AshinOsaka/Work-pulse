"""Productivity intelligence API: rules, metrics, scores (with their components) and insights."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.models.productivity import Category, RuleKind, RuleScope
from app.schemas.common import APIModel
from app.schemas.organization import EmployeeRef, Ref

CategoryOrUnclassified = Literal["productive", "neutral", "unproductive", "unclassified"]


# --------------------------------------------------------------------------- rules
class RuleOut(APIModel):
    id: str
    kind: RuleKind
    pattern: str
    category: Category
    scope: RuleScope
    scope_ref: Ref | None
    role: str | None
    note: str | None
    created_at: datetime


class RuleCreate(APIModel):
    kind: RuleKind
    pattern: str = Field(min_length=1, max_length=253)
    category: Category
    scope: RuleScope = RuleScope.COMPANY
    scope_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{24}$")
    role: str | None = Field(default=None, max_length=40)
    note: str | None = Field(default=None, max_length=200)

    @field_validator("pattern")
    @classmethod
    def _normalise(cls, value: str) -> str:
        value = value.strip().lower()
        if value.startswith(("http://", "https://")):
            value = value.split("://", 1)[1]
        value = value.split("/", 1)[0]
        return value.removeprefix("www.") if value.startswith("www.") else value

    @model_validator(mode="after")
    def _scope_target(self) -> RuleCreate:
        if self.scope in (RuleScope.DEPARTMENT, RuleScope.TEAM, RuleScope.PROFILE) and not self.scope_id:
            raise ValueError("Choose the department, team or work profile this rule applies to.")
        if self.scope == RuleScope.ROLE and not self.role:
            raise ValueError("Choose the role this rule applies to.")
        if self.kind == RuleKind.WEBSITE and ("." not in self.pattern or " " in self.pattern):
            raise ValueError("Enter a domain such as example.com.")
        return self


class RuleUpdate(APIModel):
    category: Category | None = None
    note: str | None = Field(default=None, max_length=200)


# --------------------------------------------------------------------------- work profiles (job roles)
class TemplateRule(APIModel):
    kind: RuleKind
    pattern: str
    category: Category


class ProfileTemplateOut(APIModel):
    key: str
    name: str
    description: str
    rules: list[TemplateRule]


class WorkProfileOut(APIModel):
    id: str
    name: str
    description: str | None
    template: str | None
    members: list[EmployeeRef]
    rule_count: int
    created_at: datetime


class WorkProfileCreate(APIModel):
    name: str = Field(min_length=2, max_length=60)
    description: str | None = Field(default=None, max_length=300)
    #: Start from a template's rules (see GET /productivity/profile-templates).
    template: str | None = Field(default=None, max_length=40)


class WorkProfileUpdate(APIModel):
    name: str | None = Field(default=None, min_length=2, max_length=60)
    description: str | None = Field(default=None, max_length=300)


class ProfileMembers(APIModel):
    employee_ids: list[str] = Field(max_length=1000)


class RecommendedResult(APIModel):
    added: int
    skipped: int


class UnclassifiedItem(APIModel):
    kind: Literal["app", "website"]
    key: str
    name: str
    seconds: int
    employees: int


# --------------------------------------------------------------------------- metrics and scores
class MetricsOut(APIModel):
    work_seconds: int
    active_seconds: int
    idle_seconds: int
    extended_idle_seconds: int
    away_seconds: int
    tracked_seconds: int
    productive_seconds: int
    neutral_seconds: int
    unproductive_seconds: int
    unclassified_seconds: int
    focus_sessions: int
    focus_seconds: int
    longest_focus_seconds: int
    context_switches: int
    task_seconds: int
    tasks_completed: int
    tasks_due_open: int


class ScoreComponent(APIModel):
    key: str
    label: str
    seconds: int


class ScoreOut(APIModel):
    key: Literal["activity_score", "productive_share", "focus_score", "work_utilization"]
    label: str
    value: int | None
    status: Literal["ok", "insufficient_data"]
    formula: str
    components: list[ScoreComponent]
    interpretation: str
    reason: str | None = None
    #: Productive share only: % of tracked time covered by rules.
    coverage: int | None = None


class Scores(APIModel):
    activity_score: ScoreOut
    productive_share: ScoreOut
    focus_score: ScoreOut
    work_utilization: ScoreOut


class SummaryLine(APIModel):
    """A headline measurement (e.g. "Active work: 6h 42m"), with the metrics it comes from."""

    key: str
    label: str
    value: str
    metrics: list[str]


class ProjectSignal(APIModel):
    """Work on one project in the period, next to the project's overall progress."""

    id: str
    name: str
    key: str
    color: str
    #: Time logged on the project's tasks in the period (by the people in this report).
    task_seconds: int
    #: Tasks completed in the period (by the people in this report).
    tasks_completed: int
    #: Whole project: completed top-level tasks ÷ all top-level tasks, 0-100.
    progress: int
    total_tasks: int


class TaskCompletion(APIModel):
    available: bool
    reason: str
    value: int | None = None
    formula: str | None = None
    completed: int = 0
    due_open: int = 0
    task_seconds: int = 0
    interpretation: str | None = None


class Insight(APIModel):
    tone: Literal["positive", "info", "attention"]
    title: str
    detail: str
    #: The metrics (keys of MetricsOut) this observation is based on.
    metrics: list[str]


class UsageItemOut(APIModel):
    kind: Literal["app", "website"]
    key: str
    name: str
    seconds: int
    category: CategoryOrUnclassified
    rule_scope: RuleScope | None
    rule_pattern: str | None


class FocusSessionOut(APIModel):
    started_at: datetime
    ended_at: datetime
    seconds: int
    productive_seconds: int
    top_apps: list[str]


class DayMetrics(APIModel):
    day: date
    metrics: MetricsOut
    activity_score: int | None
    productive_share: int | None
    focus_score: int | None
    work_utilization: int | None


class EmployeeProductivity(APIModel):
    employee: EmployeeRef
    #: The work profile (job role) whose rules apply, if any.
    work_profile: Ref | None
    start: date
    end: date
    timezone: str
    totals: MetricsOut
    scores: Scores
    task_completion: TaskCompletion
    days: list[DayMetrics]
    usage: list[UsageItemOut]
    focus_sessions: list[FocusSessionOut]
    summary: list[SummaryLine]
    projects: list[ProjectSignal]
    insights: list[Insight]
    disclaimer: str


class TrendPoint(APIModel):
    start: date
    end: date
    productive_share: int | None
    activity_score: int | None
    #: Null for monthly trends (focus needs per-segment analysis, which is limited to shorter ranges).
    focus_score: int | None
    work_utilization: int | None
    work_seconds: int
    active_seconds: int
    productive_seconds: int
    classified_seconds: int
    focus_seconds: int
    task_seconds: int
    #: People with recorded work in the bucket.
    people: int


class ProductivityTrend(APIModel):
    period: Literal["daily", "weekly", "monthly"]
    timezone: str
    focus_available: bool
    points: list[TrendPoint]


class TeamRow(APIModel):
    employee: EmployeeRef
    team: Ref | None
    work_profile: Ref | None
    metrics: MetricsOut
    activity_score: int | None
    productive_share: int | None
    focus_score: int | None
    work_utilization: int | None


class TeamProductivity(APIModel):
    start: date
    end: date
    timezone: str
    totals: MetricsOut
    scores: Scores
    task_completion: TaskCompletion
    days: list[DayMetrics]
    rows: list[TeamRow]
    summary: list[SummaryLine]
    projects: list[ProjectSignal]
    insights: list[Insight]
    disclaimer: str


class GroupRow(APIModel):
    """One department or team: totals and scores for its people (never a ranking; sorted by name)."""

    group: Ref | None
    people: int
    people_with_data: int
    metrics: MetricsOut
    scores: Scores
    task_completion: int | None


class GroupBreakdown(APIModel):
    by: Literal["department", "team"]
    start: date
    end: date
    timezone: str
    rows: list[GroupRow]
    disclaimer: str
