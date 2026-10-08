"""Projects, tasks, comments, activity, attachments and time entries."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from bson import ObjectId
from pymongo import ASCENDING, DESCENDING, IndexModel, ReturnDocument
from pymongo.errors import DuplicateKeyError

from app.models.work import Milestone, Project, Task, TaskActivity, TaskAttachment, TaskComment, TimeEntry
from app.repositories.base import CASE_INSENSITIVE, TenantRepository


class ProjectRepository(TenantRepository[Project]):
    collection_name = "projects"
    model = Project
    indexes = (
        IndexModel([("company_id", ASCENDING), ("key", ASCENDING)], name="uniq_company_key", unique=True),
        IndexModel(
            [("company_id", ASCENDING), ("name", ASCENDING)], name="company_name", collation=CASE_INSENSITIVE
        ),
        IndexModel([("company_id", ASCENDING), ("member_ids", ASCENDING)], name="company_members"),
        IndexModel([("company_id", ASCENDING), ("status", ASCENDING)], name="company_status"),
    )

    async def next_number(self, company_id: ObjectId, project_id: ObjectId) -> int:
        doc = await self._collection.find_one_and_update(
            self._scoped(company_id, {"_id": project_id}),
            {"$inc": {"task_counter": 1}},
            return_document=ReturnDocument.AFTER,
            projection={"task_counter": 1},
        )
        if doc is None:
            raise LookupError("project not found")
        return int(doc["task_counter"])

    async def visible(self, company_id: ObjectId, query: Mapping[str, Any] | None) -> list[Project]:
        return await self._find_many(self._scoped(company_id, query), sort=[("name", ASCENDING)], limit=2000)


class TaskRepository(TenantRepository[Task]):
    collection_name = "tasks"
    model = Task
    indexes = (
        IndexModel(
            [("company_id", ASCENDING), ("project_id", ASCENDING), ("number", ASCENDING)],
            name="uniq_project_number",
            unique=True,
        ),
        IndexModel(
            [
                ("company_id", ASCENDING),
                ("project_id", ASCENDING),
                ("status", ASCENDING),
                ("rank", ASCENDING),
            ],
            name="project_board",
        ),
        IndexModel(
            [("company_id", ASCENDING), ("assignee_ids", ASCENDING), ("status", ASCENDING)],
            name="assignee_status",
        ),
        IndexModel([("company_id", ASCENDING), ("parent_id", ASCENDING)], name="parent"),
        IndexModel([("company_id", ASCENDING), ("due_date", ASCENDING)], name="due"),
        IndexModel([("company_id", ASCENDING), ("completed_at", DESCENDING)], name="completed"),
        IndexModel(
            [("company_id", ASCENDING), ("project_id", ASCENDING), ("labels", ASCENDING)], name="labels"
        ),
        IndexModel([("company_id", ASCENDING), ("milestone_id", ASCENDING)], name="milestone"),
    )

    async def query(
        self,
        company_id: ObjectId,
        query: Mapping[str, Any],
        *,
        limit: int = 2000,
        sort: Sequence[tuple[str, int]] | None = None,
    ) -> list[Task]:
        return await self._find_many(
            self._scoped(company_id, query),
            sort=sort or [("status", 1), ("rank", 1), ("number", 1)],
            limit=limit,
        )

    async def max_rank(self, company_id: ObjectId, project_id: ObjectId, status: str) -> float:
        found = await self._find_many(
            self._scoped(company_id, {"project_id": project_id, "status": status}),
            sort=[("rank", DESCENDING)],
            limit=1,
        )
        return found[0].rank if found else 0.0

    async def set_ranks(self, company_id: ObjectId, ranks: Mapping[ObjectId, float]) -> None:
        for task_id, rank in ranks.items():
            await self._collection.update_one(
                self._scoped(company_id, {"_id": task_id}), {"$set": {"rank": rank}}
            )

    async def inc(self, company_id: ObjectId, task_id: ObjectId, field: str, by: int) -> None:
        await self._collection.update_one(self._scoped(company_id, {"_id": task_id}), {"$inc": {field: by}})

    async def counts_by_project(
        self, company_id: ObjectId, project_ids: Sequence[ObjectId]
    ) -> dict[ObjectId, dict[str, int]]:
        rows = await (
            await self._collection.aggregate(
                [
                    {
                        "$match": {
                            "company_id": company_id,
                            "project_id": {"$in": list(project_ids)},
                            "parent_id": None,
                        }
                    },
                    {
                        "$group": {
                            "_id": {"p": "$project_id", "s": "$status"},
                            "n": {"$sum": 1},
                            "t": {"$sum": "$time_spent_seconds"},
                        }
                    },
                ]
            )
        ).to_list()
        out: dict[ObjectId, dict[str, int]] = {}
        for row in rows:
            entry = out.setdefault(row["_id"]["p"], {"time_spent_seconds": 0})
            entry[row["_id"]["s"]] = row["n"]
            entry["time_spent_seconds"] += row["t"]
        return out

    async def label_counts(self, company_id: ObjectId, project_id: ObjectId) -> list[tuple[str, int]]:
        rows = await (
            await self._collection.aggregate(
                [
                    {"$match": {"company_id": company_id, "project_id": project_id}},
                    {"$unwind": "$labels"},
                    {"$group": {"_id": "$labels", "n": {"$sum": 1}}},
                    {"$sort": {"n": -1, "_id": 1}},
                    {"$limit": 200},
                ]
            )
        ).to_list()
        return [(row["_id"], row["n"]) for row in rows]

    async def counts_by_milestone(
        self, company_id: ObjectId, milestone_ids: Sequence[ObjectId]
    ) -> dict[ObjectId, dict[str, int]]:
        """Top-level tasks per milestone: total and completed."""
        rows = await (
            await self._collection.aggregate(
                [
                    {
                        "$match": {
                            "company_id": company_id,
                            "milestone_id": {"$in": list(milestone_ids)},
                            "parent_id": None,
                        }
                    },
                    {
                        "$group": {
                            "_id": "$milestone_id",
                            "total": {"$sum": 1},
                            "completed": {"$sum": {"$cond": [{"$eq": ["$status", "COMPLETED"]}, 1, 0]}},
                        }
                    },
                ]
            )
        ).to_list()
        return {row["_id"]: {"total": row["total"], "completed": row["completed"]} for row in rows}

    async def clear_milestone(self, company_id: ObjectId, milestone_id: ObjectId) -> None:
        await self._collection.update_many(
            self._scoped(company_id, {"milestone_id": milestone_id}), {"$set": {"milestone_id": None}}
        )

    async def remove_member_assignments(
        self, company_id: ObjectId, project_id: ObjectId, employee_ids: Sequence[ObjectId]
    ) -> None:
        await self._collection.update_many(
            self._scoped(company_id, {"project_id": project_id}),
            {"$pull": {"assignee_ids": {"$in": list(employee_ids)}}},
        )

    async def delete_tree(self, company_id: ObjectId, task_id: ObjectId) -> list[ObjectId]:
        """Delete a task and its subtasks; returns the ids removed."""
        ids = [task_id, *[t.id for t in await self.query(company_id, {"parent_id": task_id})]]
        await self._collection.delete_many(self._scoped(company_id, {"_id": {"$in": ids}}))
        return ids


class MilestoneRepository(TenantRepository[Milestone]):
    collection_name = "milestones"
    model = Milestone
    indexes = (
        IndexModel(
            [("company_id", ASCENDING), ("project_id", ASCENDING), ("due_date", ASCENDING)],
            name="project_due",
        ),
    )

    async def for_project(self, company_id: ObjectId, project_id: ObjectId) -> list[Milestone]:
        return await self._find_many(
            self._scoped(company_id, {"project_id": project_id}),
            sort=[("due_date", ASCENDING), ("created_at", ASCENDING)],
            limit=500,
        )


class TaskCommentRepository(TenantRepository[TaskComment]):
    collection_name = "task_comments"
    model = TaskComment
    indexes = (
        IndexModel(
            [("company_id", ASCENDING), ("task_id", ASCENDING), ("created_at", ASCENDING)],
            name="task_created",
        ),
    )

    async def for_task(self, company_id: ObjectId, task_id: ObjectId) -> list[TaskComment]:
        return await self._find_many(
            self._scoped(company_id, {"task_id": task_id}), sort=[("created_at", ASCENDING)], limit=1000
        )

    async def delete_for_tasks(self, company_id: ObjectId, task_ids: Sequence[ObjectId]) -> None:
        await self._collection.delete_many(self._scoped(company_id, {"task_id": {"$in": list(task_ids)}}))


class TaskActivityRepository(TenantRepository[TaskActivity]):
    collection_name = "task_activity"
    model = TaskActivity
    indexes = (
        IndexModel(
            [("company_id", ASCENDING), ("task_id", ASCENDING), ("created_at", DESCENDING)],
            name="task_created",
        ),
        IndexModel(
            [("company_id", ASCENDING), ("project_id", ASCENDING), ("created_at", DESCENDING)],
            name="project_created",
        ),
    )

    async def for_task(self, company_id: ObjectId, task_id: ObjectId, limit: int = 200) -> list[TaskActivity]:
        return await self._find_many(
            self._scoped(company_id, {"task_id": task_id}), sort=[("created_at", DESCENDING)], limit=limit
        )

    async def delete_for_tasks(self, company_id: ObjectId, task_ids: Sequence[ObjectId]) -> None:
        await self._collection.delete_many(self._scoped(company_id, {"task_id": {"$in": list(task_ids)}}))

    async def for_project(
        self, company_id: ObjectId, project_id: ObjectId, limit: int = 50
    ) -> list[TaskActivity]:
        return await self._find_many(
            self._scoped(company_id, {"project_id": project_id}),
            sort=[("created_at", DESCENDING)],
            limit=limit,
        )


class TaskAttachmentRepository(TenantRepository[TaskAttachment]):
    collection_name = "task_attachments"
    model = TaskAttachment
    indexes = (IndexModel([("company_id", ASCENDING), ("task_id", ASCENDING)], name="task"),)

    async def for_task(self, company_id: ObjectId, task_id: ObjectId) -> list[TaskAttachment]:
        return await self._find_many(
            self._scoped(company_id, {"task_id": task_id}), sort=[("created_at", ASCENDING)], limit=500
        )

    async def for_tasks(self, company_id: ObjectId, task_ids: Sequence[ObjectId]) -> list[TaskAttachment]:
        return await self._find_many(
            self._scoped(company_id, {"task_id": {"$in": list(task_ids)}}), limit=10_000
        )

    async def delete_for_tasks(self, company_id: ObjectId, task_ids: Sequence[ObjectId]) -> None:
        await self._collection.delete_many(self._scoped(company_id, {"task_id": {"$in": list(task_ids)}}))


class TimeEntryRepository(TenantRepository[TimeEntry]):
    collection_name = "time_entries"
    model = TimeEntry
    indexes = (
        # At most one running timer per employee, enforced by the database.
        IndexModel(
            [("company_id", ASCENDING), ("employee_id", ASCENDING)],
            name="uniq_running_timer",
            unique=True,
            partialFilterExpression={"ended_at": None},
        ),
        IndexModel(
            [("company_id", ASCENDING), ("employee_id", ASCENDING), ("started_at", DESCENDING)],
            name="employee_started",
        ),
        IndexModel(
            [("company_id", ASCENDING), ("task_id", ASCENDING), ("started_at", DESCENDING)],
            name="task_started",
        ),
        IndexModel(
            [("company_id", ASCENDING), ("project_id", ASCENDING), ("started_at", DESCENDING)],
            name="project_started",
        ),
    )

    async def running(self, company_id: ObjectId, employee_id: ObjectId) -> TimeEntry | None:
        return await self._find_one(self._scoped(company_id, {"employee_id": employee_id, "ended_at": None}))

    async def start(self, entry: TimeEntry) -> TimeEntry | None:
        try:
            return await self.create(entry.company_id, entry)
        except DuplicateKeyError:
            return None

    async def query_running_for_task(self, company_id: ObjectId, task_id: ObjectId) -> list[TimeEntry]:
        return await self._find_many(
            self._scoped(company_id, {"task_id": task_id, "ended_at": None}), limit=1000
        )

    async def stop(
        self, company_id: ObjectId, entry_id: ObjectId, at: datetime, seconds: int
    ) -> TimeEntry | None:
        return await self._update_one(
            self._scoped(company_id, {"_id": entry_id, "ended_at": None}),
            {"ended_at": at, "seconds": seconds},
        )

    async def for_task(self, company_id: ObjectId, task_id: ObjectId) -> list[TimeEntry]:
        return await self._find_many(
            self._scoped(company_id, {"task_id": task_id}), sort=[("started_at", DESCENDING)], limit=500
        )

    async def overlapping(
        self, company_id: ObjectId, employee_ids: Sequence[ObjectId], start: datetime, end: datetime
    ) -> list[TimeEntry]:
        return await self._find_many(
            self._scoped(
                company_id,
                {
                    "employee_id": {"$in": list(employee_ids)},
                    "started_at": {"$lt": end},
                    "$or": [{"ended_at": None}, {"ended_at": {"$gt": start}}],
                },
            ),
            limit=100_000,
        )

    async def for_project(self, company_id: ObjectId, project_id: ObjectId) -> list[TimeEntry]:
        return await self._find_many(self._scoped(company_id, {"project_id": project_id}), limit=100_000)

    async def delete_for_tasks(self, company_id: ObjectId, task_ids: Sequence[ObjectId]) -> None:
        await self._collection.delete_many(self._scoped(company_id, {"task_id": {"$in": list(task_ids)}}))
