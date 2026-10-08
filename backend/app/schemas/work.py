"""Projects & tasks API."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Literal

from pydantic import Field, field_validator

from app.models.work import ProjectStatus, TaskPriority, TaskStatus
from app.schemas.common import APIModel
from app.schemas.organization import EmployeeRef

ObjectIdPattern = r"^[0-9a-f]{24}$"
MAX_LABELS = 10
MAX_LABEL_LENGTH = 30


def normalize_labels(values: list[str]) -> list[str]:
    """Trim, collapse spaces, lower-case and de-duplicate, keeping the order given."""
    out: list[str] = []
    for raw in values:
        label = re.sub(r"\s+", " ", raw).strip().lower()
        if not label:
            continue
        if len(label) > MAX_LABEL_LENGTH:
            raise ValueError(f"Labels can be at most {MAX_LABEL_LENGTH} characters.")
        if any(ord(c) < 32 for c in label) or "," in label:
            raise ValueError("Labels can't contain commas or control characters.")
        if label not in out:
            out.append(label)
    if len(out) > MAX_LABELS:
        raise ValueError(f"Use at most {MAX_LABELS} labels.")
    return out


PROJECT_COLORS = ("indigo", "blue", "teal", "green", "amber", "orange", "red", "pink", "violet", "slate")


# --------------------------------------------------------------------------- projects
class ProjectStats(APIModel):
    total: int
    completed: int
    by_status: dict[TaskStatus, int]
    overdue: int
    time_spent_seconds: int
    #: completed / total, 0-100 (top-level tasks; subtasks count towards their parent's progress only).
    progress: int


class ProjectOut(APIModel):
    id: str
    name: str
    key: str
    description: str | None
    color: str
    status: ProjectStatus
    owner: EmployeeRef | None
    members: list[EmployeeRef]
    due_date: date | None
    stats: ProjectStats
    created_at: datetime
    #: What the requester may do here: edit the project itself / manage its tasks and milestones.
    can_manage: bool
    can_manage_tasks: bool


class ProjectCreate(APIModel):
    name: str = Field(min_length=2, max_length=80)
    key: str | None = Field(default=None, min_length=2, max_length=6)
    description: str | None = Field(default=None, max_length=2000)
    color: str = "indigo"
    owner_employee_id: str | None = Field(default=None, pattern=ObjectIdPattern)
    member_ids: list[str] = Field(default_factory=list, max_length=500)
    due_date: date | None = None

    @field_validator("key")
    @classmethod
    def _key(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip().upper()
        if not re.fullmatch(r"[A-Z][A-Z0-9]{1,5}", value):
            raise ValueError("Use 2-6 letters or digits, starting with a letter.")
        return value

    @field_validator("color")
    @classmethod
    def _color(cls, value: str) -> str:
        if value not in PROJECT_COLORS:
            raise ValueError("Unknown colour.")
        return value


class ProjectUpdate(APIModel):
    name: str | None = Field(default=None, min_length=2, max_length=80)
    description: str | None = Field(default=None, max_length=2000)
    color: str | None = None
    owner_employee_id: str | None = Field(default=None, pattern=ObjectIdPattern)
    due_date: date | None = None
    status: ProjectStatus | None = None

    @field_validator("color")
    @classmethod
    def _color(cls, value: str | None) -> str | None:
        if value is not None and value not in PROJECT_COLORS:
            raise ValueError("Unknown colour.")
        return value


class ProjectMembers(APIModel):
    member_ids: list[str] = Field(max_length=500)


# --------------------------------------------------------------------------- tasks
class TaskOut(APIModel):
    id: str
    project_id: str
    project_key: str
    reference: str
    title: str
    description: str | None
    status: TaskStatus
    priority: TaskPriority
    assignees: list[EmployeeRef]
    parent_id: str | None
    due_date: date | None
    start_date: date | None
    labels: list[str]
    milestone_id: str | None
    overdue: bool
    rank: float
    estimate_minutes: int | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    time_spent_seconds: int
    comment_count: int
    attachment_count: int
    subtask_total: int
    subtask_done: int
    #: The requester's running timer is on this task.
    timer_running: bool
    can_edit: bool


class TaskCreate(APIModel):
    project_id: str = Field(pattern=ObjectIdPattern)
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10_000)
    status: TaskStatus = TaskStatus.TODO
    priority: TaskPriority = TaskPriority.MEDIUM
    assignee_ids: list[str] = Field(default_factory=list, max_length=20)
    parent_id: str | None = Field(default=None, pattern=ObjectIdPattern)
    due_date: date | None = None
    start_date: date | None = None
    labels: list[str] = Field(default_factory=list, max_length=50)
    milestone_id: str | None = Field(default=None, pattern=ObjectIdPattern)
    estimate_minutes: int | None = Field(default=None, ge=1, le=100_000)

    @field_validator("labels")
    @classmethod
    def _labels(cls, value: list[str]) -> list[str]:
        return normalize_labels(value)


class TaskUpdate(APIModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=10_000)
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    assignee_ids: list[str] | None = Field(default=None, max_length=20)
    due_date: date | None = None
    estimate_minutes: int | None = Field(default=None, ge=1, le=100_000)
    #: Explicitly clear the due date (null in `due_date` means "unchanged").
    clear_due_date: bool = False
    #: For these three, sending null clears the value; leaving the field out keeps it.
    start_date: date | None = None
    labels: list[str] | None = Field(default=None, max_length=50)
    milestone_id: str | None = Field(default=None, pattern=ObjectIdPattern)

    @field_validator("labels")
    @classmethod
    def _labels(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else normalize_labels(value)


# --------------------------------------------------------------------------- milestones & labels
class MilestoneOut(APIModel):
    id: str
    project_id: str
    name: str
    description: str | None
    due_date: date | None
    closed: bool
    closed_at: datetime | None
    #: Top-level tasks in the milestone.
    total: int
    completed: int
    #: completed / total, 0-100 (0 when empty).
    progress: int
    #: Due date passed and not closed.
    overdue: bool
    can_manage: bool


class MilestoneCreate(APIModel):
    name: str = Field(min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=2000)
    due_date: date | None = None


class MilestoneUpdate(APIModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=2000)
    #: Null clears the date; leaving the field out keeps it.
    due_date: date | None = None
    closed: bool | None = None


class LabelCount(APIModel):
    name: str
    count: int


class TaskMove(APIModel):
    status: TaskStatus
    #: Position within the target column (0 = top).
    index: int = Field(ge=0, le=10_000)


class CommentOut(APIModel):
    id: str
    author: EmployeeRef | None
    body: str
    created_at: datetime
    edited_at: datetime | None
    can_edit: bool


class CommentCreate(APIModel):
    body: str = Field(min_length=1, max_length=5000)


class ActivityOut(APIModel):
    id: str
    kind: str
    actor: EmployeeRef | None
    data: dict[str, Any]
    created_at: datetime


class AttachmentOut(APIModel):
    id: str
    filename: str
    content_type: str
    size_bytes: int
    uploaded_by: EmployeeRef | None
    created_at: datetime
    #: Short-lived, viewer-bound download link.
    download_url: str
    can_delete: bool


class TimeEntryOut(APIModel):
    id: str
    task_id: str
    employee: EmployeeRef | None
    started_at: datetime
    ended_at: datetime | None
    seconds: int
    source: Literal["timer", "manual"]
    note: str | None


class ManualTime(APIModel):
    minutes: int = Field(ge=1, le=24 * 60)
    day: date
    note: str | None = Field(default=None, max_length=300)


class TaskDetail(TaskOut):
    project_name: str
    subtasks: list[TaskOut]
    comments: list[CommentOut]
    activity: list[ActivityOut]
    attachments: list[AttachmentOut]
    time_entries: list[TimeEntryOut]


# --------------------------------------------------------------------------- timer & dashboards
class TimerOut(APIModel):
    running: bool
    task: TaskOut | None
    started_at: datetime | None
    #: Seconds on the running entry so far.
    elapsed_seconds: int
    #: Total time logged by the requester today (company timezone), including the running entry.
    today_seconds: int


class MyWork(APIModel):
    has_employee_record: bool
    timer: TimerOut
    current_task: TaskOut | None
    today: list[TaskOut]
    overdue: list[TaskOut]
    upcoming: list[TaskOut]
    #: Every open task assigned to me (most urgent first).
    assigned: list[TaskOut]
    #: Completed in the last 7 days, newest first.
    recently_completed: list[TaskOut]
    counts: dict[str, int]


class MemberWorkload(APIModel):
    employee: EmployeeRef
    open_tasks: int
    in_progress: int
    blocked: int
    overdue: int
    completed_in_period: int
    time_spent_seconds: int


class WorkSummary(APIModel):
    """Manager view: completion and time in scope for a period."""

    start: date
    end: date
    timezone: str
    completed: int
    created: int
    open: int
    overdue: int
    on_time_completed: int
    #: completed on or before the due date / completed with a due date, 0-100.
    on_time_rate: int | None
    time_spent_seconds: int
    blocked: int
    members: list[MemberWorkload]
    projects: list[ProjectOut]
    #: The tasks behind the counts (most urgent first; capped).
    blocked_tasks: list[TaskOut]
    overdue_tasks: list[TaskOut]
