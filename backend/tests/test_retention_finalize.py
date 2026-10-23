"""Prod build #4: finalise-first retention — durable daily summaries, then raw-segment purging.

A settled day is finalised into the permanent ``daily_summaries`` collection before its raw ``activity_segments``
are purged, so focus/switching history and long-horizon reports survive even though raw data is short-lived.
Rollups (``activity_daily``) and work sessions are kept. Today is never finalised, and days inside the raw
retention window keep their raw segments.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from bson import ObjectId
from fastapi.testclient import TestClient

from tests.org_helpers import Workspace
from tests.test_agent_api import AgentClient, enrol_member, event
from tests.test_productivity_api import DAY, add_rule, segment, workday

OLD_BASE = (datetime.now(UTC) - timedelta(days=4)).replace(hour=0, minute=0, second=0, microsecond=0)


def old_at(hour: float) -> datetime:
    return OLD_BASE + timedelta(hours=hour)


def old_workday(agent: AgentClient) -> None:
    """Two hours of coding on a day four days ago (older than the 72-hour raw retention window)."""
    session_id = str(uuid.uuid4())
    response = agent.events(
        event("session.started", old_at(9), session_id=session_id),
        segment(old_at(9), 60, "code.exe", "Visual Studio Code"),
        segment(old_at(10), 60, "code.exe", "Visual Studio Code"),
        event("session.stopped", old_at(11), session_id=session_id, reason="user", active_seconds=7200, idle_seconds=0),
    )
    assert response.status_code == 200 and response.json()["rejected"] == [], response.text


def _segments_on(sync_db: Any, employee_id: str, base: datetime) -> int:
    return sync_db["activity_segments"].count_documents(
        {"employee_id": ObjectId(employee_id), "started_at": {"$gte": base, "$lt": base + timedelta(days=1)}}
    )


def test_days_are_finalised_durably_before_their_raw_segments_are_purged(
    ws: Workspace, client: TestClient, sync_db: Any
) -> None:
    member, agent = enrol_member(ws, "Fin Alise")
    assert add_rule(ws, kind="app", pattern="code.exe", category="productive").status_code == 201
    old_workday(agent)  # four days ago -> outside the 72h window
    workday(agent)  # yesterday -> settled but still inside the 72h window

    finalizer = client.app.state.background.finalizer  # type: ignore[attr-defined]
    written, purged = client.portal.call(finalizer.sweep)  # type: ignore[attr-defined]
    assert written >= 2 and purged > 0  # both settled days finalised; only the old day's raw purged

    old_iso = OLD_BASE.date().isoformat()
    summary = sync_db["daily_summaries"].find_one(
        {"employee_id": ObjectId(member.employee_id), "day": old_iso}
    )
    assert summary is not None, "the old day must be finalised durably"
    assert summary["metrics"]["work_seconds"] == 7200 and summary["metrics"]["productive_seconds"] == 7200
    assert summary["engine_version"] >= 1 and summary.get("finalized_at") is not None

    # Finalise-first: the old day's raw segments are gone, but its rollup (and the summary) remain.
    assert _segments_on(sync_db, member.employee_id, OLD_BASE) == 0
    assert (
        sync_db["activity_daily"].count_documents({"employee_id": ObjectId(member.employee_id), "day": old_iso})
        >= 1
    )
    # Yesterday is finalised too, but inside the 72h window, so its raw segments are kept.
    assert sync_db["daily_summaries"].find_one(
        {"employee_id": ObjectId(member.employee_id), "day": DAY.date().isoformat()}
    ) is not None
    assert _segments_on(sync_db, member.employee_id, DAY) > 0

    # Today is never finalised (it is still changing).
    today_iso = datetime.now(UTC).date().isoformat()
    assert sync_db["daily_summaries"].find_one({"day": today_iso}) is None


def test_the_durable_summary_survives_purging_for_long_range_trends(
    ws: Workspace, client: TestClient, sync_db: Any
) -> None:
    member, agent = enrol_member(ws, "Trendy Tom")
    assert add_rule(ws, kind="app", pattern="code.exe", category="productive").status_code == 201
    old_workday(agent)

    finalizer = client.app.state.background.finalizer  # type: ignore[attr-defined]
    client.portal.call(finalizer.sweep)  # type: ignore[attr-defined]
    assert _segments_on(sync_db, member.employee_id, OLD_BASE) == 0  # raw gone

    # The monthly trend still reflects the old day's work, read from the durable summary (not raw data).
    monthly = ws.get("/productivity/trend", period="monthly", employee_id=member.employee_id).json()
    assert sum(p["work_seconds"] for p in monthly["points"]) >= 7200
    assert sum(p["productive_seconds"] for p in monthly["points"]) >= 7200
