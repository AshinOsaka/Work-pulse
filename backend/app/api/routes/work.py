"""Projects & tasks: projects, tasks and subtasks, board moves, comments, attachments, timers, dashboards."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal
from urllib.parse import quote

from fastapi import APIRouter, Query, Request, Response, status

from app.api.deps import RequestMetaDep, WorkServiceDep
from app.auth.dependencies import CurrentPrincipal
from app.core.dependencies import SettingsDep
from app.core.exceptions import PayloadTooLargeError
from app.models.work import TaskPriority, TaskStatus
from app.schemas.common import ObjectIdStr
from app.schemas.work import (
    ActivityOut,
    AttachmentOut,
    CommentCreate,
    CommentOut,
    LabelCount,
    ManualTime,
    MilestoneCreate,
    MilestoneOut,
    MilestoneUpdate,
    MyWork,
    ProjectCreate,
    ProjectMembers,
    ProjectOut,
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
from app.services.work.service import INLINE_TYPES, MAX_ATTACHMENT_BYTES

router = APIRouter(tags=["projects & tasks"])


# --------------------------------------------------------------------------- projects
@router.get("/projects", response_model=list[ProjectOut])
async def list_projects(
    principal: CurrentPrincipal, service: WorkServiceDep, include_archived: bool = False
) -> list[ProjectOut]:
    return await service.list_projects(principal, include_archived)


@router.post("/projects", response_model=ProjectOut, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate, principal: CurrentPrincipal, service: WorkServiceDep, meta: RequestMetaDep
) -> ProjectOut:
    return await service.create_project(principal, payload, meta)


@router.get("/projects/{project_id}", response_model=ProjectOut)
async def get_project(project_id: str, principal: CurrentPrincipal, service: WorkServiceDep) -> ProjectOut:
    return await service.get_project(principal, project_id)


@router.patch("/projects/{project_id}", response_model=ProjectOut)
async def update_project(
    project_id: str,
    payload: ProjectUpdate,
    principal: CurrentPrincipal,
    service: WorkServiceDep,
    meta: RequestMetaDep,
) -> ProjectOut:
    return await service.update_project(principal, project_id, payload, meta)


@router.put("/projects/{project_id}/members", response_model=ProjectOut)
async def set_project_members(
    project_id: str,
    payload: ProjectMembers,
    principal: CurrentPrincipal,
    service: WorkServiceDep,
    meta: RequestMetaDep,
) -> ProjectOut:
    return await service.set_members(principal, project_id, payload, meta)


@router.get("/projects/{project_id}/activity", response_model=list[ActivityOut])
async def project_activity(
    project_id: str, principal: CurrentPrincipal, service: WorkServiceDep
) -> list[ActivityOut]:
    return await service.project_activity(principal, project_id)


# --------------------------------------------------------------------------- tasks
@router.get("/tasks", response_model=list[TaskOut])
async def list_tasks(
    principal: CurrentPrincipal,
    service: WorkServiceDep,
    project_id: Annotated[ObjectIdStr | None, Query()] = None,
    assignee: Annotated[str | None, Query(max_length=24, description='An employee id, or "me"')] = None,
    team_id: Annotated[ObjectIdStr | None, Query()] = None,
    status_: Annotated[list[TaskStatus] | None, Query(alias="status")] = None,
    priority: TaskPriority | None = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
    due: Literal["overdue", "today", "week"] | None = None,
    include_subtasks: bool = False,
    limit: Annotated[int, Query(ge=1, le=2000)] = 1000,
    label: Annotated[str | None, Query(max_length=30)] = None,
    milestone_id: Annotated[
        str | None, Query(pattern=r"^([0-9a-f]{24}|none)$", description='A milestone id, or "none"')
    ] = None,
) -> list[TaskOut]:
    return await service.list_tasks(
        principal,
        project_id=project_id,
        assignee=assignee,
        team_id=team_id,
        statuses=status_,
        priority=priority.value if priority else None,
        search=search,
        due=due,
        include_subtasks=include_subtasks,
        limit=limit,
        label=label,
        milestone=milestone_id,
    )


# --------------------------------------------------------------------------- milestones & labels
@router.get("/projects/{project_id}/milestones", response_model=list[MilestoneOut])
async def list_milestones(
    project_id: str, principal: CurrentPrincipal, service: WorkServiceDep
) -> list[MilestoneOut]:
    return await service.list_milestones(principal, project_id)


@router.post(
    "/projects/{project_id}/milestones", response_model=MilestoneOut, status_code=status.HTTP_201_CREATED
)
async def create_milestone(
    project_id: str, payload: MilestoneCreate, principal: CurrentPrincipal, service: WorkServiceDep
) -> MilestoneOut:
    return await service.create_milestone(principal, project_id, payload)


@router.patch("/milestones/{milestone_id}", response_model=MilestoneOut)
async def update_milestone(
    milestone_id: str, payload: MilestoneUpdate, principal: CurrentPrincipal, service: WorkServiceDep
) -> MilestoneOut:
    return await service.update_milestone(principal, milestone_id, payload)


@router.delete("/milestones/{milestone_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_milestone(milestone_id: str, principal: CurrentPrincipal, service: WorkServiceDep) -> None:
    await service.delete_milestone(principal, milestone_id)


@router.get(
    "/projects/{project_id}/labels", response_model=list[LabelCount], summary="Labels used in a project"
)
async def project_labels(
    project_id: str, principal: CurrentPrincipal, service: WorkServiceDep
) -> list[LabelCount]:
    return await service.project_labels(principal, project_id)


@router.post("/tasks", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
async def create_task(payload: TaskCreate, principal: CurrentPrincipal, service: WorkServiceDep) -> TaskOut:
    return await service.create_task(principal, payload)


@router.get("/tasks/{task_id}", response_model=TaskDetail)
async def get_task(task_id: str, principal: CurrentPrincipal, service: WorkServiceDep) -> TaskDetail:
    return await service.get_task(principal, task_id)


@router.patch("/tasks/{task_id}", response_model=TaskOut)
async def update_task(
    task_id: str, payload: TaskUpdate, principal: CurrentPrincipal, service: WorkServiceDep
) -> TaskOut:
    return await service.update_task(principal, task_id, payload)


@router.post("/tasks/{task_id}/move", response_model=TaskOut, summary="Board drag & drop")
async def move_task(
    task_id: str, payload: TaskMove, principal: CurrentPrincipal, service: WorkServiceDep
) -> TaskOut:
    return await service.move_task(principal, task_id, payload)


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(task_id: str, principal: CurrentPrincipal, service: WorkServiceDep) -> Response:
    await service.delete_task(principal, task_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------- comments
@router.post("/tasks/{task_id}/comments", response_model=CommentOut, status_code=status.HTTP_201_CREATED)
async def add_comment(
    task_id: str, payload: CommentCreate, principal: CurrentPrincipal, service: WorkServiceDep
) -> CommentOut:
    return await service.add_comment(principal, task_id, payload)


@router.patch("/tasks/{task_id}/comments/{comment_id}", response_model=CommentOut)
async def edit_comment(
    task_id: str,
    comment_id: str,
    payload: CommentCreate,
    principal: CurrentPrincipal,
    service: WorkServiceDep,
) -> CommentOut:
    return await service.edit_comment(principal, task_id, comment_id, payload)


@router.delete("/tasks/{task_id}/comments/{comment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_comment(
    task_id: str, comment_id: str, principal: CurrentPrincipal, service: WorkServiceDep
) -> Response:
    await service.delete_comment(principal, task_id, comment_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# --------------------------------------------------------------------------- attachments
@router.post(
    "/tasks/{task_id}/attachments", response_model=AttachmentOut, status_code=status.HTTP_201_CREATED
)
async def upload_attachment(
    task_id: str,
    request: Request,
    principal: CurrentPrincipal,
    service: WorkServiceDep,
    filename: Annotated[str, Query(min_length=1, max_length=255)],
) -> AttachmentOut:
    """Raw file body (any type, up to 9 MB); the file name goes in the query string."""
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_ATTACHMENT_BYTES:
        raise PayloadTooLargeError("Attachments must be at most 9 MB.")
    chunks, total = [], 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > MAX_ATTACHMENT_BYTES:
            raise PayloadTooLargeError("Attachments must be at most 9 MB.")
        chunks.append(chunk)
    content_type = (
        request.headers.get("content-type", "application/octet-stream").split(";")[0].strip().lower()
    )
    return await service.add_attachment(principal, task_id, filename, content_type, b"".join(chunks))


@router.delete("/tasks/{task_id}/attachments/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_attachment(
    task_id: str, attachment_id: str, principal: CurrentPrincipal, service: WorkServiceDep
) -> Response:
    await service.delete_attachment(principal, task_id, attachment_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/task-files/{attachment_id}", include_in_schema=False)
async def download_attachment(
    attachment_id: str,
    service: WorkServiceDep,
    settings: SettingsDep,
    c: Annotated[str, Query(max_length=128)],
    u: Annotated[str, Query(max_length=128)],
    e: Annotated[int, Query()],
    s: Annotated[str, Query(max_length=128)],
) -> Response:
    """Signed, viewer-bound and re-authorised download. Only a few safe types are shown inline."""
    attachment, data = await service.read_attachment(
        attachment_id=attachment_id, company_id=c, user_id=u, expires=e, signature=s
    )
    inline = attachment.content_type in INLINE_TYPES
    disposition = "inline" if inline else "attachment"
    return Response(
        content=data,
        media_type=attachment.content_type if inline else "application/octet-stream",
        headers={
            "Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(attachment.filename)}",
            "Cache-Control": f"private, max-age={settings.screenshot_url_ttl_seconds}",
            "Content-Security-Policy": "default-src 'none'; sandbox",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
        },
    )


# --------------------------------------------------------------------------- time
@router.get("/me/timer", response_model=TimerOut)
async def my_timer(principal: CurrentPrincipal, service: WorkServiceDep) -> TimerOut:
    return await service.timer(principal)


@router.post("/tasks/{task_id}/timer/start", response_model=TimerOut, summary="Start (or switch) your timer")
async def start_timer(task_id: str, principal: CurrentPrincipal, service: WorkServiceDep) -> TimerOut:
    return await service.start_timer(principal, task_id)


@router.post("/me/timer/stop", response_model=TimerOut)
async def stop_timer(principal: CurrentPrincipal, service: WorkServiceDep) -> TimerOut:
    return await service.stop_timer(principal)


@router.post("/tasks/{task_id}/time", response_model=TimeEntryOut, status_code=status.HTTP_201_CREATED)
async def log_time(
    task_id: str, payload: ManualTime, principal: CurrentPrincipal, service: WorkServiceDep
) -> TimeEntryOut:
    return await service.log_time(principal, task_id, payload)


# --------------------------------------------------------------------------- dashboards
@router.get("/me/work", response_model=MyWork, summary="Current task, timer, today's and overdue tasks")
async def my_work(principal: CurrentPrincipal, service: WorkServiceDep) -> MyWork:
    return await service.my_work(principal)


@router.get("/work/summary", response_model=WorkSummary, summary="Task completion and time in scope")
async def work_summary(
    principal: CurrentPrincipal,
    service: WorkServiceDep,
    start: date,
    end: date,
    team_id: Annotated[ObjectIdStr | None, Query()] = None,
    project_id: Annotated[ObjectIdStr | None, Query()] = None,
) -> WorkSummary:
    return await service.summary(principal, start, end, team_id, project_id)
