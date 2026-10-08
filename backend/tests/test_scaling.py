"""Phase 17: two API processes sharing MongoDB and Redis behave as one.

Two complete application instances (each with its own event loop, connections and in-memory state, exactly like two
production processes) run against the same database and Redis. Realtime events, live-viewing signalling, stopping a
stream from the "wrong" process, a crashed process's sessions, and cluster-wide leases must all work.

Needs Redis: set TEST_REDIS_URL (skipped otherwise).
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient

from app.core.broker import MemoryBroker, RedisBroker
from app.core.config import Settings
from app.main import create_app
from app.websocket.events import EventType, WsEvent
from tests.conftest import CapturingEmailSender
from tests.org_helpers import Workspace, auth
from tests.test_agent_api import enrol_member
from tests.test_live import enable as enable_live
from tests.test_live import working

REDIS = os.environ.get("TEST_REDIS_URL")
pytestmark = pytest.mark.skipif(not REDIS, reason="needs Redis (TEST_REDIS_URL)")


@pytest.fixture
def second_process(
    settings: Settings, email_sender: CapturingEmailSender, client: TestClient
) -> Iterator[TestClient]:
    """Another API process: same database and Redis, separate everything else."""
    assert isinstance(client.app.state.broker, RedisBroker), "the main test app must use Redis too"  # type: ignore[attr-defined]
    app = create_app(settings)
    app.state.email_sender = email_sender
    with TestClient(app) as other:
        yield other


def wait_for(predicate: Any, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError("condition not met in time")


def test_processes_have_their_own_identity(client: TestClient, second_process: TestClient) -> None:
    a = client.app.state.broker.node_id  # type: ignore[attr-defined]
    b = second_process.app.state.broker.node_id  # type: ignore[attr-defined]
    assert a != b


def test_realtime_events_reach_sockets_on_any_process(
    ws: Workspace, client: TestClient, second_process: TestClient
) -> None:
    member = ws.member("Rosa Remote")
    company = ObjectId(ws.get("/companies/current").json()["id"])
    # The member's browser is connected to process B; the event is raised on process A.
    with second_process.websocket_connect(f"/api/ws?token={member.token}") as sock:
        assert sock.receive_json()["type"] == "connection.ready"
        manager_a = client.app.state.ws_manager  # type: ignore[attr-defined]
        event = WsEvent(type=EventType.PONG, payload={"marker": "cross-process"})
        wait_for(
            lambda: client.portal.call(manager_a.send_to_user, company, ObjectId(member.user_id), event) >= 1
        )  # type: ignore[attr-defined]
        message = sock.receive_json()
        assert message["payload"]["marker"] == "cross-process"


def test_notifications_raised_on_one_process_are_pushed_from_another(
    ws: Workspace, client: TestClient, second_process: TestClient
) -> None:
    """A live view started through process A notifies the person, whose browser is connected to process B."""
    enable_live(ws)
    member, agent = enrol_member(ws, "Nell Notified")
    working(agent)
    with (
        second_process.websocket_connect(f"/api/ws?token={member.token}") as person,
        client.websocket_connect("/api/agent/live", headers=auth(agent.token)) as agent_sock,
    ):
        assert person.receive_json()["type"] == "connection.ready"
        assert agent_sock.receive_json()["type"] == "hello"
        session = ws.post("/live/sessions", {"employee_id": member.employee_id}).json()
        with client.websocket_connect(
            f"/api/live/sessions/{session['id']}/ws?token={ws.admin.token}"
        ) as viewer:
            assert viewer.receive_json()["type"] == "ready"
            viewer.send_json({"type": "state", "state": "connected"})
            seen = person.receive_json()
            while seen["type"] != "notification.created":
                seen = person.receive_json()
            assert "viewing" in seen["payload"]["notification"]["title"]
            viewer.send_json({"type": "stop"})


def test_live_signalling_spans_processes(
    ws: Workspace, client: TestClient, second_process: TestClient, sync_db: Any
) -> None:
    """Agent on B, session created and owned by A, viewer on B, stopped through B."""
    enable_live(ws)
    member, agent = enrol_member(ws, "Pip Distributed")
    working(agent)
    with second_process.websocket_connect("/api/agent/live", headers=auth(agent.token)) as agent_sock:
        assert agent_sock.receive_json()["type"] == "hello"
        # Process A sees the agent connected to B (shared registry), so discovery and creation work there.
        listing = {e["employee"]["id"]: e for e in ws.get("/live/employees").json()["employees"]}
        assert listing[member.employee_id]["online"] is True
        created = client.post(
            "/api/live/sessions", json={"employee_id": member.employee_id}, headers=auth(ws.admin.token)
        )
        assert created.status_code == 201, created.text
        session_id = created.json()["id"]
        assert client.app.state.live_hub.runtime(ObjectId(session_id)) is not None  # type: ignore[attr-defined]

        with second_process.websocket_connect(
            f"/api/live/sessions/{session_id}/ws?token={ws.admin.token}"
        ) as viewer:
            ready = viewer.receive_json()
            assert ready["type"] == "ready" and ready["agent_online"] is True
            viewer.send_json({"type": "offer", "sdp": "v=0 offer"})
            offer = agent_sock.receive_json()
            assert (
                offer["type"] == "offer" and offer["sdp"] == "v=0 offer" and offer["session_id"] == session_id
            )
            agent_sock.send_json({"type": "answer", "session_id": session_id, "sdp": "v=0 answer"})
            assert viewer.receive_json() == {"type": "answer", "sdp": "v=0 answer"}
            viewer.send_json({"type": "state", "state": "connected"})
            wait_for(
                lambda: sync_db["live_sessions"].find_one({"_id": ObjectId(session_id)})["status"] == "live"
            )

            # Stopping through process B (not the owner) ends it on A, and both sockets hear about it.
            stopped = second_process.post(
                f"/api/live/sessions/{session_id}/stop", headers=auth(ws.admin.token)
            )
            assert stopped.status_code == 200 and stopped.json()["status"] == "ended"
            assert viewer.receive_json()["type"] == "ended"
            stop = agent_sock.receive_json()
            assert stop["type"] == "stop" and stop["reason"] == "viewer_stopped"
    doc = sync_db["live_sessions"].find_one({"_id": ObjectId(session_id)})
    assert doc["end_reason"] == "viewer_stopped" and doc["connected_at"] is not None


def test_sessions_of_a_crashed_process_are_ended(
    ws: Workspace, client: TestClient, second_process: TestClient, sync_db: Any
) -> None:
    enable_live(ws)
    member, agent = enrol_member(ws, "Cass Crash")
    working(agent)
    with second_process.websocket_connect("/api/agent/live", headers=auth(agent.token)) as agent_sock:
        agent_sock.receive_json()
        session_id = ws.post("/live/sessions", {"employee_id": member.employee_id}).json()["id"]
        hub_a = client.app.state.live_hub  # type: ignore[attr-defined]
        # Simulate process A dying: its in-memory state vanishes and its registry entry expires.
        rt = hub_a._sessions.pop(ObjectId(session_id))
        for task in rt.timers.values():
            task.cancel()
        client.portal.call(client.app.state.broker.delete, f"live:owner:{session_id}")  # type: ignore[attr-defined]

        hub_b = second_process.app.state.live_hub  # type: ignore[attr-defined]
        assert second_process.portal.call(hub_b.sweep_orphans) >= 1  # type: ignore[attr-defined]
        stop = agent_sock.receive_json()
        assert stop["type"] == "stop" and stop["reason"] == "server_restart"
    doc = sync_db["live_sessions"].find_one({"_id": ObjectId(session_id)})
    assert doc["status"] == "ended" and doc["end_reason"] == "server_restart"


def test_a_restarting_process_hands_live_sessions_over(
    ws: Workspace, client: TestClient, second_process: TestClient, sync_db: Any
) -> None:
    """A deploy restarts the owner (A) mid-view: the viewer reconnects to B, which adopts the session; it goes on."""
    enable_live(ws)
    member, agent = enrol_member(ws, "Hana Handover")
    working(agent)
    hub_a = client.app.state.live_hub  # type: ignore[attr-defined]
    hub_b = second_process.app.state.live_hub  # type: ignore[attr-defined]
    with second_process.websocket_connect("/api/agent/live", headers=auth(agent.token)) as agent_sock:
        agent_sock.receive_json()
        session_id = ws.post("/live/sessions", {"employee_id": member.employee_id}).json()["id"]
        sid = ObjectId(session_id)
        assert hub_a.runtime(sid) is not None
        with second_process.websocket_connect(
            f"/api/live/sessions/{session_id}/ws?token={ws.admin.token}"
        ) as v:
            v.receive_json()
            v.send_json({"type": "offer", "sdp": "v=0 offer"})
            agent_sock.receive_json()
            agent_sock.send_json({"type": "answer", "session_id": session_id, "sdp": "v=0 answer"})
            v.receive_json()
            v.send_json({"type": "state", "state": "connected"})
            wait_for(lambda: sync_db["live_sessions"].find_one({"_id": sid})["status"] == "live")
            connected_at = sync_db["live_sessions"].find_one({"_id": sid})["connected_at"]

            # A shuts down cleanly (what a deploy does): the session is handed over, not ended.
            client.portal.call(hub_a._release, sid)  # type: ignore[attr-defined]
            doc = sync_db["live_sessions"].find_one({"_id": sid})
            assert doc["status"] == "interrupted" and doc["handover_at"] is not None
            # The sweeper leaves it alone during the grace period.
            second_process.portal.call(hub_b.sweep_orphans)  # type: ignore[attr-defined]
            assert sync_db["live_sessions"].find_one({"_id": sid})["status"] == "interrupted"

        # The viewer's socket reconnects (to B), which adopts the session and renegotiates.
        with second_process.websocket_connect(
            f"/api/live/sessions/{session_id}/ws?token={ws.admin.token}"
        ) as v:
            ready = v.receive_json()
            assert (
                ready["type"] == "ready"
                and ready["status"] == "interrupted"
                and ready["agent_online"] is True
            )
            assert hub_b.runtime(sid) is not None
            v.send_json({"type": "offer", "sdp": "v=0 again"})
            offer = agent_sock.receive_json()
            assert offer["type"] == "offer" and offer["sdp"] == "v=0 again"
            agent_sock.send_json({"type": "answer", "session_id": session_id, "sdp": "v=0 answer 2"})
            assert v.receive_json() == {"type": "answer", "sdp": "v=0 answer 2"}
            v.send_json({"type": "state", "state": "connected"})
            wait_for(lambda: sync_db["live_sessions"].find_one({"_id": sid})["status"] == "live")
            doc = sync_db["live_sessions"].find_one({"_id": sid})
            assert doc["handover_at"] is None and doc["connected_at"] == connected_at  # the same session
            stopped = second_process.post(
                f"/api/live/sessions/{session_id}/stop", headers=auth(ws.admin.token)
            )
            assert stopped.json()["status"] == "ended"
    assert sync_db["live_sessions"].find_one({"_id": sid})["end_reason"] == "viewer_stopped"


def test_a_handed_over_session_nobody_returns_to_ends_after_the_grace_period(
    ws: Workspace, client: TestClient, second_process: TestClient, sync_db: Any
) -> None:
    enable_live(ws)
    member, agent = enrol_member(ws, "Gus Gone")
    working(agent)
    with second_process.websocket_connect("/api/agent/live", headers=auth(agent.token)) as agent_sock:
        agent_sock.receive_json()
        session_id = ws.post("/live/sessions", {"employee_id": member.employee_id}).json()["id"]
        sid = ObjectId(session_id)
        client.portal.call(client.app.state.live_hub._release, sid)  # type: ignore[attr-defined]
        # Nobody came back: once the grace period is over, the sweeper ends it.
        sync_db["live_sessions"].update_one(
            {"_id": sid}, {"$set": {"handover_at": datetime.now(UTC) - timedelta(minutes=10)}}
        )
        hub_b = second_process.app.state.live_hub  # type: ignore[attr-defined]
        assert second_process.portal.call(hub_b.sweep_orphans) >= 1  # type: ignore[attr-defined]
        stop = agent_sock.receive_json()
        assert stop["type"] == "stop" and stop["reason"] == "server_restart"
    assert sync_db["live_sessions"].find_one({"_id": sid})["end_reason"] == "server_restart"


def test_an_agent_reconnecting_to_another_process_replaces_its_old_socket(
    ws: Workspace, client: TestClient, second_process: TestClient
) -> None:
    _, agent = enrol_member(ws, "Ray Roaming")
    with client.websocket_connect("/api/agent/live", headers=auth(agent.token)) as old:
        assert old.receive_json()["type"] == "hello"
        with second_process.websocket_connect("/api/agent/live", headers=auth(agent.token)) as new:
            assert new.receive_json()["type"] == "hello"
            from starlette.websockets import WebSocketDisconnect

            with pytest.raises(WebSocketDisconnect) as closed:
                for _ in range(20):
                    old.receive_json()
            assert closed.value.code == 4000


def test_leases_and_counters_are_cluster_wide() -> None:
    async def scenario() -> tuple[list[bool], list[int]]:
        a, b = RedisBroker(REDIS or ""), RedisBroker(REDIS or "")
        await a.start()
        await b.start()
        name = f"test-lease-{uuid.uuid4().hex}"
        try:
            leases = [await a.lease(name, 5), await b.lease(name, 5), await a.lease(name, 5)]
            key = f"test-hit-{uuid.uuid4().hex}"
            hits = [await a.hit(key, 60), await b.hit(key, 60), await a.hit(key, 60)]
            return leases, hits
        finally:
            await a.stop()
            await b.stop()

    leases, hits = asyncio.run(scenario())
    assert leases == [True, False, True]  # one holder at a time; the holder renews
    assert hits == [1, 2, 3]


def test_memory_broker_matches_the_interface() -> None:
    async def scenario() -> list[Any]:
        broker = MemoryBroker()
        got: list[Any] = []

        async def handler(message: dict[str, Any]) -> None:
            got.append(message["n"])

        await broker.subscribe("c", handler)
        for n in range(3):
            await broker.publish("c", {"n": n})
        await asyncio.sleep(0.05)
        await broker.set("k", "v", ttl=0.05, only_if_absent=True)
        first = await broker.set("k", "w", only_if_absent=True)
        await asyncio.sleep(0.08)
        return [got, first, await broker.get("k"), await broker.lease("x", 5), await broker.hit("h", 60)]

    got, first, expired, lease, hit = asyncio.run(scenario())
    assert got == [0, 1, 2] and first is False and expired is None and lease is True and hit == 1
