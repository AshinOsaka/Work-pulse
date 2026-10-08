"""Projects & tasks use-cases."""

from __future__ import annotations

import re
import secrets
from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from bson import ObjectId
from pymongo.errors import DuplicateKeyError

from app.auth.permissions import Permission, permissions_for_role
from app.auth.principal import Principal
from app.core.config import Settings
from app.core.exceptions import (
    BadRequestError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    PayloadTooLargeError,
)
from app.core.object_storage import ObjectNotFoundError, ObjectStorage
from app.core.signed_urls import UrlSigner
from app.models.company import Company
from app.models.organization import Employee, EmployeeStatus
from app.models.user import UserStatus
from app.models.work import (
    Milestone,
    Project,
    ProjectStatus,
    Task,
    TaskActivity,
    TaskAttachment,
    TaskComment,
    TaskStatus,
    TimeEntry,
)
from app.repositories.company import CompanyRepository
from app.repositories.organization import EmployeeRepository
from app.repositories.user import UserRepository
from app.repositories.work import (
    MilestoneRepository,
    ProjectRepository,
    TaskActivityRepository,
    TaskAttachmentRepository,
    TaskCommentRepository,
    TaskRepository,
    TimeEntryRepository,
)
from app.schemas.work import (
    ActivityOut,
    AttachmentOut,
    CommentCreate,
    CommentOut,
    LabelCount,
    ManualTime,
    MemberWorkload,
    MilestoneCreate,
    MilestoneOut,
    MilestoneUpdate,
    MyWork,
    ProjectCreate,
    ProjectMembers,
    ProjectOut,
    ProjectStats,
    ProjectUpdate,
    TaskCreate,
    TaskDetail,
    TaskMove,
    TaskOut,
    TaskUpdate,
    TimeEntryOut,
    TimerOut,
    WorkSummary,
)
from app.services.access_scope import AccessScopeService
from app.services.audit_service import AuditService
from app.services.context import RequestMeta
from app.services.employee_service import employee_ref
from app.services.helpers import parse_id, parse_ref
from app.services.work.access import WorkAccess
from app.utils.time import utcnow

MAX_ATTACHMENT_BYTES = 9 * 1024 * 1024
MAX_SUMMARY_DAYS = 92
#: Shown inline in the browser; everything else downloads.
INLINE_TYPES = frozenset({"image/png", "image/jpeg", "image/gif", "image/webp", "application/pdf"})


def sniffed_type(declared: str, data: bytes) -> str:
    """The content type to store. Types shown inline must match the file's own signature (magic bytes); anything
    else, or a mismatch (an HTML page uploaded as "image/png"), is stored as an opaque download."""
    declared = (declared or "").split(";")[0].strip().lower()[:100] or "application/octet-stream"
    if declared not in INLINE_TYPES:
        return declared
    matches = {
        "image/png": data.startswith(b"\x89PNG\r\n\x1a\n"),
        "image/jpeg": data.startswith(b"\xff\xd8\xff"),
        "image/gif": data[:6] in (b"GIF87a", b"GIF89a"),
        "image/webp": data[:4] == b"RIFF" and data[8:12] == b"WEBP",
        "application/pdf": data.startswith(b"%PDF-"),
    }
    return declared if matches[declared] else "application/octet-stream"


_NOT_FOUND_PROJECT = "Project not found."
_NOT_FOUND_TASK = "Task not found."


def _day_dt(value: date | None) -> datetime | None:
    return datetime.combine(value, time.min, tzinfo=UTC) if value else None


def _dt_day(value: datetime | None) -> date | None:
    return value.date() if value else None


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


_PRIORITY_ORDER = {"urgent": 0, "high": 1, "medium": 2, "low": 3}
SUMMARY_TASK_LIMIT = 50


def _urgency(task: TaskOut) -> tuple[int, date, int]:
    """Overdue first, then by due date (undated last), then priority."""
    return (0 if task.overdue else 1, task.due_date or date.max, _PRIORITY_ORDER.get(task.priority.value, 9))


def _check_dates(start: date | None, due: date | None) -> None:
    if start and due and start > due:
        raise BadRequestError("The start date must be on or before the due date.", code="invalid_dates")


def _project_key(name: str) -> str:
    letters = re.sub(r"[^A-Za-z0-9 ]", "", name).upper().split()
    key = "".join(w[0] for w in letters)[:4] if len(letters) > 1 else (letters[0][:4] if letters else "PRJ")
    return key if len(key) >= 2 and key[0].isalpha() else f"P{key}"[:4].ljust(2, "X")


class WorkService:
    def __init__(
        self,
        *,
        settings: Settings,
        companies: CompanyRepository,
        employees: EmployeeRepository,
        users: UserRepository,
        projects: ProjectRepository,
        milestones: MilestoneRepository,
        tasks: TaskRepository,
        comments: TaskCommentRepository,
        activity: TaskActivityRepository,
        attachments: TaskAttachmentRepository,
        time_entries: TimeEntryRepository,
        scopes: AccessScopeService,
        audit: AuditService,
        storage: ObjectStorage,
        signer: UrlSigner,
    ) -> None:
        self._settings = settings
        self._companies = companies
        self._employees = employees
        self._users = users
        self._projects = projects
        self._milestones = milestones
        self._tasks = tasks
        self._comments = comments
        self._activity = activity
        self._attachments = attachments
        self._time = time_entries
        self._scopes = scopes
        self._audit = audit
        self._storage = storage
        self._signer = signer

    # ------------------------------------------------------------------ helpers
    async def access(self, principal: Principal) -> WorkAccess:
        scope_ids: set[ObjectId] | None = None
        if principal.has(Permission.TASK_MANAGE) and not principal.has(Permission.PROJECT_MANAGE):
            scope = await self._scopes.employee_scope(principal)
            scope_ids = set(await self._employees.ids_matching(principal.company_id, scope.filter))
        return WorkAccess.build(principal, scope_ids)

    async def _company(self, company_id: ObjectId) -> Company:
        company = await self._companies.get_by_id(company_id)
        if company is None:
            raise NotFoundError("Workspace not found.")
        return company

    async def _today(self, company_id: ObjectId) -> date:
        company = await self._company(company_id)
        return utcnow().astimezone(ZoneInfo(company.timezone)).date()

    async def _project(self, access: WorkAccess, project_id: str | ObjectId) -> Project:
        oid = (
            project_id
            if isinstance(project_id, ObjectId)
            else parse_id(project_id, not_found=_NOT_FOUND_PROJECT, code="project_not_found")
        )
        project = await self._projects.get_by_id(access.principal.company_id, oid)
        if project is None or not access.sees_project(project):
            raise NotFoundError(_NOT_FOUND_PROJECT, code="project_not_found")
        return project

    async def _task(self, access: WorkAccess, task_id: str) -> tuple[Task, Project]:
        oid = parse_id(task_id, not_found=_NOT_FOUND_TASK, code="task_not_found")
        task = await self._tasks.get_by_id(access.principal.company_id, oid)
        if task is None:
            raise NotFoundError(_NOT_FOUND_TASK, code="task_not_found")
        project = await self._projects.get_by_id(access.principal.company_id, task.project_id)
        if project is None or not access.sees_project(project):
            raise NotFoundError(_NOT_FOUND_TASK, code="task_not_found")
        return task, project

    async def _people(self, company_id: ObjectId, ids: Iterable[ObjectId | None]) -> dict[ObjectId, Employee]:
        return await self._employees.find_by_ids(company_id, [i for i in ids if i])

    async def _valid_members(
        self, company_id: ObjectId, raw_ids: Sequence[str], field: str
    ) -> list[ObjectId]:
        ids = list(dict.fromkeys(oid for v in raw_ids if (oid := parse_ref(v, field))))
        found = await self._employees.find_by_ids(company_id, ids)
        missing = [i for i in ids if i not in found or found[i].status == EmployeeStatus.TERMINATED]
        if missing:
            raise BadRequestError(
                "Some people were not found or are no longer active.",
                code="invalid_reference",
                details={"field": field},
            )
        return ids

    async def _log(self, access: WorkAccess, task: Task, kind: str, **data: Any) -> None:
        await self._activity.create(
            access.principal.company_id,
            TaskActivity(
                company_id=access.principal.company_id,
                task_id=task.id,
                project_id=task.project_id,
                actor_employee_id=access.me,
                kind=kind,
                data=data,
            ),
        )

    # ------------------------------------------------------------------ project output
    async def _project_stats(
        self, company_id: ObjectId, projects: Sequence[Project], today: date
    ) -> dict[ObjectId, ProjectStats]:
        counts = await self._tasks.counts_by_project(company_id, [p.id for p in projects])
        overdue: dict[ObjectId, int] = defaultdict(int)
        if projects:
            for t in await self._tasks.query(
                company_id,
                {
                    "project_id": {"$in": [p.id for p in projects]},
                    "parent_id": None,
                    "status": {"$ne": TaskStatus.COMPLETED},
                    "due_date": {"$lt": _day_dt(today)},
                },
                limit=50_000,
            ):
                overdue[t.project_id] += 1
        out = {}
        for p in projects:
            c = counts.get(p.id, {})
            by_status = {s: int(c.get(s.value, 0)) for s in TaskStatus}
            total = sum(by_status.values())
            done = by_status[TaskStatus.COMPLETED]
            out[p.id] = ProjectStats(
                total=total,
                completed=done,
                by_status=by_status,
                overdue=overdue[p.id],
                time_spent_seconds=int(c.get("time_spent_seconds", 0)),
                progress=round(100 * done / total) if total else 0,
            )
        return out

    async def _projects_out(self, access: WorkAccess, projects: Sequence[Project]) -> list[ProjectOut]:
        company_id = access.principal.company_id
        today = await self._today(company_id)
        people = await self._people(
            company_id, [i for p in projects for i in (*p.member_ids, p.owner_employee_id)]
        )
        stats = await self._project_stats(company_id, projects, today)
        return [
            ProjectOut(
                id=str(p.id),
                name=p.name,
                key=p.key,
                description=p.description,
                color=p.color,
                status=p.status,
                owner=employee_ref(people[p.owner_employee_id]) if p.owner_employee_id in people else None,
                members=sorted(
                    (employee_ref(people[m]) for m in p.member_ids if m in people),
                    key=lambda e: e.full_name.lower(),
                ),
                due_date=_dt_day(p.due_date),
                stats=stats[p.id],
                created_at=p.created_at,
                can_manage=access.manages_project(p),
                can_manage_tasks=access.manages_tasks(p),
            )
            for p in projects
        ]

    # ------------------------------------------------------------------ projects
    async def list_projects(self, principal: Principal, include_archived: bool) -> list[ProjectOut]:
        access = await self.access(principal)
        query = dict(access.project_query() or {})
        if not include_archived:
            query["status"] = ProjectStatus.ACTIVE
        return await self._projects_out(access, await self._projects.visible(principal.company_id, query))

    async def get_project(self, principal: Principal, project_id: str) -> ProjectOut:
        access = await self.access(principal)
        return (await self._projects_out(access, [await self._project(access, project_id)]))[0]

    async def create_project(
        self, principal: Principal, data: ProjectCreate, meta: RequestMeta
    ) -> ProjectOut:
        access = await self.access(principal)
        if not access.manage_all:
            raise ForbiddenError(
                "You do not have permission to create projects.", code="insufficient_permissions"
            )
        members = await self._valid_members(principal.company_id, data.member_ids, "member_ids")
        owner = parse_ref(data.owner_employee_id, "owner_employee_id") or access.me
        if owner and owner not in members:
            members.insert(0, owner)
        if owner:
            await self._valid_members(principal.company_id, [str(owner)], "owner_employee_id")
        base = data.key or _project_key(data.name)
        for attempt in range(20):
            key = base if attempt == 0 else f"{base[:4]}{attempt + 1}"
            project = Project(
                company_id=principal.company_id,
                name=data.name.strip(),
                key=key,
                description=data.description,
                color=data.color,
                owner_employee_id=owner,
                member_ids=members,
                due_date=_day_dt(data.due_date),
                created_by=principal.user_id,
            )
            try:
                await self._projects.create(principal.company_id, project)
                break
            except DuplicateKeyError as exc:
                if data.key:
                    raise ConflictError(
                        "Another project already uses this key.", code="project_key_taken"
                    ) from exc
        else:
            raise ConflictError("Could not find a free project key.", code="project_key_taken")
        await self._audit.record(
            "project.created",
            company_id=principal.company_id,
            actor_user_id=principal.user_id,
            target_type="project",
            target_id=str(project.id),
            meta=meta,
            metadata={"name": project.name},
        )
        return (await self._projects_out(access, [project]))[0]

    async def update_project(
        self, principal: Principal, project_id: str, data: ProjectUpdate, meta: RequestMeta
    ) -> ProjectOut:
        access = await self.access(principal)
        project = await self._project(access, project_id)
        if not access.manages_project(project):
            raise ForbiddenError(
                "Only project managers can change the project.", code="insufficient_permissions"
            )
        changes: dict[str, Any] = {
            k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None
        }
        if "due_date" in changes:
            changes["due_date"] = _day_dt(changes["due_date"])
        if "owner_employee_id" in changes:
            owner = (
                await self._valid_members(
                    principal.company_id, [changes["owner_employee_id"]], "owner_employee_id"
                )
            )[0]
            changes["owner_employee_id"] = owner
            if owner not in project.member_ids:
                changes["member_ids"] = [*project.member_ids, owner]
        updated = await self._projects.update_by_id(principal.company_id, project.id, changes) or project
        action = "project.archived" if changes.get("status") == ProjectStatus.ARCHIVED else "project.updated"
        await self._audit.record(
            action,
            company_id=principal.company_id,
            actor_user_id=principal.user_id,
            target_type="project",
            target_id=str(project.id),
            meta=meta,
            metadata={"fields": sorted(changes)},
        )
        return (await self._projects_out(access, [updated]))[0]

    async def set_members(
        self, principal: Principal, project_id: str, data: ProjectMembers, meta: RequestMeta
    ) -> ProjectOut:
        access = await self.access(principal)
        project = await self._project(access, project_id)
        if not access.manages_project(project):
            raise ForbiddenError("Only project managers can change members.", code="insufficient_permissions")
        members = await self._valid_members(principal.company_id, data.member_ids, "member_ids")
        if project.owner_employee_id and project.owner_employee_id not in members:
            members.insert(0, project.owner_employee_id)
        removed = [m for m in project.member_ids if m not in members]
        if removed:
            await self._tasks.remove_member_assignments(principal.company_id, project.id, removed)
        updated = (
            await self._projects.update_by_id(principal.company_id, project.id, {"member_ids": members})
            or project
        )
        await self._audit.record(
            "project.members_changed",
            company_id=principal.company_id,
            actor_user_id=principal.user_id,
            target_type="project",
            target_id=str(project.id),
            meta=meta,
            metadata={
                "added": len([m for m in members if m not in project.member_ids]),
                "removed": len(removed),
            },
        )
        return (await self._projects_out(access, [updated]))[0]

    async def project_activity(self, principal: Principal, project_id: str) -> list[ActivityOut]:
        access = await self.access(principal)
        project = await self._project(access, project_id)
        items = await self._activity.for_project(principal.company_id, project.id)
        return await self._activity_out(principal.company_id, items)

    # ------------------------------------------------------------------ task output
    async def _tasks_out(
        self, access: WorkAccess, tasks: Sequence[Task], projects: dict[ObjectId, Project] | None = None
    ) -> list[TaskOut]:
        company_id = access.principal.company_id
        if not tasks:
            return []
        if projects is None:
            projects = await self._projects.find_by_ids(company_id, {t.project_id for t in tasks})
        people = await self._people(company_id, [a for t in tasks for a in t.assignee_ids])
        today = await self._today(company_id)
        subtasks: dict[ObjectId, list[Task]] = defaultdict(list)
        for sub in await self._tasks.query(
            company_id, {"parent_id": {"$in": [t.id for t in tasks]}}, limit=50_000
        ):
            subtasks[sub.parent_id].append(sub)  # type: ignore[index]
        running = await self._time.running(company_id, access.me) if access.me else None
        out = []
        for t in tasks:
            project = projects.get(t.project_id)
            if project is None:
                continue
            due = _dt_day(t.due_date)
            subs = subtasks.get(t.id, [])
            out.append(
                TaskOut(
                    id=str(t.id),
                    project_id=str(t.project_id),
                    project_key=project.key,
                    reference=f"{project.key}-{t.number}",
                    title=t.title,
                    description=t.description,
                    status=t.status,
                    priority=t.priority,
                    assignees=[employee_ref(people[a]) for a in t.assignee_ids if a in people],
                    parent_id=str(t.parent_id) if t.parent_id else None,
                    due_date=due,
                    start_date=_dt_day(t.start_date),
                    labels=t.labels,
                    milestone_id=str(t.milestone_id) if t.milestone_id else None,
                    overdue=bool(due and due < today and t.status != TaskStatus.COMPLETED),
                    rank=t.rank,
                    estimate_minutes=t.estimate_minutes,
                    completed_at=t.completed_at,
                    created_at=t.created_at,
                    updated_at=t.updated_at,
                    time_spent_seconds=t.time_spent_seconds
                    + (self._elapsed(running) if running and running.task_id == t.id else 0),
                    comment_count=t.comment_count,
                    attachment_count=t.attachment_count,
                    subtask_total=len(subs),
                    subtask_done=sum(1 for s in subs if s.status == TaskStatus.COMPLETED),
                    timer_running=bool(running and running.task_id == t.id),
                    can_edit=access.can_edit_task(project, t),
                )
            )
        return out

    @staticmethod
    def _elapsed(entry: TimeEntry) -> int:
        return max(0, int((utcnow() - _aware(entry.started_at)).total_seconds()))

    async def _activity_out(self, company_id: ObjectId, items: Sequence[TaskActivity]) -> list[ActivityOut]:
        people = await self._people(company_id, [a.actor_employee_id for a in items])
        return [
            ActivityOut(
                id=str(a.id),
                kind=a.kind,
                data=a.data,
                created_at=a.created_at,
                actor=employee_ref(people[a.actor_employee_id]) if a.actor_employee_id in people else None,
            )
            for a in items
        ]

    # ------------------------------------------------------------------ tasks
    async def list_tasks(
        self,
        principal: Principal,
        *,
        project_id: str | None,
        assignee: str | None,
        team_id: str | None,
        statuses: list[TaskStatus] | None,
        priority: str | None,
        search: str | None,
        due: str | None,
        include_subtasks: bool,
        limit: int,
        label: str | None = None,
        milestone: str | None = None,
    ) -> list[TaskOut]:
        access = await self.access(principal)
        company_id = principal.company_id
        if project_id:
            projects = {p.id: p for p in [await self._project(access, project_id)]}
        else:
            projects = {
                p.id: p
                for p in await self._projects.visible(
                    company_id, {**(access.project_query() or {}), "status": ProjectStatus.ACTIVE}
                )
            }
        query: dict[str, Any] = {"project_id": {"$in": list(projects)}}
        if not include_subtasks:
            query["parent_id"] = None
        if assignee == "me":
            if not access.me:
                return []
            query["assignee_ids"] = access.me
        elif assignee:
            query["assignee_ids"] = parse_ref(assignee, "assignee")
        if team_id:
            team = parse_ref(team_id, "team_id")
            scope = await self._scopes.employee_scope(principal)
            clauses = [c for c in ({"team_id": team}, scope.filter) if c]
            ids = await self._employees.ids_matching(
                company_id, {"$and": clauses} if len(clauses) > 1 else clauses[0]
            )
            query["assignee_ids"] = {"$in": ids}
        if statuses:
            query["status"] = {"$in": [s.value for s in statuses]}
        if priority:
            query["priority"] = priority
        if search:
            query["title"] = {"$regex": re.escape(search.strip()[:100]), "$options": "i"}
        if label:
            query["labels"] = label.strip().lower()[:30]
        if milestone == "none":
            query["milestone_id"] = None
        elif milestone:
            query["milestone_id"] = parse_ref(milestone, "milestone_id")
        if due:
            today = await self._today(company_id)
            if due == "overdue":
                query["due_date"] = {"$lt": _day_dt(today)}
                query["status"] = {"$ne": TaskStatus.COMPLETED}
            elif due == "today":
                query["due_date"] = _day_dt(today)
            elif due == "week":
                query["due_date"] = {"$gte": _day_dt(today), "$lte": _day_dt(today + timedelta(days=7))}
        tasks = await self._tasks.query(company_id, query, limit=min(limit, 2000))
        return await self._tasks_out(access, tasks, projects)

    async def get_task(self, principal: Principal, task_id: str) -> TaskDetail:
        access = await self.access(principal)
        task, project = await self._task(access, task_id)
        company_id = principal.company_id
        (base,) = await self._tasks_out(access, [task], {project.id: project})
        subtasks = await self._tasks_out(
            access,
            await self._tasks.query(company_id, {"parent_id": task.id}, sort=[("rank", 1), ("number", 1)]),
            {project.id: project},
        )
        comments = await self._comments.for_task(company_id, task.id)
        attachments = await self._attachments.for_task(company_id, task.id)
        entries = await self._time.for_task(company_id, task.id)
        people = await self._people(
            company_id,
            [c.author_employee_id for c in comments]
            + [a.uploaded_by_employee_id for a in attachments]
            + [e.employee_id for e in entries],
        )
        return TaskDetail(
            **base.model_dump(),
            project_name=project.name,
            subtasks=subtasks,
            comments=[
                CommentOut(
                    id=str(c.id),
                    body=c.body,
                    created_at=c.created_at,
                    edited_at=c.edited_at,
                    author=employee_ref(people[c.author_employee_id])
                    if c.author_employee_id in people
                    else None,
                    can_edit=c.author_employee_id == access.me or access.manages_tasks(project),
                )
                for c in comments
            ],
            activity=await self._activity_out(company_id, await self._activity.for_task(company_id, task.id)),
            attachments=[self._attachment_out(access, project, a, people) for a in attachments],
            time_entries=[
                TimeEntryOut(
                    id=str(e.id),
                    task_id=str(e.task_id),
                    started_at=e.started_at,
                    ended_at=e.ended_at,
                    seconds=e.seconds if e.ended_at else self._elapsed(e),
                    source=e.source,
                    note=e.note,
                    employee=employee_ref(people[e.employee_id]) if e.employee_id in people else None,
                )
                for e in entries
            ],
        )

    async def create_task(self, principal: Principal, data: TaskCreate) -> TaskOut:
        access = await self.access(principal)
        project = await self._project(access, data.project_id)
        if project.status == ProjectStatus.ARCHIVED:
            raise BadRequestError("This project is archived.", code="project_archived")
        if not access.can_create_task(project):
            raise ForbiddenError("Only project members can add tasks.", code="insufficient_permissions")
        parent: Task | None = None
        if data.parent_id:
            parent_oid = parse_ref(data.parent_id, "parent_id")
            parent = await self._tasks.get_by_id(principal.company_id, parent_oid) if parent_oid else None
            if parent is None or parent.project_id != project.id:
                raise BadRequestError("The parent task is not in this project.", code="invalid_reference")
            if parent.parent_id is not None:
                raise BadRequestError("Subtasks can't have their own subtasks.", code="nesting_too_deep")
        assignees = await self._check_assignees(access, project, data.assignee_ids)
        milestone = await self._milestone_in(project, data.milestone_id)
        _check_dates(data.start_date, data.due_date)
        number = await self._projects.next_number(principal.company_id, project.id)
        task = Task(
            company_id=principal.company_id,
            project_id=project.id,
            number=number,
            title=data.title.strip(),
            description=data.description,
            status=data.status,
            priority=data.priority,
            assignee_ids=assignees,
            parent_id=parent.id if parent else None,
            due_date=_day_dt(data.due_date),
            start_date=_day_dt(data.start_date),
            labels=data.labels,
            milestone_id=milestone.id if milestone else None,
            rank=await self._tasks.max_rank(principal.company_id, project.id, data.status) + 1000,
            estimate_minutes=data.estimate_minutes,
            completed_at=utcnow() if data.status == TaskStatus.COMPLETED else None,
            created_by_employee_id=access.me,
        )
        await self._tasks.create(principal.company_id, task)
        await self._log(access, task, "created", title=task.title)
        if parent:
            await self._log(
                access, parent, "subtask_added", title=task.title, subtask=f"{project.key}-{task.number}"
            )
        return (await self._tasks_out(access, [task], {project.id: project}))[0]

    async def _check_assignees(
        self, access: WorkAccess, project: Project, raw: Sequence[str]
    ) -> list[ObjectId]:
        ids = await self._valid_members(access.principal.company_id, raw, "assignee_ids")
        outsiders = [i for i in ids if i not in project.member_ids]
        if outsiders:
            raise BadRequestError("Tasks can only be assigned to project members.", code="not_a_member")
        if not access.manages_tasks(project) and any(i != access.me for i in ids):
            raise ForbiddenError(
                "Only task managers can assign tasks to others.", code="insufficient_permissions"
            )
        return ids

    async def update_task(self, principal: Principal, task_id: str, data: TaskUpdate) -> TaskOut:
        access = await self.access(principal)
        task, project = await self._task(access, task_id)
        if not access.can_edit_task(project, task):
            raise ForbiddenError("You can't change this task.", code="insufficient_permissions")
        fields = data.model_dump(exclude_unset=True)
        changes: dict[str, Any] = {}
        if fields.get("title") and fields["title"].strip() != task.title:
            changes["title"] = fields["title"].strip()
            await self._log(access, task, "renamed", **{"from": task.title, "to": changes["title"]})
        if "description" in fields and fields["description"] != task.description:
            changes["description"] = fields["description"]
            await self._log(access, task, "description_changed")
        if fields.get("priority") and fields["priority"] != task.priority:
            changes["priority"] = fields["priority"]
            await self._log(
                access,
                task,
                "priority_changed",
                **{"from": task.priority.value, "to": fields["priority"].value},
            )
        if data.clear_due_date and task.due_date is not None:
            changes["due_date"] = None
            await self._log(access, task, "due_changed", **{"from": str(_dt_day(task.due_date)), "to": None})
        elif fields.get("due_date") and _day_dt(fields["due_date"]) != task.due_date:
            changes["due_date"] = _day_dt(fields["due_date"])
            await self._log(
                access,
                task,
                "due_changed",
                **{
                    "from": str(_dt_day(task.due_date)) if task.due_date else None,
                    "to": str(fields["due_date"]),
                },
            )
        if "start_date" in fields and _day_dt(fields["start_date"]) != task.start_date:
            changes["start_date"] = _day_dt(fields["start_date"])
            await self._log(
                access,
                task,
                "start_changed",
                **{
                    "from": str(_dt_day(task.start_date)) if task.start_date else None,
                    "to": str(fields["start_date"]) if fields["start_date"] else None,
                },
            )
        final_due = _dt_day(changes["due_date"]) if "due_date" in changes else _dt_day(task.due_date)
        final_start = _dt_day(changes["start_date"]) if "start_date" in changes else _dt_day(task.start_date)
        _check_dates(final_start, final_due)
        if "labels" in fields:
            labels = fields["labels"] or []
            if labels != task.labels:
                changes["labels"] = labels
                await self._log(
                    access,
                    task,
                    "labels_changed",
                    added=[x for x in labels if x not in task.labels],
                    removed=[x for x in task.labels if x not in labels],
                )
        if "milestone_id" in fields:
            milestone = await self._milestone_in(project, fields["milestone_id"])
            new_id = milestone.id if milestone else None
            if new_id != task.milestone_id:
                old = (
                    await self._milestones.get_by_id(principal.company_id, task.milestone_id)
                    if task.milestone_id
                    else None
                )
                changes["milestone_id"] = new_id
                await self._log(
                    access,
                    task,
                    "milestone_changed",
                    **{"from": old.name if old else None, "to": milestone.name if milestone else None},
                )
        if "estimate_minutes" in fields:
            changes["estimate_minutes"] = fields["estimate_minutes"]
        if fields.get("assignee_ids") is not None:
            ids = await self._check_assignees(access, project, fields["assignee_ids"])
            if set(ids) != set(task.assignee_ids):
                people = await self._people(principal.company_id, set(ids) | set(task.assignee_ids))
                added = [people[i].full_name for i in ids if i not in task.assignee_ids and i in people]
                removed = [people[i].full_name for i in task.assignee_ids if i not in ids and i in people]
                changes["assignee_ids"] = ids
                await self._log(access, task, "assignees_changed", added=added, removed=removed)
        if fields.get("status") and fields["status"] != task.status:
            changes.update(await self._status_change(access, task, fields["status"]))
        if changes:
            task = await self._tasks.update_by_id(principal.company_id, task.id, changes) or task
        return (await self._tasks_out(access, [task], {project.id: project}))[0]

    async def _status_change(self, access: WorkAccess, task: Task, status: TaskStatus) -> dict[str, Any]:
        changes: dict[str, Any] = {"status": status}
        if status == TaskStatus.COMPLETED:
            changes["completed_at"] = utcnow()
            await self._stop_timers_on(access.principal.company_id, task)
        elif task.status == TaskStatus.COMPLETED:
            changes["completed_at"] = None
        changes["rank"] = (
            await self._tasks.max_rank(access.principal.company_id, task.project_id, status) + 1000
        )
        await self._log(access, task, "status_changed", **{"from": task.status.value, "to": status.value})
        return changes

    async def move_task(self, principal: Principal, task_id: str, data: TaskMove) -> TaskOut:
        """Kanban drag & drop: change column and/or position within it."""
        access = await self.access(principal)
        task, project = await self._task(access, task_id)
        if not access.can_edit_task(project, task):
            raise ForbiddenError("You can't move this task.", code="insufficient_permissions")
        changes: dict[str, Any] = {}
        if data.status != task.status:
            changes.update(await self._status_change(access, task, data.status))
        column = [
            t
            for t in await self._tasks.query(
                principal.company_id,
                {"project_id": project.id, "status": data.status, "parent_id": None},
                sort=[("rank", 1), ("number", 1)],
            )
            if t.id != task.id
        ]
        column.insert(min(data.index, len(column)), task)
        await self._tasks.set_ranks(
            principal.company_id, {t.id: float((i + 1) * 1000) for i, t in enumerate(column)}
        )
        changes.pop("rank", None)
        if changes:
            await self._tasks.update_by_id(principal.company_id, task.id, changes)
        moved = await self._tasks.get_by_id(principal.company_id, task.id) or task
        return (await self._tasks_out(access, [moved], {project.id: project}))[0]

    async def delete_task(self, principal: Principal, task_id: str) -> None:
        access = await self.access(principal)
        task, project = await self._task(access, task_id)
        if not access.can_delete_task(project, task):
            raise ForbiddenError("You can't delete this task.", code="insufficient_permissions")
        company_id = principal.company_id
        await self._stop_timers_on(company_id, task)
        attachments = await self._attachments.for_tasks(company_id, [task.id])
        ids = await self._tasks.delete_tree(company_id, task.id)
        attachments += await self._attachments.for_tasks(company_id, [i for i in ids if i != task.id])
        if attachments:
            await self._storage.delete(*[a.object_key for a in attachments])
        await self._attachments.delete_for_tasks(company_id, ids)
        await self._comments.delete_for_tasks(company_id, ids)
        await self._activity.delete_for_tasks(company_id, ids)
        # Time entries are kept: logged time stays in reports even if the task is removed.
        if task.parent_id:
            await self._log(
                access,
                Task(**{**task.model_dump(), "id": task.parent_id}),
                "subtask_removed",
                title=task.title,
            )

    # ------------------------------------------------------------------ milestones & labels
    async def _milestone_in(self, project: Project, raw: str | None) -> Milestone | None:
        """Resolve a milestone id for a task; it must belong to the task's project."""
        if not raw:
            return None
        oid = parse_ref(raw, "milestone_id")
        milestone = await self._milestones.get_by_id(project.company_id, oid) if oid else None
        if milestone is None or milestone.project_id != project.id:
            raise BadRequestError("That milestone is not in this project.", code="invalid_reference")
        return milestone

    async def _milestones_out(
        self, access: WorkAccess, project: Project, items: Sequence[Milestone]
    ) -> list[MilestoneOut]:
        counts = await self._tasks.counts_by_milestone(access.principal.company_id, [m.id for m in items])
        today = await self._today(access.principal.company_id)
        out = []
        for m in items:
            c = counts.get(m.id, {"total": 0, "completed": 0})
            due = _dt_day(m.due_date)
            out.append(
                MilestoneOut(
                    id=str(m.id),
                    project_id=str(m.project_id),
                    name=m.name,
                    description=m.description,
                    due_date=due,
                    closed=m.closed_at is not None,
                    closed_at=m.closed_at,
                    total=c["total"],
                    completed=c["completed"],
                    progress=round(100 * c["completed"] / c["total"]) if c["total"] else 0,
                    overdue=bool(due and due < today and m.closed_at is None),
                    can_manage=access.manages_tasks(project),
                )
            )
        return out

    async def _managed_milestone(self, access: WorkAccess, milestone_id: str) -> tuple[Milestone, Project]:
        oid = parse_id(milestone_id, not_found="Milestone not found.", code="milestone_not_found")
        milestone = await self._milestones.get_by_id(access.principal.company_id, oid)
        if milestone is None:
            raise NotFoundError("Milestone not found.", code="milestone_not_found")
        project = await self._project(access, milestone.project_id)  # 404 when the project isn't visible
        if not access.manages_tasks(project):
            raise ForbiddenError("Only task managers can change milestones.", code="insufficient_permissions")
        return milestone, project

    async def list_milestones(self, principal: Principal, project_id: str) -> list[MilestoneOut]:
        access = await self.access(principal)
        project = await self._project(access, project_id)
        return await self._milestones_out(
            access, project, await self._milestones.for_project(principal.company_id, project.id)
        )

    async def create_milestone(
        self, principal: Principal, project_id: str, data: MilestoneCreate
    ) -> MilestoneOut:
        access = await self.access(principal)
        project = await self._project(access, project_id)
        if not access.manages_tasks(project):
            raise ForbiddenError("Only task managers can add milestones.", code="insufficient_permissions")
        if project.status == ProjectStatus.ARCHIVED:
            raise BadRequestError("This project is archived.", code="project_archived")
        milestone = Milestone(
            company_id=principal.company_id,
            project_id=project.id,
            name=data.name.strip(),
            description=data.description,
            due_date=_day_dt(data.due_date),
            created_by_employee_id=access.me,
        )
        await self._milestones.create(principal.company_id, milestone)
        return (await self._milestones_out(access, project, [milestone]))[0]

    async def update_milestone(
        self, principal: Principal, milestone_id: str, data: MilestoneUpdate
    ) -> MilestoneOut:
        access = await self.access(principal)
        milestone, project = await self._managed_milestone(access, milestone_id)
        fields = data.model_dump(exclude_unset=True)
        changes: dict[str, Any] = {}
        if fields.get("name"):
            changes["name"] = fields["name"].strip()
        if "description" in fields:
            changes["description"] = fields["description"]
        if "due_date" in fields:
            changes["due_date"] = _day_dt(fields["due_date"])
        if fields.get("closed") is not None and fields["closed"] != (milestone.closed_at is not None):
            changes["closed_at"] = utcnow() if fields["closed"] else None
        if changes:
            milestone = (
                await self._milestones.update_by_id(principal.company_id, milestone.id, changes) or milestone
            )
        return (await self._milestones_out(access, project, [milestone]))[0]

    async def delete_milestone(self, principal: Principal, milestone_id: str) -> None:
        """Removes the milestone only; its tasks stay, without a milestone."""
        access = await self.access(principal)
        milestone, _project = await self._managed_milestone(access, milestone_id)
        await self._tasks.clear_milestone(principal.company_id, milestone.id)
        await self._milestones.delete_by_id(principal.company_id, milestone.id)

    async def project_labels(self, principal: Principal, project_id: str) -> list[LabelCount]:
        access = await self.access(principal)
        project = await self._project(access, project_id)
        return [
            LabelCount(name=name, count=n)
            for name, n in await self._tasks.label_counts(principal.company_id, project.id)
        ]

    # ------------------------------------------------------------------ comments
    async def add_comment(self, principal: Principal, task_id: str, data: CommentCreate) -> CommentOut:
        access = await self.access(principal)
        task, _ = await self._task(access, task_id)
        if not access.me:
            raise ForbiddenError(
                "Only people with an employee record can comment.", code="no_employee_record"
            )
        comment = TaskComment(
            company_id=principal.company_id,
            task_id=task.id,
            author_employee_id=access.me,
            body=data.body.strip(),
        )
        await self._comments.create(principal.company_id, comment)
        await self._tasks.inc(principal.company_id, task.id, "comment_count", 1)
        await self._log(access, task, "commented", excerpt=comment.body[:120])
        people = await self._people(principal.company_id, [access.me])
        return CommentOut(
            id=str(comment.id),
            body=comment.body,
            created_at=comment.created_at,
            edited_at=None,
            author=employee_ref(people[access.me]) if access.me in people else None,
            can_edit=True,
        )

    async def _own_comment(
        self, access: WorkAccess, task_id: str, comment_id: str
    ) -> tuple[Task, Project, TaskComment]:
        task, project = await self._task(access, task_id)
        oid = parse_id(comment_id, not_found="Comment not found.", code="comment_not_found")
        comment = await self._comments.get_by_id(access.principal.company_id, oid)
        if comment is None or comment.task_id != task.id:
            raise NotFoundError("Comment not found.", code="comment_not_found")
        if comment.author_employee_id != access.me and not access.manages_tasks(project):
            raise ForbiddenError("You can only change your own comments.", code="insufficient_permissions")
        return task, project, comment

    async def edit_comment(
        self, principal: Principal, task_id: str, comment_id: str, data: CommentCreate
    ) -> CommentOut:
        access = await self.access(principal)
        _, _, comment = await self._own_comment(access, task_id, comment_id)
        updated = (
            await self._comments.update_by_id(
                principal.company_id, comment.id, {"body": data.body.strip(), "edited_at": utcnow()}
            )
            or comment
        )
        people = await self._people(principal.company_id, [updated.author_employee_id])
        return CommentOut(
            id=str(updated.id),
            body=updated.body,
            created_at=updated.created_at,
            edited_at=updated.edited_at,
            author=employee_ref(people[updated.author_employee_id])
            if updated.author_employee_id in people
            else None,
            can_edit=True,
        )

    async def delete_comment(self, principal: Principal, task_id: str, comment_id: str) -> None:
        access = await self.access(principal)
        task, _, comment = await self._own_comment(access, task_id, comment_id)
        await self._comments.delete_by_id(principal.company_id, comment.id)
        await self._tasks.inc(principal.company_id, task.id, "comment_count", -1)

    # ------------------------------------------------------------------ attachments
    def _attachment_out(
        self, access: WorkAccess, project: Project, a: TaskAttachment, people: dict[ObjectId, Employee]
    ) -> AttachmentOut:
        url = self._signer.sign(
            f"{self._settings.api_prefix}/task-files/{a.id}",
            company_id=str(access.principal.company_id),
            user_id=str(access.principal.user_id),
            object_id=str(a.id),
            variant="attachment",
        )
        return AttachmentOut(
            id=str(a.id),
            filename=a.filename,
            content_type=a.content_type,
            size_bytes=a.size_bytes,
            created_at=a.created_at,
            uploaded_by=employee_ref(people[a.uploaded_by_employee_id])
            if a.uploaded_by_employee_id in people
            else None,
            download_url=url,
            can_delete=a.uploaded_by_employee_id == access.me or access.manages_tasks(project),
        )

    async def add_attachment(
        self, principal: Principal, task_id: str, filename: str, content_type: str, data: bytes
    ) -> AttachmentOut:
        access = await self.access(principal)
        task, project = await self._task(access, task_id)
        if not (access.is_member(project) or access.manages_tasks(project)):
            raise ForbiddenError("Only project members can attach files.", code="insufficient_permissions")
        if len(data) > MAX_ATTACHMENT_BYTES:
            raise PayloadTooLargeError(
                f"Attachments must be at most {MAX_ATTACHMENT_BYTES // (1024 * 1024)} MB."
            )
        if not data:
            raise BadRequestError("The file is empty.", code="empty_file")
        safe_name = re.sub(r"[\x00-\x1f/\\]+", "_", filename.strip())[:180] or "file"
        attachment_id = ObjectId()
        key = f"attachments/{principal.company_id}/{task.project_id}/{attachment_id}-{secrets.token_hex(4)}"
        await self._storage.put(key, data)
        attachment = TaskAttachment(
            id=attachment_id,
            company_id=principal.company_id,
            task_id=task.id,
            uploaded_by_employee_id=access.me,
            filename=safe_name,
            content_type=sniffed_type(content_type, data),
            size_bytes=len(data),
            object_key=key,
        )
        await self._attachments.create(principal.company_id, attachment)
        await self._tasks.inc(principal.company_id, task.id, "attachment_count", 1)
        await self._log(access, task, "attachment_added", filename=safe_name)
        people = await self._people(principal.company_id, [access.me])
        return self._attachment_out(access, project, attachment, people)

    async def delete_attachment(self, principal: Principal, task_id: str, attachment_id: str) -> None:
        access = await self.access(principal)
        task, project = await self._task(access, task_id)
        oid = parse_id(attachment_id, not_found="Attachment not found.", code="attachment_not_found")
        attachment = await self._attachments.get_by_id(principal.company_id, oid)
        if attachment is None or attachment.task_id != task.id:
            raise NotFoundError("Attachment not found.", code="attachment_not_found")
        if attachment.uploaded_by_employee_id != access.me and not access.manages_tasks(project):
            raise ForbiddenError("You can only remove files you added.", code="insufficient_permissions")
        await self._storage.delete(attachment.object_key)
        await self._attachments.delete_by_id(principal.company_id, oid)
        await self._tasks.inc(principal.company_id, task.id, "attachment_count", -1)
        await self._log(access, task, "attachment_removed", filename=attachment.filename)

    async def read_attachment(
        self, *, attachment_id: str, company_id: str, user_id: str, expires: int, signature: str
    ) -> tuple[TaskAttachment, bytes]:
        not_found = NotFoundError("Attachment not found.", code="attachment_not_found")
        if not self._signer.verify(
            company_id=company_id,
            user_id=user_id,
            object_id=attachment_id,
            variant="attachment",
            expires=expires,
            signature=signature,
        ):
            raise not_found
        company_oid = parse_id(company_id, not_found="x")
        user = await self._users.get_by_id(company_oid, parse_id(user_id, not_found="x"))
        if user is None or user.status != UserStatus.ACTIVE:
            raise not_found
        access = await self.access(Principal(user=user, permissions=permissions_for_role(user.role)))
        attachment = await self._attachments.get_by_id(company_oid, parse_id(attachment_id, not_found="x"))
        if attachment is None:
            raise not_found
        await self._task(access, str(attachment.task_id))  # still visible to this viewer?
        try:
            return attachment, await self._storage.get(attachment.object_key)
        except ObjectNotFoundError:
            raise not_found from None

    # ------------------------------------------------------------------ time
    async def _stop_timers_on(self, company_id: ObjectId, task: Task) -> None:
        for entry in await self._time.query_running_for_task(company_id, task.id):
            await self._close_entry(company_id, entry)

    async def _close_entry(self, company_id: ObjectId, entry: TimeEntry) -> int:
        seconds = self._elapsed(entry)
        stopped = await self._time.stop(company_id, entry.id, utcnow(), seconds)
        if stopped:
            await self._tasks.inc(company_id, entry.task_id, "time_spent_seconds", seconds)
        return seconds

    async def timer(self, principal: Principal) -> TimerOut:
        access = await self.access(principal)
        company = await self._company(principal.company_id)
        running = await self._time.running(principal.company_id, access.me) if access.me else None
        task_out = None
        if running:
            task = await self._tasks.get_by_id(principal.company_id, running.task_id)
            if task is not None:
                outs = await self._tasks_out(access, [task])
                task_out = outs[0] if outs else None
        return TimerOut(
            running=running is not None,
            task=task_out,
            started_at=running.started_at if running else None,
            elapsed_seconds=self._elapsed(running) if running else 0,
            today_seconds=await self._today_seconds(principal.company_id, access.me, company)
            if access.me
            else 0,
        )

    async def _today_seconds(self, company_id: ObjectId, employee_id: ObjectId, company: Company) -> int:
        tz = ZoneInfo(company.timezone)
        now = utcnow()
        start = datetime.combine(now.astimezone(tz).date(), time.min, tzinfo=tz)
        total = 0.0
        for e in await self._time.overlapping(company_id, [employee_id], start, now):
            end = _aware(e.ended_at) if e.ended_at else now
            total += max(0.0, (min(end, now) - max(_aware(e.started_at), start)).total_seconds())
        return round(total)

    async def start_timer(self, principal: Principal, task_id: str) -> TimerOut:
        access = await self.access(principal)
        task, project = await self._task(access, task_id)
        if not access.can_track_time(project):
            raise ForbiddenError("Only project members can track time here.", code="insufficient_permissions")
        if task.status == TaskStatus.COMPLETED:
            raise BadRequestError(
                "This task is completed. Reopen it to track more time.", code="task_completed"
            )
        assert access.me is not None
        running = await self._time.running(principal.company_id, access.me)
        if running and running.task_id == task.id:
            return await self.timer(principal)
        if running:
            await self._close_entry(principal.company_id, running)
            previous = await self._tasks.get_by_id(principal.company_id, running.task_id)
            if previous:
                await self._log(access, previous, "timer_stopped")
        entry = TimeEntry(
            company_id=principal.company_id,
            task_id=task.id,
            project_id=task.project_id,
            employee_id=access.me,
            started_at=utcnow(),
        )
        if await self._time.start(entry) is None:
            raise ConflictError("A timer is already running. Try again.", code="timer_running")
        if task.status == TaskStatus.TODO:
            await self._tasks.update_by_id(
                principal.company_id, task.id, await self._status_change(access, task, TaskStatus.IN_PROGRESS)
            )
        await self._log(access, task, "timer_started")
        return await self.timer(principal)

    async def stop_timer(self, principal: Principal) -> TimerOut:
        access = await self.access(principal)
        running = await self._time.running(principal.company_id, access.me) if access.me else None
        if running:
            await self._close_entry(principal.company_id, running)
            task = await self._tasks.get_by_id(principal.company_id, running.task_id)
            if task:
                await self._log(access, task, "timer_stopped", seconds=self._elapsed(running))
        return await self.timer(principal)

    async def log_time(self, principal: Principal, task_id: str, data: ManualTime) -> TimeEntryOut:
        access = await self.access(principal)
        task, project = await self._task(access, task_id)
        if not access.can_track_time(project):
            raise ForbiddenError("Only project members can track time here.", code="insufficient_permissions")
        company = await self._company(principal.company_id)
        today = utcnow().astimezone(ZoneInfo(company.timezone)).date()
        if data.day > today or data.day < today - timedelta(days=31):
            raise BadRequestError("Log time for today or the past 31 days.", code="invalid_day")
        assert access.me is not None
        seconds = data.minutes * 60
        # Today's entry ends now (never in the future); earlier days are placed from 09:00 local time.
        if data.day == today:
            start = utcnow() - timedelta(seconds=seconds)
        else:
            start = datetime.combine(data.day, time(9), tzinfo=ZoneInfo(company.timezone))
        entry = TimeEntry(
            company_id=principal.company_id,
            task_id=task.id,
            project_id=task.project_id,
            employee_id=access.me,
            started_at=start,
            ended_at=start + timedelta(seconds=seconds),
            seconds=seconds,
            source="manual",
            note=data.note,
        )
        await self._time.create(principal.company_id, entry)
        await self._tasks.inc(principal.company_id, task.id, "time_spent_seconds", seconds)
        await self._log(access, task, "time_logged", minutes=data.minutes, day=str(data.day))
        people = await self._people(principal.company_id, [access.me])
        return TimeEntryOut(
            id=str(entry.id),
            task_id=str(task.id),
            started_at=entry.started_at,
            ended_at=entry.ended_at,
            seconds=seconds,
            source="manual",
            note=entry.note,
            employee=employee_ref(people[access.me]) if access.me in people else None,
        )

    # ------------------------------------------------------------------ dashboards
    async def my_work(self, principal: Principal) -> MyWork:
        access = await self.access(principal)
        timer = await self.timer(principal)
        if not access.me:
            return MyWork(
                has_employee_record=False,
                timer=timer,
                current_task=None,
                today=[],
                overdue=[],
                upcoming=[],
                assigned=[],
                recently_completed=[],
                counts={},
            )
        company_id = principal.company_id
        tz = ZoneInfo((await self._company(company_id)).timezone)
        today = utcnow().astimezone(tz).date()
        visible = {
            p.id: p
            for p in await self._projects.visible(
                company_id, {**(access.project_query() or {}), "status": ProjectStatus.ACTIVE}
            )
        }
        mine = await self._tasks.query(
            company_id,
            {
                "project_id": {"$in": list(visible)},
                "assignee_ids": access.me,
                "status": {"$ne": TaskStatus.COMPLETED},
            },
            limit=1000,
        )
        outs = await self._tasks_out(access, mine, visible)
        by_id = {o.id: o for o in outs}
        current = timer.task or next(
            (
                by_id[str(t.id)]
                for t in sorted(mine, key=lambda t: t.updated_at, reverse=True)
                if t.status == TaskStatus.IN_PROGRESS
            ),
            None,
        )
        today_list = [
            o for o in outs if not o.overdue and (o.due_date == today or o.status == TaskStatus.IN_PROGRESS)
        ]
        overdue = sorted((o for o in outs if o.overdue), key=lambda o: o.due_date or today)
        upcoming = sorted(
            (
                o
                for o in outs
                if o.due_date and today < o.due_date <= today + timedelta(days=7) and o not in today_list
            ),
            key=lambda o: o.due_date or today,
        )
        start = datetime.combine(today, time.min, tzinfo=UTC) - timedelta(days=7)
        done_recently = await self._tasks.query(
            company_id,
            {
                "project_id": {"$in": list(visible)},
                "assignee_ids": access.me,
                "completed_at": {"$gte": start},
            },
            sort=[("completed_at", -1)],
            limit=500,
        )
        done_today = [
            t
            for t in done_recently
            if t.completed_at and _aware(t.completed_at).astimezone(tz).date() == today
        ]
        assigned = sorted(outs, key=_urgency)
        return MyWork(
            has_employee_record=True,
            timer=timer,
            current_task=current,
            today=today_list,
            overdue=overdue,
            upcoming=upcoming,
            assigned=assigned,
            recently_completed=await self._tasks_out(access, done_recently[:10], visible),
            counts={
                "open": len(outs),
                "in_progress": sum(1 for o in outs if o.status == TaskStatus.IN_PROGRESS),
                "blocked": sum(1 for o in outs if o.status == TaskStatus.BLOCKED),
                "overdue": len(overdue),
                "completed_today": len(done_today),
            },
        )

    async def summary(
        self, principal: Principal, start: date, end: date, team_id: str | None, project_id: str | None
    ) -> WorkSummary:
        """Completion and time for the people in scope (managers)."""
        if end < start or (end - start).days >= MAX_SUMMARY_DAYS:
            raise BadRequestError(
                f"Choose a period of at most {MAX_SUMMARY_DAYS} days.", code="invalid_range"
            )
        access = await self.access(principal)
        company = await self._company(principal.company_id)
        tz = ZoneInfo(company.timezone)
        lo = datetime.combine(start, time.min, tzinfo=tz)
        hi = datetime.combine(end + timedelta(days=1), time.min, tzinfo=tz)
        today = utcnow().astimezone(tz).date()
        scope = await self._scopes.employee_scope(principal)
        clauses: list[dict[str, Any]] = [{"status": {"$ne": EmployeeStatus.TERMINATED}}]
        if scope.filter:
            clauses.append(scope.filter)
        if team := parse_ref(team_id, "team_id"):
            clauses.append({"team_id": team})
        people_ids = await self._employees.ids_matching(principal.company_id, {"$and": clauses})
        people = await self._employees.find_by_ids(principal.company_id, people_ids)

        if project_id:
            projects = [await self._project(access, project_id)]
        else:
            projects = await self._projects.visible(
                principal.company_id, {**(access.project_query() or {}), "status": ProjectStatus.ACTIVE}
            )
        project_ids = [p.id for p in projects]
        tasks = await self._tasks.query(
            principal.company_id, {"project_id": {"$in": project_ids}, "parent_id": None}, limit=50_000
        )
        people_set = set(people_ids)
        in_scope = [
            t
            for t in tasks
            if people_set.intersection(t.assignee_ids) or (not t.assignee_ids and access.manage_all)
        ]
        completed = [t for t in in_scope if t.completed_at and lo <= _aware(t.completed_at) < hi]
        with_due = [t for t in completed if t.due_date]
        on_time = [
            t
            for t in with_due
            if t.completed_at
            and t.due_date
            and _aware(t.completed_at).astimezone(tz).date() <= _aware(t.due_date).date()
        ]
        open_tasks = [t for t in in_scope if t.status != TaskStatus.COMPLETED]
        overdue = [t for t in open_tasks if t.due_date and _aware(t.due_date).date() < today]
        blocked = [t for t in open_tasks if t.status == TaskStatus.BLOCKED]
        by_project = {p.id: p for p in projects}

        entries = await self._time.overlapping(principal.company_id, people_ids, lo, hi)
        project_set = set(project_ids)
        entries = [e for e in entries if e.project_id in project_set]
        now = utcnow()
        seconds_by_person: dict[ObjectId, float] = defaultdict(float)
        for e in entries:
            e_end = _aware(e.ended_at) if e.ended_at else now
            seconds_by_person[e.employee_id] += max(
                0.0, (min(e_end, hi) - max(_aware(e.started_at), lo)).total_seconds()
            )

        # One pass over the tasks, indexed by assignee (a scan per person was quadratic at 1,000 people).
        assigned_to: dict[ObjectId, list[Task]] = defaultdict(list)
        for t in in_scope:
            for assignee in t.assignee_ids:
                if assignee in people_set:
                    assigned_to[assignee].append(t)
        overdue_ids = {t.id for t in overdue}
        completed_ids = {t.id for t in completed}
        members = []
        for pid in people_ids:
            assigned = assigned_to.get(pid, [])
            if not assigned and pid not in seconds_by_person:
                continue
            members.append(
                MemberWorkload(
                    employee=employee_ref(people[pid]),
                    open_tasks=sum(1 for t in assigned if t.status != TaskStatus.COMPLETED),
                    in_progress=sum(1 for t in assigned if t.status == TaskStatus.IN_PROGRESS),
                    blocked=sum(1 for t in assigned if t.status == TaskStatus.BLOCKED),
                    overdue=sum(1 for t in assigned if t.id in overdue_ids),
                    completed_in_period=sum(1 for t in assigned if t.id in completed_ids),
                    time_spent_seconds=round(seconds_by_person.get(pid, 0.0)),
                )
            )
        members.sort(key=lambda m: m.employee.full_name.lower())
        return WorkSummary(
            start=start,
            end=end,
            timezone=company.timezone,
            completed=len(completed),
            created=sum(1 for t in in_scope if lo <= _aware(t.created_at) < hi),
            open=len(open_tasks),
            overdue=len(overdue),
            on_time_completed=len(on_time),
            on_time_rate=round(100 * len(on_time) / len(with_due)) if with_due else None,
            time_spent_seconds=round(sum(seconds_by_person.values())),
            blocked=len(blocked),
            members=members,
            projects=await self._projects_out(access, projects),
            blocked_tasks=sorted(
                await self._tasks_out(access, blocked[:SUMMARY_TASK_LIMIT], by_project), key=_urgency
            ),
            overdue_tasks=sorted(
                await self._tasks_out(
                    access,
                    sorted(overdue, key=lambda t: _aware(t.due_date) if t.due_date else hi)[
                        :SUMMARY_TASK_LIMIT
                    ],
                    by_project,
                ),
                key=_urgency,
            ),
        )
