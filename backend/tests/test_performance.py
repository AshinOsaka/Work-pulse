"""Phase 17: the performance work must never change what people see.

* The productivity day cache returns exactly what a fresh computation would, and is invalidated by rule changes and
  by late uploads for past days.
* The durable notification outbox loses nothing, survives a dispatcher being down, and hands work to whichever
  dispatcher runs next.
* The warm-up job fills the cache for past days.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi.testclient import TestClient

from app.models.notification import NotificationType
from app.services.notifications.notifier import AlertEvent
from tests.org_helpers import Workspace
from tests.test_agent_api import enrol_member, event
from tests.test_productivity_api import DAY, add_rule, at, report, segment, workday


def team_week(ws: Workspace) -> Any:
    day = DAY.date().isoformat()
    response = ws.get("/productivity/team", start=day, end=day)
    assert response.status_code == 200, response.text
    return response.json()


def test_cached_results_equal_a_fresh_computation(ws: Workspace, sync_db: Any) -> None:
    member, agent = enrol_member(ws, "Cara Cached")
    workday(agent)
    sync_db["productivity_daily"].delete_many({})
    cold = report(ws, member.employee_id).json()
    assert sync_db["productivity_daily"].count_documents({}) >= 1  # the past day was stored
    cached_entry = sync_db["productivity_daily"].find_one({"day": DAY.date().isoformat()})
    assert cached_entry["time"] is not None  # a settled past day carries its time accounting too
    warm = report(ws, member.employee_id).json()
    assert warm == cold
    assert team_week(ws) == team_week(ws)


def test_a_rule_change_is_reflected_immediately(ws: Workspace) -> None:
    member, agent = enrol_member(ws, "Rhea Rules")
    workday(agent)
    before = report(ws, member.employee_id).json()
    unclassified = before["totals"]["unclassified_seconds"]
    assert unclassified > 0  # Notion has no rule yet
    assert add_rule(ws, kind="app", pattern="notion.exe", category="productive").status_code == 201
    after = report(ws, member.employee_id).json()
    assert after["totals"]["unclassified_seconds"] < unclassified
    assert after["totals"]["productive_seconds"] > before["totals"]["productive_seconds"]


def test_a_late_upload_for_a_past_day_is_picked_up(ws: Workspace) -> None:
    member, agent = enrol_member(ws, "Lars Late")
    workday(agent)
    before = report(ws, member.employee_id).json()  # caches the (past) day
    # The agent's offline queue delivers more of that day later.
    late = str(uuid.uuid4())
    response = agent.events(
        event("session.started", at(16), session_id=late),
        segment(at(16), 30, "code.exe", "Visual Studio Code"),
        event(
            "session.stopped", at(16.5), session_id=late, reason="user", active_seconds=1800, idle_seconds=0
        ),
    )
    assert response.status_code == 200 and response.json()["rejected"] == []
    after = report(ws, member.employee_id).json()
    assert after["totals"]["work_seconds"] == before["totals"]["work_seconds"] + 1800
    assert after["totals"]["tracked_seconds"] > before["totals"]["tracked_seconds"]


def test_the_warm_up_job_fills_the_cache(ws: Workspace, client: TestClient, sync_db: Any) -> None:
    _, agent = enrol_member(ws, "Wade Warm")
    workday(agent)
    sync_db["productivity_daily"].delete_many({})
    warmer = client.app.state.background.warmer  # type: ignore[attr-defined]
    processed = client.portal.call(warmer.warm_all)  # type: ignore[attr-defined]
    assert processed >= 1
    assert sync_db["productivity_daily"].find_one({"day": DAY.date().isoformat()}) is not None


def test_alerts_are_persisted_before_delivery_and_none_are_lost(
    ws: Workspace, client: TestClient, sync_db: Any
) -> None:
    """A burst far larger than the old in-memory queue, with the dispatcher down, then back."""
    from bson import ObjectId

    company = ObjectId(ws.get("/companies/current").json()["id"])
    me = ObjectId(ws.admin.user_id)
    dispatcher = client.app.state.notification_dispatcher  # type: ignore[attr-defined]
    notifier = client.app.state.notifier  # type: ignore[attr-defined]
    client.portal.call(dispatcher.stop)  # type: ignore[attr-defined]
    marker = uuid.uuid4().hex
    try:
        for i in range(600):
            notifier.emit(
                AlertEvent(
                    company_id=company,
                    type=NotificationType.TASK_OVERDUE,
                    title=f"{marker} {i}",
                    body="Burst",
                    subject=f"{marker}:{i}",
                    dedupe_key=f"{marker}:{i}",
                    user_ids=[me],
                )
            )
        client.portal.call(notifier.flush)  # type: ignore[attr-defined]
        assert (
            sync_db["notification_outbox"].count_documents({"event.title": {"$regex": f"^{marker}"}}) == 600
        )
    finally:
        client.portal.call(dispatcher.start)  # type: ignore[attr-defined]
    client.portal.call(notifier.drain, 60)  # type: ignore[attr-defined]
    assert sync_db["notification_outbox"].count_documents({"event.title": {"$regex": f"^{marker}"}}) == 0
    assert (
        sync_db["notifications"].count_documents({"title": {"$regex": f"^{marker}"}, "recipient_user_id": me})
        == 600
    )
    # Beyond the burst limit they are stored quietly (not pushed), never dropped.
    assert (
        sync_db["notifications"].count_documents({"title": {"$regex": f"^{marker}"}, "data.quiet": True}) > 0
    )


def test_a_crashed_dispatchers_claim_is_taken_over(ws: Workspace, client: TestClient, sync_db: Any) -> None:
    from datetime import timedelta

    from bson import ObjectId

    from app.utils.time import utcnow

    company = ObjectId(ws.get("/companies/current").json()["id"])
    marker = uuid.uuid4().hex
    # An event claimed by a dispatcher that died ten minutes ago.
    sync_db["notification_outbox"].insert_one(
        {
            "event": AlertEvent(
                company_id=company,
                type=NotificationType.TASK_OVERDUE,
                title=marker,
                body="Orphaned",
                subject=marker,
                user_ids=[ObjectId(ws.admin.user_id)],
            ).to_document(),
            "created_at": utcnow() - timedelta(minutes=10),
            "claim": "dead-dispatcher",
            "claimed_at": utcnow() - timedelta(minutes=10),
            "attempts": 1,
        }
    )
    dispatcher = client.app.state.notification_dispatcher  # type: ignore[attr-defined]
    while client.portal.call(dispatcher.process_batch):  # type: ignore[attr-defined]
        pass
    assert sync_db["notifications"].find_one({"title": marker}) is not None
    assert sync_db["notification_outbox"].find_one({"event.title": marker}) is None


def test_cached_team_views_still_reflect_rule_changes_at_once(ws: Workspace) -> None:
    _, agent = enrol_member(ws, "Tess Team")
    workday(agent)
    first = team_week(ws)
    assert team_week(ws) == first  # served from the short-lived cache
    unclassified = first["totals"]["unclassified_seconds"]
    assert unclassified > 0
    assert add_rule(ws, kind="app", pattern="notion.exe", category="productive").status_code == 201
    after = team_week(ws)  # the rule change invalidated the cached view
    assert after["totals"]["unclassified_seconds"] < unclassified
