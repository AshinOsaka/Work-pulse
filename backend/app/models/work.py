"""Projects and tasks: the work itself, its conversation, its files and the time spent on it."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import Field

from app.models.base import PyObjectId, TenantModel


class ProjectStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class TaskStatus(StrEnum):
    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    BLOCKED = "BLOCKED"
    IN_REVIEW = "IN_REVIEW"
    COMPLETED = "COMPLETED"


class TaskPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class Project(TenantModel):
    name: str
    #: Short prefix for task references, e.g. "WEB" -> WEB-42.
    key: str
    description: str | None = None
    color: str = "indigo"
    status: ProjectStatus = ProjectStatus.ACTIVE
    owner_employee_id: PyObjectId | None = None
    member_ids: list[PyObjectId] = Field(default_factory=list)
    due_date: datetime | None = None
    #: Last task number issued (task references are KEY-number).
    task_counter: int = 0
    created_by: PyObjectId | None = None


class Task(TenantModel):
    project_id: PyObjectId
    number: int
    title: str
    description: str | None = None
    status: TaskStatus = TaskStatus.TODO
    priority: TaskPriority = TaskPriority.MEDIUM
    assignee_ids: list[PyObjectId] = Field(default_factory=list)
    #: Subtasks point to their parent (one level deep).
    parent_id: PyObjectId | None = None
    due_date: datetime | None = None
    #: When work is planned to start (timeline); optional.
    start_date: datetime | None = None
    #: Free-form tags, normalised to lower case (see `schemas.work.normalize_labels`).
    labels: list[str] = Field(default_factory=list)
    milestone_id: PyObjectId | None = None
    #: Ordering within a status column of the board.
    rank: float = 0.0
    estimate_minutes: int | None = None
    completed_at: datetime | None = None
    created_by_employee_id: PyObjectId | None = None
    #: Rolled up from time entries for fast lists.
    time_spent_seconds: int = 0
    comment_count: int = 0
    attachment_count: int = 0


class Milestone(TenantModel):
    """A dated goal within a project; tasks belong to at most one. Progress is derived from its tasks."""

    project_id: PyObjectId
    name: str
    description: str | None = None
    due_date: datetime | None = None
    #: Set when someone marks the milestone as reached.
    closed_at: datetime | None = None
    created_by_employee_id: PyObjectId | None = None


class TaskComment(TenantModel):
    task_id: PyObjectId
    author_employee_id: PyObjectId
    body: str
    edited_at: datetime | None = None


class TaskActivity(TenantModel):
    task_id: PyObjectId
    project_id: PyObjectId
    actor_employee_id: PyObjectId | None = None
    #: created, status_changed, assigned, unassigned, priority_changed, due_changed, renamed, commented,
    #: attachment_added, attachment_removed, timer_started, timer_stopped, time_logged, subtask_added
    kind: str
    data: dict[str, Any] = Field(default_factory=dict)


class TaskAttachment(TenantModel):
    task_id: PyObjectId
    uploaded_by_employee_id: PyObjectId | None = None
    filename: str
    content_type: str
    size_bytes: int
    #: Encrypted in private object storage; served only through signed, viewer-bound URLs.
    object_key: str


class TimeEntry(TenantModel):
    task_id: PyObjectId
    project_id: PyObjectId
    employee_id: PyObjectId
    started_at: datetime
    #: None while the timer is running (at most one running entry per employee).
    ended_at: datetime | None = None
    seconds: int = 0
    source: str = "timer"  # "timer" or "manual"
    note: str | None = None
