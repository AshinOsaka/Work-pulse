"""Who may see and change which projects and tasks.

* ``PROJECT_MANAGE`` (admins, managers): every project in the workspace; create, edit, archive, members.
* ``TASK_MANAGE`` (team leads, managers): projects with at least one member in their access scope; manage
  any task in them (create, assign, edit, move, delete).
* Everyone else: projects they are a member of. Members create tasks, comment, attach files and log
  time; they edit tasks they created or are assigned to.

Anything not visible is reported as not found (404), never forbidden.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bson import ObjectId

from app.auth.permissions import Permission
from app.auth.principal import Principal
from app.models.work import Project, Task


@dataclass(frozen=True)
class WorkAccess:
    principal: Principal
    me: ObjectId | None
    manage_all: bool
    task_manager: bool
    #: Employees in the requester's scope (for TASK_MANAGE without PROJECT_MANAGE).
    scope_ids: frozenset[ObjectId]

    @classmethod
    def build(cls, principal: Principal, scope_ids: set[ObjectId] | None) -> WorkAccess:
        return cls(
            principal=principal,
            me=principal.user.employee_id,
            manage_all=principal.has(Permission.PROJECT_MANAGE),
            task_manager=principal.has(Permission.TASK_MANAGE),
            scope_ids=frozenset(scope_ids or ()),
        )

    def project_query(self) -> dict[str, Any] | None:
        """Mongo filter for visible projects (None = all)."""
        if self.manage_all:
            return None
        ids = set(self.scope_ids) if self.task_manager else set()
        if self.me:
            ids.add(self.me)
        return {"member_ids": {"$in": list(ids)}}

    def sees_project(self, project: Project) -> bool:
        if self.manage_all:
            return True
        members = set(project.member_ids)
        if self.me in members:
            return True
        return self.task_manager and bool(members & self.scope_ids)

    def is_member(self, project: Project) -> bool:
        return self.me is not None and self.me in project.member_ids

    def manages_project(self, project: Project) -> bool:
        return self.manage_all or (self.me is not None and project.owner_employee_id == self.me)

    def manages_tasks(self, project: Project) -> bool:
        return (
            self.manage_all
            or (self.task_manager and self.sees_project(project))
            or self.manages_project(project)
        )

    def can_create_task(self, project: Project) -> bool:
        return self.manages_tasks(project) or self.is_member(project)

    def can_edit_task(self, project: Project, task: Task) -> bool:
        if self.manages_tasks(project):
            return True
        return self.me is not None and (
            self.me in task.assignee_ids or task.created_by_employee_id == self.me
        )

    def can_delete_task(self, project: Project, task: Task) -> bool:
        return self.manages_tasks(project) or (self.me is not None and task.created_by_employee_id == self.me)

    def can_track_time(self, project: Project) -> bool:
        return self.me is not None and (self.is_member(project) or self.manages_tasks(project))
