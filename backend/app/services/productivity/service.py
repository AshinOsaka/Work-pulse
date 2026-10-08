"""Productivity intelligence: rule management and the employee and team reports."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.auth.permissions import Permission
from app.auth.principal import Principal
from app.core.config import Settings
from app.core.exceptions import BadRequestError, ConflictError, NotFoundError
from app.models.agent import WorkSession
from app.models.company import Company
from app.models.organization import Employee, EmployeeStatus
from app.models.productivity import ProductivityRule, RuleScope, WorkProfile
from app.models.work import TaskStatus
from app.repositories.activity import ActivityDailyRepository, ActivitySegmentRepository
from app.repositories.agent import WorkSessionRepository
from app.repositories.company import CompanyRepository
from app.repositories.organization import (
    DepartmentRepository,
    DeviceRepository,
    EmployeeRepository,
    TeamRepository,
)
from app.repositories.productivity import (
    ProductivityRuleRepository,
    WebsiteDailyRepository,
    WorkProfileRepository,
)
from app.repositories.user import UserRepository
from app.repositories.work import ProjectRepository, TaskRepository, TimeEntryRepository
from app.schemas.organization import Ref
from app.schemas.productivity import (
    DayMetrics,
    EmployeeProductivity,
    FocusSessionOut,
    GroupBreakdown,
    GroupRow,
    Insight,
    MetricsOut,
    ProductivityTrend,
    ProfileMembers,
    ProfileTemplateOut,
    ProjectSignal,
    RecommendedResult,
    RuleCreate,
    RuleOut,
    RuleUpdate,
    ScoreOut,
    Scores,
    SummaryLine,
    TaskCompletion,
    TeamProductivity,
    TeamRow,
    TemplateRule,
    TrendPoint,
    UnclassifiedItem,
    UsageItemOut,
    WorkProfileCreate,
    WorkProfileOut,
    WorkProfileUpdate,
)
from app.services.access_scope import AccessScopeService
from app.services.audit_service import AuditService
from app.services.context import RequestMeta
from app.services.employee_service import employee_ref
from app.services.helpers import parse_id, parse_ref
from app.services.productivity.day_cache import DayResult, ProductivityDayRepository
from app.services.productivity.engine import (
    FocusSession,
    Metrics,
    Segment,
    UsageItem,
    activity_score,
    category_time,
    classify_segments,
    context_switches,
    day_bounds,
    focus_score,
    focus_sessions,
    insights,
    local_days,
    productive_share,
    summary,
    task_completion,
    time_accounting,
    work_utilization,
)
from app.services.productivity.rules import (
    PROFILE_TEMPLATES,
    RECOMMENDED_RULES,
    TEMPLATES_BY_KEY,
    UNCLASSIFIED,
    EmployeeContext,
    RuleBook,
)
from app.services.work_sessions import effective_ends
from app.utils.time import utcnow

MAX_RANGE_DAYS = 31
#: Long analytics loops yield to the event loop this often, so one large report does not stall other requests on the
#: same process (QA load test: "My work" waited up to 9 s behind 1,000-person team views).
YIELD_EVERY = 25
MAX_SEGMENTS = 300_000
DISCLAIMER = (
    "These figures describe recorded computer activity under your workspace's rules. They are context for a "
    "conversation, not a measure of anyone's performance: meetings, calls, thinking and offline work are "
    "invisible to them, and the categories depend on how the rules are set up."
)


@dataclass
class EmployeeData:
    days: dict[date, Metrics]
    items: dict[tuple[str, str], UsageItem] = field(default_factory=dict)
    focus: list[FocusSession] = field(default_factory=list)

    @property
    def totals(self) -> Metrics:
        total = Metrics()
        for m in self.days.values():
            total.add(m)
        return total


def _metrics_out(m: Metrics) -> MetricsOut:
    return MetricsOut(**m.as_dict())


def _scores(m: Metrics) -> Scores:
    return Scores(
        activity_score=ScoreOut(**activity_score(m)),
        productive_share=ScoreOut(**productive_share(m)),
        focus_score=ScoreOut(**focus_score(m)),
        work_utilization=ScoreOut(**work_utilization(m)),
    )


def _summary(m: Metrics) -> list[SummaryLine]:
    return [SummaryLine(**line) for line in summary(m)]


def _day_rows(days: dict[date, Metrics]) -> list[DayMetrics]:
    return [
        DayMetrics(
            day=day,
            metrics=_metrics_out(m),
            activity_score=activity_score(m)["value"],
            productive_share=productive_share(m)["value"],
            focus_score=focus_score(m)["value"],
            work_utilization=work_utilization(m)["value"],
        )
        for day, m in sorted(days.items())
    ]


def _usage(items: dict[tuple[str, str], UsageItem], limit: int = 60) -> list[UsageItemOut]:
    ranked = sorted(items.values(), key=lambda i: -i.seconds)[:limit]
    return [
        UsageItemOut(
            kind=i.kind,
            key=i.key,
            name=i.name,
            seconds=round(i.seconds),
            category=i.category,
            rule_scope=RuleScope(i.rule_scope) if i.rule_scope else None,
            rule_pattern=i.rule_pattern,
        )
        for i in ranked
        if i.seconds >= 30
    ]


class ProductivityService:
    def __init__(
        self,
        *,
        companies: CompanyRepository,
        employees: EmployeeRepository,
        departments: DepartmentRepository,
        teams: TeamRepository,
        users: UserRepository,
        rules: ProductivityRuleRepository,
        sessions: WorkSessionRepository,
        daily: ActivityDailyRepository,
        websites: WebsiteDailyRepository,
        segments: ActivitySegmentRepository,
        tasks: TaskRepository,
        time_entries: TimeEntryRepository,
        projects: ProjectRepository,
        profiles: WorkProfileRepository,
        devices: DeviceRepository,
        settings: Settings,
        scopes: AccessScopeService,
        audit: AuditService,
    ) -> None:
        self._companies = companies
        self._employees = employees
        self._departments = departments
        self._teams = teams
        self._users = users
        self._rules = rules
        self._sessions = sessions
        self._daily = daily
        # Derived results cache (same database as the rollups it summarises).
        self._day_cache = ProductivityDayRepository(daily._db)
        self._websites = websites
        self._segments = segments
        self._devices = devices
        self._tasks = tasks
        self._time = time_entries
        self._projects = projects
        self._profiles = profiles
        self._settings = settings
        self._scopes = scopes
        self._audit = audit

    async def _company(self, company_id: ObjectId) -> Company:
        company = await self._companies.get_by_id(company_id)
        if company is None:
            raise NotFoundError("Workspace not found.")
        return company

    # ------------------------------------------------------------------ rules
    async def _rule_out(self, company_id: ObjectId, rules: list[ProductivityRule]) -> list[RuleOut]:
        departments = await self._departments.find_by_ids(
            company_id, [r.scope_id for r in rules if r.scope == RuleScope.DEPARTMENT and r.scope_id]
        )
        teams = await self._teams.find_by_ids(
            company_id, [r.scope_id for r in rules if r.scope == RuleScope.TEAM and r.scope_id]
        )
        profiles = await self._profiles.find_by_ids(
            company_id, [r.scope_id for r in rules if r.scope == RuleScope.PROFILE and r.scope_id]
        )
        out = []
        for r in rules:
            target: Any = None
            if r.scope_id is not None and r.scope == RuleScope.DEPARTMENT:
                target = departments.get(r.scope_id)
            elif r.scope_id is not None and r.scope == RuleScope.TEAM:
                target = teams.get(r.scope_id)
            elif r.scope_id is not None and r.scope == RuleScope.PROFILE:
                target = profiles.get(r.scope_id)
            out.append(
                RuleOut(
                    id=str(r.id),
                    kind=r.kind,
                    pattern=r.pattern,
                    category=r.category,
                    scope=r.scope,
                    scope_ref=Ref(id=str(target.id), name=target.name) if target else None,
                    role=r.role,
                    note=r.note,
                    created_at=r.created_at,
                )
            )
        return out

    async def list_rules(self, principal: Principal) -> list[RuleOut]:
        return await self._rule_out(
            principal.company_id, await self._rules.all_for_company(principal.company_id)
        )

    async def create_rule(self, principal: Principal, data: RuleCreate, meta: RequestMeta) -> RuleOut:
        scope_id = (
            parse_ref(data.scope_id, "scope_id")
            if data.scope in (RuleScope.DEPARTMENT, RuleScope.TEAM, RuleScope.PROFILE)
            else None
        )
        if scope_id is not None:
            repo: Any = {
                RuleScope.DEPARTMENT: self._departments,
                RuleScope.TEAM: self._teams,
                RuleScope.PROFILE: self._profiles,
            }[data.scope]
            if await repo.get_by_id(principal.company_id, scope_id) is None:
                label = "Work profile" if data.scope == RuleScope.PROFILE else data.scope.value.title()
                raise BadRequestError(f"{label} not found.", code="invalid_reference")
        rule = ProductivityRule(
            company_id=principal.company_id,
            kind=data.kind,
            pattern=data.pattern,
            category=data.category,
            scope=data.scope,
            scope_id=scope_id,
            role=data.role if data.scope == RuleScope.ROLE else None,
            note=data.note,
            created_by=principal.user_id,
        )
        try:
            await self._rules.create(principal.company_id, rule)
        except DuplicateKeyError as exc:
            raise ConflictError("A rule for this item and scope already exists.", code="rule_exists") from exc
        await self._audit_rule("productivity.rule_created", principal, rule, meta)
        return (await self._rule_out(principal.company_id, [rule]))[0]

    async def update_rule(
        self, principal: Principal, rule_id: str, data: RuleUpdate, meta: RequestMeta
    ) -> RuleOut:
        oid = parse_id(rule_id, not_found="Rule not found.", code="rule_not_found")
        changes = data.model_dump(exclude_unset=True)
        rule = (
            await self._rules.update_by_id(principal.company_id, oid, changes)
            if changes
            else await self._rules.get_by_id(principal.company_id, oid)
        )
        if rule is None:
            raise NotFoundError("Rule not found.", code="rule_not_found")
        await self._audit_rule("productivity.rule_updated", principal, rule, meta)
        return (await self._rule_out(principal.company_id, [rule]))[0]

    async def delete_rule(self, principal: Principal, rule_id: str, meta: RequestMeta) -> None:
        oid = parse_id(rule_id, not_found="Rule not found.", code="rule_not_found")
        rule = await self._rules.get_by_id(principal.company_id, oid)
        if rule is None or not await self._rules.delete_by_id(principal.company_id, oid):
            raise NotFoundError("Rule not found.", code="rule_not_found")
        await self._audit_rule("productivity.rule_deleted", principal, rule, meta)

    async def load_recommended(self, principal: Principal, meta: RequestMeta) -> RecommendedResult:
        existing = {
            (r.kind, r.pattern)
            for r in await self._rules.all_for_company(principal.company_id)
            if r.scope == RuleScope.COMPANY
        }
        added = 0
        for kind, pattern, category in RECOMMENDED_RULES:
            if (kind, pattern) in existing:
                continue
            await self._rules.create(
                principal.company_id,
                ProductivityRule(
                    company_id=principal.company_id,
                    kind=kind,
                    pattern=pattern,
                    category=category,
                    created_by=principal.user_id,
                    note="Recommended starting point",
                ),
            )
            added += 1
        await self._audit.record(
            "productivity.recommended_rules_loaded",
            company_id=principal.company_id,
            actor_user_id=principal.user_id,
            target_type="company",
            target_id=str(principal.company_id),
            meta=meta,
            metadata={"added": added},
        )
        return RecommendedResult(added=added, skipped=len(RECOMMENDED_RULES) - added)

    async def _audit_rule(
        self, action: str, principal: Principal, rule: ProductivityRule, meta: RequestMeta
    ) -> None:
        await self._audit.record(
            action,
            company_id=principal.company_id,
            actor_user_id=principal.user_id,
            target_type="productivity_rule",
            target_id=str(rule.id),
            meta=meta,
            metadata={
                "kind": rule.kind.value,
                "pattern": rule.pattern,
                "category": rule.category.value,
                "scope": rule.scope.value,
            },
        )

    # ------------------------------------------------------------------ work profiles (job roles)
    @staticmethod
    def templates() -> list[ProfileTemplateOut]:
        return [
            ProfileTemplateOut(
                key=t.key,
                name=t.name,
                description=t.description,
                rules=[TemplateRule(kind=k, pattern=p, category=c) for k, p, c in t.rules],
            )
            for t in PROFILE_TEMPLATES
        ]

    async def _profiles_out(self, company_id: ObjectId, profiles: list[WorkProfile]) -> list[WorkProfileOut]:
        ids = [p.id for p in profiles]
        members = await self._employees.find_many(
            company_id,
            {"work_profile_id": {"$in": ids}, "status": {"$ne": EmployeeStatus.TERMINATED}},
            sort=[("full_name", 1)],
            limit=10_000,
        )
        counts = await self._rules.count_by_scope_id(company_id, RuleScope.PROFILE)
        return [
            WorkProfileOut(
                id=str(p.id),
                name=p.name,
                description=p.description,
                template=p.template,
                members=[employee_ref(e) for e in members if e.work_profile_id == p.id],
                rule_count=counts.get(p.id, 0),
                created_at=p.created_at,
            )
            for p in profiles
        ]

    async def list_profiles(self, principal: Principal) -> list[WorkProfileOut]:
        return await self._profiles_out(
            principal.company_id, await self._profiles.all_for_company(principal.company_id)
        )

    async def _profile(self, principal: Principal, profile_id: str) -> WorkProfile:
        oid = parse_id(profile_id, not_found="Work profile not found.", code="profile_not_found")
        profile = await self._profiles.get_by_id(principal.company_id, oid)
        if profile is None:
            raise NotFoundError("Work profile not found.", code="profile_not_found")
        return profile

    async def _audit_profile(
        self, action: str, principal: Principal, profile: WorkProfile, meta: RequestMeta, **extra: Any
    ) -> None:
        await self._audit.record(
            action,
            company_id=principal.company_id,
            actor_user_id=principal.user_id,
            target_type="work_profile",
            target_id=str(profile.id),
            meta=meta,
            metadata={"name": profile.name, **extra},
        )

    async def create_profile(
        self, principal: Principal, data: WorkProfileCreate, meta: RequestMeta
    ) -> WorkProfileOut:
        template = TEMPLATES_BY_KEY.get(data.template) if data.template else None
        if data.template and template is None:
            raise BadRequestError("Unknown template.", code="invalid_template")
        profile = WorkProfile(
            company_id=principal.company_id,
            name=data.name.strip(),
            description=data.description or (template.description if template else None),
            template=template.key if template else None,
            created_by=principal.user_id,
        )
        try:
            await self._profiles.create(principal.company_id, profile)
        except DuplicateKeyError as exc:
            raise ConflictError(
                "A work profile with this name already exists.", code="profile_exists"
            ) from exc
        for kind, pattern, category in template.rules if template else ():
            await self._rules.create(
                principal.company_id,
                ProductivityRule(
                    company_id=principal.company_id,
                    kind=kind,
                    pattern=pattern,
                    category=category,
                    scope=RuleScope.PROFILE,
                    scope_id=profile.id,
                    note=f"From the {template.name} template" if template else None,
                    created_by=principal.user_id,
                ),
            )
        await self._audit_profile(
            "productivity.profile_created",
            principal,
            profile,
            meta,
            template=profile.template,
            rules=len(template.rules) if template else 0,
        )
        return (await self._profiles_out(principal.company_id, [profile]))[0]

    async def update_profile(
        self, principal: Principal, profile_id: str, data: WorkProfileUpdate, meta: RequestMeta
    ) -> WorkProfileOut:
        profile = await self._profile(principal, profile_id)
        changes = {k: v for k, v in data.model_dump(exclude_unset=True).items() if k != "name" or v}
        if changes.get("name"):
            changes["name"] = changes["name"].strip()
        if changes:
            try:
                profile = (
                    await self._profiles.update_by_id(principal.company_id, profile.id, changes) or profile
                )
            except DuplicateKeyError as exc:
                raise ConflictError(
                    "A work profile with this name already exists.", code="profile_exists"
                ) from exc
            await self._audit_profile(
                "productivity.profile_updated", principal, profile, meta, fields=sorted(changes)
            )
        return (await self._profiles_out(principal.company_id, [profile]))[0]

    async def delete_profile(self, principal: Principal, profile_id: str, meta: RequestMeta) -> None:
        """Removes the profile and its rules; its members fall back to their other rules."""
        profile = await self._profile(principal, profile_id)
        await self._employees.set_work_profile(principal.company_id, profile.id, [])
        removed = await self._rules.delete_for_scope(principal.company_id, RuleScope.PROFILE, profile.id)
        await self._profiles.delete_by_id(principal.company_id, profile.id)
        await self._audit_profile(
            "productivity.profile_deleted", principal, profile, meta, rules_removed=removed
        )

    async def set_profile_members(
        self, principal: Principal, profile_id: str, data: ProfileMembers, meta: RequestMeta
    ) -> WorkProfileOut:
        profile = await self._profile(principal, profile_id)
        ids = [parse_ref(raw, "employee_ids") for raw in data.employee_ids]
        wanted = [i for i in dict.fromkeys(ids) if i is not None]
        found = await self._employees.find_by_ids(principal.company_id, wanted)
        if len(found) != len(wanted):
            raise BadRequestError("Some employees were not found.", code="invalid_reference")
        await self._employees.set_work_profile(principal.company_id, profile.id, wanted)
        await self._audit_profile(
            "productivity.profile_members_changed", principal, profile, meta, members=len(wanted)
        )
        return (await self._profiles_out(principal.company_id, [profile]))[0]

    # ------------------------------------------------------------------ data
    @staticmethod
    def _range(start: date, end: date) -> None:
        if end < start:
            raise BadRequestError("The end date must not be before the start date.", code="invalid_range")
        if (end - start).days >= MAX_RANGE_DAYS:
            raise BadRequestError(f"Choose a period of at most {MAX_RANGE_DAYS} days.", code="range_too_long")

    async def _contexts(
        self, company_id: ObjectId, employees: list[Employee]
    ) -> dict[ObjectId, EmployeeContext]:
        users = await self._users.find_by_ids(company_id, [e.user_id for e in employees if e.user_id])
        return {
            e.id: EmployeeContext(
                department_id=e.department_id,
                team_id=e.team_id,
                role=(users[e.user_id].role.value if e.user_id and e.user_id in users else None),
                profile_id=e.work_profile_id,
            )
            for e in employees
        }

    async def compute(
        self, company: Company, employees: list[Employee], start: date, end: date, *, with_segments: bool
    ) -> dict[ObjectId, EmployeeData]:
        """Per-employee daily metrics, usage and focus for a period (used by reports)."""
        return await self._compute(company, employees, start, end, with_segments=with_segments)

    async def project_signals(
        self, company: Company, ids: list[ObjectId], start: date, end: date
    ) -> list[ProjectSignal]:
        return await self._project_signals(company, ids, start, end)

    async def _compute(
        self,
        company: Company,
        employees: list[Employee],
        start: date,
        end: date,
        *,
        with_segments: bool = True,
    ) -> dict[ObjectId, EmployeeData]:
        tz = ZoneInfo(company.timezone)
        days = local_days(start, end)
        lo, hi = day_bounds(start, tz)[0], day_bounds(end, tz)[1]
        ids = [e.id for e in employees]
        if not ids:
            return {}
        now = utcnow()
        rules = await self._rules.all_for_company(company.id)
        contexts = await self._contexts(company.id, employees)

        books = {e.id: RuleBook(rules, contexts[e.id]) for e in employees}
        per_day, fresh, fps = await self._day_results(
            company, employees, books, days, tz, now, with_segments=with_segments
        )
        times, settled = await self._time_results(company, ids, days, tz, now, per_day)
        # One write per new entry (time included); existing entries only get their newly settled time.
        today = now.astimezone(tz).date()
        await self._day_cache.store(
            company.id, [(e, d, fps[e], per_day[(e, d)]) for (e, d) in fresh if d <= today]
        )
        await self._day_cache.store_time(
            company.id, [row for row in settled if (row[0], row[1]) not in fresh]
        )

        task_days_by_person: dict[ObjectId, list[tuple[date, tuple[float, int, int]]]] = defaultdict(list)
        for (emp, day), values in (await self._task_days(company, ids, lo, hi, tz, now)).items():
            task_days_by_person[emp].append((day, values))
        result: dict[ObjectId, EmployeeData] = {}
        for _n, employee in enumerate(employees):
            if _n % YIELD_EVERY == YIELD_EVERY - 1:
                await asyncio.sleep(0)  # let other requests run: this loop is CPU-bound
            data = EmployeeData(days={day: times.get((employee.id, day)) or Metrics() for day in days})
            for day, values in task_days_by_person.get(employee.id, []):
                if day in data.days:
                    m = data.days[day]
                    m.task_seconds, m.tasks_completed, m.tasks_due_open = values
            for day in days:
                r = per_day.get((employee.id, day))
                if r is None:
                    continue
                m = data.days[day]
                m.productive, m.neutral, m.unproductive, m.unclassified = (
                    r.productive,
                    r.neutral,
                    r.unproductive,
                    r.unclassified,
                )
                for item in r.items:
                    merged = data.items.setdefault(
                        (item.kind, item.key),
                        UsageItem(
                            item.kind,
                            item.key,
                            item.name,
                            0.0,
                            item.category,
                            item.rule_scope,
                            item.rule_pattern,
                        ),
                    )
                    merged.seconds += item.seconds
                if with_segments:
                    m.focus_count = r.focus_count
                    m.focus_seconds = r.focus_seconds
                    m.longest_focus_seconds = r.longest_focus_seconds
                    m.context_switches = r.context_switches
                    data.focus.extend(r.focus)
            result[employee.id] = data
        return result

    async def _time_results(
        self,
        company: Company,
        ids: list[ObjectId],
        days: list[date],
        tz: ZoneInfo,
        now: datetime,
        per_day: dict[tuple[ObjectId, date], DayResult],
    ) -> tuple[
        dict[tuple[ObjectId, date], Metrics],
        list[tuple[ObjectId, date, tuple[float, float, float, float, float]]],
    ]:
        """Work, active, idle and away time per person and day, reusing cached past days.

        A past day is cached only once none of the person's sessions touching it is still open (an unclosed
        session's effective end can still move), so cached values never change underneath a report.
        """
        out: dict[tuple[ObjectId, date], Metrics] = {}
        need: dict[ObjectId, list[date]] = defaultdict(list)
        for emp in ids:
            for day in days:
                cached = per_day.get((emp, day))
                if cached is not None and cached.time is not None:
                    w, a, i, x, aw = cached.time
                    out[(emp, day)] = Metrics(work=w, active=a, idle=i, extended_idle=x, away=aw)
                else:
                    need[emp].append(day)
        if not need:
            return out, []
        first = min(d for ds in need.values() for d in ds)
        last = max(d for ds in need.values() for d in ds)
        lo, hi = day_bounds(first, tz)[0], day_bounds(last, tz)[1]
        overlapping = await self._sessions.overlapping(company.id, list(need), lo, hi)
        sessions: dict[ObjectId, list[WorkSession]] = defaultdict(list)
        for s in overlapping:
            sessions[s.employee_id].append(s)
        open_sessions = [s for s in overlapping if s.ended_at is None]
        open_devices = list({s.device_id for s in open_sessions})
        devices = await self._devices.find_by_ids(company.id, open_devices) if open_devices else {}
        evidence = await self._segments.last_activity(
            company.id, [s.client_session_id for s in open_sessions]
        )
        open_ends = effective_ends(
            overlapping, devices, now, timedelta(seconds=self._settings.agent_offline_after_seconds), evidence
        )
        today = now.astimezone(tz).date()
        settled: list[tuple[ObjectId, date, tuple[float, float, float, float, float]]] = []
        for _n, (emp, wanted) in enumerate(need.items()):
            if _n % YIELD_EVERY == YIELD_EVERY - 1:
                await asyncio.sleep(0)  # let other requests run: this loop is CPU-bound
            own = sessions.get(emp, [])
            computed = time_accounting(own, wanted, tz, now, open_ends)
            open_starts = [_utc(s.started_at).astimezone(tz).date() for s in own if s.ended_at is None]
            for day, m in computed.items():
                out[(emp, day)] = m
                still_open = any(start <= day for start in open_starts)
                if day < today and not still_open and (emp, day) in per_day:
                    value = (m.work, m.active, m.idle, m.extended_idle, m.away)
                    per_day[(emp, day)].time = value
                    settled.append((emp, day, value))
        return out, settled

    async def _day_results(
        self,
        company: Company,
        employees: list[Employee],
        books: dict[ObjectId, RuleBook],
        days: list[date],
        tz: ZoneInfo,
        now: datetime,
        *,
        with_segments: bool,
    ) -> tuple[dict[tuple[ObjectId, date], DayResult], set[tuple[ObjectId, date]], dict[ObjectId, str]]:
        """Classification, usage and focus per person and day: cached results where valid, computed otherwise.

        Returns the results, which of them are new (to be stored by the caller) and each person's fingerprint.
        """
        today = now.astimezone(tz).date()
        fps = {e.id: books[e.id].fingerprint for e in employees}
        cached = await self._day_cache.load(company.id, fps, days, today, need_focus=with_segments)
        missing: dict[ObjectId, list[date]] = defaultdict(list)
        for e in employees:
            for day in days:
                if (e.id, day) not in cached:
                    missing[e.id].append(day)
        if not missing:
            return cached, set(), fps
        ids = list(missing)
        first = min(d for ds in missing.values() for d in ds)
        last = max(d for ds in missing.values() for d in ds)
        wanted = {(e, d) for e, ds in missing.items() for d in ds}
        app_rows: dict[tuple[ObjectId, date], list[dict[str, Any]]] = defaultdict(list)
        for row in await self._daily.rows(company.id, ids, first, last):
            app_rows[(row["employee_id"], date.fromisoformat(row["day"]))].append(row)
        site_rows: dict[tuple[ObjectId, date], list[dict[str, Any]]] = defaultdict(list)
        for row in await self._websites.rows(company.id, ids, first, last):
            site_rows[(row["employee_id"], date.fromisoformat(row["day"]))].append(row)
        segments: dict[tuple[ObjectId, date], list[Segment]] = defaultdict(list)
        if with_segments:
            lo, hi = day_bounds(first, tz)[0], day_bounds(last, tz)[1]
            for doc in await self._segments.light_for_employees(company.id, ids, lo, hi, MAX_SEGMENTS):
                start = _utc(doc["started_at"])
                key = (doc["employee_id"], start.astimezone(tz).date())
                if key in wanted:
                    segments[key].append(
                        Segment(
                            start, _utc(doc["ended_at"]), doc["app_id"], doc["app_name"], doc.get("domain")
                        )
                    )
        computed: dict[tuple[ObjectId, date], DayResult] = {}
        for _n, key in enumerate(wanted):
            if _n % YIELD_EVERY == YIELD_EVERY - 1:
                await asyncio.sleep(0)  # let other requests run: this loop is CPU-bound
            emp, day = key
            book = books[emp]
            per_category, items = category_time(app_rows.get(key, []), site_rows.get(key, []), book)
            r = DayResult(
                productive=per_category["productive"],
                neutral=per_category["neutral"],
                unproductive=per_category["unproductive"],
                unclassified=per_category[UNCLASSIFIED],
                items=list(items.values()),
                with_focus=with_segments,
            )
            if with_segments:
                day_segments = classify_segments(segments.get(key, []), book)
                found = focus_sessions(day_segments)
                r.focus = found
                r.focus_count = len(found)
                r.focus_seconds = sum(f.seconds for f in found)
                r.longest_focus_seconds = max((f.seconds for f in found), default=0.0)
                r.context_switches = context_switches(day_segments)
            computed[key] = r
        return {**cached, **computed}, set(computed), fps

    async def _task_days(
        self, company: Company, ids: list[ObjectId], lo: datetime, hi: datetime, tz: ZoneInfo, now: datetime
    ) -> dict[tuple[ObjectId, date], tuple[float, int, int]]:
        """Per employee and local day: seconds logged on tasks, tasks completed, open tasks that were due."""
        seconds: dict[tuple[ObjectId, date], float] = defaultdict(float)
        for entry in await self._time.overlapping(company.id, ids, lo, hi):
            start = max(_utc(entry.started_at), lo)
            end = min(_utc(entry.ended_at) if entry.ended_at else now, hi)
            cursor = start
            while cursor < end:  # split across local midnights
                day_end = day_bounds(cursor.astimezone(tz).date(), tz)[1]
                piece_end = min(end, day_end)
                seconds[(entry.employee_id, cursor.astimezone(tz).date())] += (
                    piece_end - cursor
                ).total_seconds()
                cursor = piece_end
        completed: dict[tuple[ObjectId, date], int] = defaultdict(int)
        for task in await self._tasks.query(
            company.id, {"assignee_ids": {"$in": ids}, "completed_at": {"$gte": lo, "$lt": hi}}, limit=50_000
        ):
            if task.completed_at:
                for emp in task.assignee_ids:
                    completed[(emp, _utc(task.completed_at).astimezone(tz).date())] += 1
        due_open: dict[tuple[ObjectId, date], int] = defaultdict(int)
        today = now.astimezone(tz).date()
        for task in await self._tasks.query(
            company.id,
            {
                "assignee_ids": {"$in": ids},
                "status": {"$ne": TaskStatus.COMPLETED},
                "due_date": {"$gte": lo - timedelta(days=1), "$lt": hi},
            },
            limit=50_000,
        ):
            due_day = _utc(task.due_date).date() if task.due_date else None
            if due_day and due_day <= today:  # not yet due: not slipping
                for emp in task.assignee_ids:
                    due_open[(emp, due_day)] += 1
        keys = set(seconds) | set(completed) | set(due_open)
        return {k: (seconds.get(k, 0.0), completed.get(k, 0), due_open.get(k, 0)) for k in keys}

    # ------------------------------------------------------------------ reports
    async def employee_report(
        self, principal: Principal, employee_id: str, start: date, end: date
    ) -> EmployeeProductivity:
        self._range(start, end)
        oid = parse_id(employee_id, not_found="Employee not found.", code="employee_not_found")
        is_self = principal.user.employee_id == oid
        if not is_self and Permission.ACTIVITY_VIEW not in principal.permissions:
            raise NotFoundError("Employee not found.", code="employee_not_found")
        scope = await self._scopes.employee_scope(principal)
        employee = await self._employees.get_in_scope(principal.company_id, oid, scope.filter)
        if employee is None:
            raise NotFoundError("Employee not found.", code="employee_not_found")
        company = await self._company(principal.company_id)

        data = (await self._compute(company, [employee], start, end))[employee.id]
        length = (end - start).days + 1
        previous = (
            await self._compute(
                company,
                [employee],
                start - timedelta(days=length),
                start - timedelta(days=1),
                with_segments=False,
            )
        )[employee.id]
        totals = data.totals
        worked = sum(1 for m in data.days.values() if m.work > 0)
        tz = ZoneInfo(company.timezone)
        profile = (
            await self._profiles.get_by_id(company.id, employee.work_profile_id)
            if employee.work_profile_id
            else None
        )
        return EmployeeProductivity(
            employee=employee_ref(employee),
            work_profile=Ref(id=str(profile.id), name=profile.name) if profile else None,
            start=start,
            end=end,
            timezone=company.timezone,
            totals=_metrics_out(totals),
            scores=_scores(totals),
            task_completion=TaskCompletion(**task_completion(totals)),
            days=_day_rows(data.days),
            usage=_usage(data.items),
            focus_sessions=[
                FocusSessionOut(
                    started_at=f.start.astimezone(tz),
                    ended_at=f.end.astimezone(tz),
                    seconds=round(f.seconds),
                    productive_seconds=round(f.productive_seconds),
                    top_apps=[name for name, _ in sorted(f.apps.items(), key=lambda kv: -kv[1])[:3]],
                )
                for f in sorted(data.focus, key=lambda f: f.start, reverse=True)
            ],
            summary=_summary(totals),
            projects=await self._project_signals(company, [employee.id], start, end),
            insights=[Insight(**i) for i in insights(totals, previous.totals, data.items.values(), worked)],
            disclaimer=DISCLAIMER,
        )

    async def _employees_in_scope(
        self,
        principal: Principal,
        team_id: str | None,
        department_id: str | None = None,
        employee_id: str | None = None,
    ) -> list[Employee]:
        scope = await self._scopes.employee_scope(principal)
        clauses: list[dict[str, Any]] = [{"status": {"$ne": EmployeeStatus.TERMINATED}}]
        if scope.filter:
            clauses.append(scope.filter)
        if team := parse_ref(team_id, "team_id"):
            clauses.append({"team_id": team})
        if department := parse_ref(department_id, "department_id"):
            clauses.append({"department_id": department})
        if person := parse_ref(employee_id, "employee_id"):
            clauses.append({"_id": person})
        ids = await self._employees.ids_matching(principal.company_id, {"$and": clauses})
        return list((await self._employees.find_by_ids(principal.company_id, ids)).values())

    async def team_report(
        self,
        principal: Principal,
        start: date,
        end: date,
        team_id: str | None,
        department_id: str | None = None,
    ) -> TeamProductivity:
        self._range(start, end)
        company = await self._company(principal.company_id)
        employees = await self._employees_in_scope(principal, team_id, department_id)
        data = await self._compute(company, employees, start, end)
        length = (end - start).days + 1
        previous = await self._compute(
            company, employees, start - timedelta(days=length), start - timedelta(days=1), with_segments=False
        )
        teams = await self._teams.find_by_ids(
            principal.company_id, [e.team_id for e in employees if e.team_id]
        )
        profiles = await self._profiles.find_by_ids(
            principal.company_id, [e.work_profile_id for e in employees if e.work_profile_id]
        )

        totals, prev_totals = Metrics(), Metrics()
        per_day = {day: Metrics() for day in local_days(start, end)}
        items: dict[tuple[str, str], UsageItem] = {}
        rows: list[TeamRow] = []
        for _n, employee in enumerate(employees):
            if _n % YIELD_EVERY == YIELD_EVERY - 1:
                await asyncio.sleep(0)  # let other requests run: this loop is CPU-bound
            d = data[employee.id]
            t = d.totals
            totals.add(t)
            prev_totals.add(previous[employee.id].totals)
            for day, m in d.days.items():
                per_day[day].add(m)
            for key, item in d.items.items():
                merged = items.setdefault(
                    key,
                    UsageItem(
                        item.kind, item.key, item.name, 0.0, item.category, item.rule_scope, item.rule_pattern
                    ),
                )
                merged.seconds += item.seconds
            if t.work == 0 and t.tracked == 0:
                continue  # nothing recorded: leave them out of the table rather than show zeros as a judgement
            team = teams.get(employee.team_id) if employee.team_id else None
            profile = profiles.get(employee.work_profile_id) if employee.work_profile_id else None
            rows.append(
                TeamRow(
                    employee=employee_ref(employee),
                    team=Ref(id=str(team.id), name=team.name) if team else None,
                    work_profile=Ref(id=str(profile.id), name=profile.name) if profile else None,
                    metrics=_metrics_out(t),
                    activity_score=activity_score(t)["value"],
                    productive_share=productive_share(t)["value"],
                    focus_score=focus_score(t)["value"],
                    work_utilization=work_utilization(t)["value"],
                )
            )
        rows.sort(key=lambda r: r.employee.full_name.lower())
        worked = sum(1 for d in data.values() for m in d.days.values() if m.work > 0)  # person-days
        return TeamProductivity(
            start=start,
            end=end,
            timezone=company.timezone,
            totals=_metrics_out(totals),
            scores=_scores(totals),
            task_completion=TaskCompletion(**task_completion(totals)),
            days=_day_rows(per_day),
            rows=rows,
            summary=_summary(totals),
            projects=await self._project_signals(company, [e.id for e in employees], start, end),
            insights=[Insight(**i) for i in insights(totals, prev_totals, items.values(), worked)],
            disclaimer=DISCLAIMER,
        )

    async def groups(self, principal: Principal, by: str, start: date, end: date) -> GroupBreakdown:
        """Totals per department or team, for the people in scope. Sorted by name; never ranked."""
        self._range(start, end)
        company = await self._company(principal.company_id)
        employees = await self._employees_in_scope(principal, None)
        data = await self._compute(company, employees, start, end)
        field_name = "department_id" if by == "department" else "team_id"
        repo: Any = self._departments if by == "department" else self._teams
        refs = await repo.find_by_ids(
            principal.company_id, [getattr(e, field_name) for e in employees if getattr(e, field_name)]
        )
        members: dict[ObjectId | None, list[Employee]] = defaultdict(list)
        for e in employees:
            key = getattr(e, field_name)
            members[key if key in refs else None].append(e)
        rows = []
        for key, people in members.items():
            m = Metrics()
            with_data = 0
            for e in people:
                t = data[e.id].totals
                m.add(t)
                with_data += 1 if (t.work or t.tracked or t.task_seconds) else 0
            group = refs.get(key) if key else None
            rows.append(
                GroupRow(
                    group=Ref(id=str(group.id), name=group.name) if group else None,
                    people=len(people),
                    people_with_data=with_data,
                    metrics=_metrics_out(m),
                    scores=_scores(m),
                    task_completion=task_completion(m)["value"],
                )
            )
        rows.sort(key=lambda r: (r.group is None, r.group.name.lower() if r.group else ""))
        return GroupBreakdown(
            by="department" if by == "department" else "team",
            start=start,
            end=end,
            timezone=company.timezone,
            rows=rows,
            disclaimer=DISCLAIMER,
        )

    async def _project_signals(
        self, company: Company, ids: list[ObjectId], start: date, end: date
    ) -> list[ProjectSignal]:
        """Per project: time logged and tasks completed by these people in the period, and overall progress."""
        if not ids:
            return []
        tz = ZoneInfo(company.timezone)
        lo, hi = day_bounds(start, tz)[0], day_bounds(end, tz)[1]
        now = utcnow()
        seconds: dict[ObjectId, float] = defaultdict(float)
        for entry in await self._time.overlapping(company.id, ids, lo, hi):
            begin = max(_utc(entry.started_at), lo)
            finish = min(_utc(entry.ended_at) if entry.ended_at else now, hi)
            seconds[entry.project_id] += max(0.0, (finish - begin).total_seconds())
        completed: dict[ObjectId, int] = defaultdict(int)
        for task in await self._tasks.query(
            company.id,
            {"assignee_ids": {"$in": ids}, "completed_at": {"$gte": lo, "$lt": hi}, "parent_id": None},
            limit=50_000,
        ):
            completed[task.project_id] += 1
        project_ids = list(set(seconds) | set(completed))
        if not project_ids:
            return []
        projects = await self._projects.find_by_ids(company.id, project_ids)
        counts = await self._tasks.counts_by_project(company.id, project_ids)
        out = []
        for pid, project in projects.items():
            c = counts.get(pid, {})
            total = sum(v for k, v in c.items() if k != "time_spent_seconds")
            done = c.get(TaskStatus.COMPLETED.value, 0)
            out.append(
                ProjectSignal(
                    id=str(pid),
                    name=project.name,
                    key=project.key,
                    color=project.color,
                    task_seconds=round(seconds.get(pid, 0.0)),
                    tasks_completed=completed.get(pid, 0),
                    progress=round(100 * done / total) if total else 0,
                    total_tasks=total,
                )
            )
        out.sort(key=lambda p: (-p.task_seconds, -p.tasks_completed, p.name.lower()))
        return out

    async def trend(
        self,
        principal: Principal,
        period: str,
        team_id: str | None,
        department_id: str | None = None,
        employee_id: str | None = None,
    ) -> ProductivityTrend:
        """Scores and time per day, week or month. Focus needs segments, so it is left out of monthly trends."""
        company = await self._company(principal.company_id)
        tz = ZoneInfo(company.timezone)
        today = utcnow().astimezone(tz).date()
        buckets: list[tuple[date, date]] = []
        if period == "daily":
            buckets = [(today - timedelta(days=i), today - timedelta(days=i)) for i in range(13, -1, -1)]
        elif period == "weekly":
            monday = today - timedelta(days=today.weekday())
            buckets = [
                (monday - timedelta(weeks=i), monday - timedelta(weeks=i) + timedelta(days=6))
                for i in range(11, -1, -1)
            ]
        else:
            first = today.replace(day=1)
            for _ in range(12):
                nxt = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
                buckets.append((first, nxt - timedelta(days=1)))
                first = (first - timedelta(days=1)).replace(day=1)
            buckets.reverse()
        if employee_id is not None and Permission.ACTIVITY_VIEW not in principal.permissions:
            me = principal.user.employee_id
            if me is None or parse_ref(employee_id, "employee_id") != me:
                raise NotFoundError("Employee not found.", code="employee_not_found")
            employees = [e for e in [await self._employees.get_by_id(company.id, me)] if e]
        else:
            employees = await self._employees_in_scope(principal, team_id, department_id, employee_id)
            if employee_id is not None and not employees:
                raise NotFoundError("Employee not found.", code="employee_not_found")
        focus_available = period != "monthly"
        data = await self._compute(
            company, employees, buckets[0][0], min(buckets[-1][1], today), with_segments=focus_available
        )
        points = []
        for lo, hi in buckets:
            m = Metrics()
            people = 0
            for d in data.values():
                worked = False
                for day, dm in d.days.items():
                    if lo <= day <= hi:
                        m.add(dm)
                        worked = worked or dm.work > 0
                people += 1 if worked else 0
            points.append(
                TrendPoint(
                    start=lo,
                    end=hi,
                    productive_share=productive_share(m)["value"],
                    activity_score=activity_score(m)["value"],
                    focus_score=focus_score(m)["value"] if focus_available else None,
                    work_utilization=work_utilization(m)["value"],
                    work_seconds=round(m.work),
                    active_seconds=round(m.active),
                    productive_seconds=round(m.productive),
                    classified_seconds=round(m.classified),
                    focus_seconds=round(m.focus_seconds) if focus_available else 0,
                    task_seconds=round(m.task_seconds),
                    people=people,
                )
            )
        return ProductivityTrend(
            period=period, timezone=company.timezone, focus_available=focus_available, points=points
        )

    async def unclassified(self, principal: Principal, start: date, end: date) -> list[UnclassifiedItem]:
        """What the rules don't cover yet, across everyone in scope: the to-do list for rule setup."""
        self._range(start, end)
        company = await self._company(principal.company_id)
        employees = await self._employees_in_scope(principal, None)
        data = await self._compute(company, employees, start, end, with_segments=False)
        totals: dict[tuple[str, str], list[Any]] = {}
        for d in data.values():
            for key, item in d.items.items():
                if item.category != UNCLASSIFIED:
                    continue
                entry = totals.setdefault(key, [item.name, 0.0, 0])
                entry[1] += item.seconds
                entry[2] += 1
        ranked = sorted(totals.items(), key=lambda kv: -kv[1][1])[:50]
        return [
            UnclassifiedItem(kind=k[0], key=k[1], name=v[0], seconds=round(v[1]), employees=v[2])
            for k, v in ranked
            if v[1] >= 30
        ]


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)
