"""Phase 7: live screen viewing — policy, discovery, authorisation, signalling relay, reconnection, timeouts, audit."""

from __future__ import annotations

import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from bson import ObjectId
from fastapi.testclient import TestClient
from pydantic import SecretStr
from starlette.websockets import WebSocketDisconnect

from app.services.live_hub import LiveHub, ice_servers
from tests.conftest import register
from tests.org_helpers import Workspace, auth
from tests.test_agent_api import AgentClient, enrol_member

OFFER = "v=0\r\no=- 1 2 IN IP4 127.0.0.1\r\ns=-\r\nt=0 0\r\nm=video 9 UDP/TLS/RTP/SAVPF 96\r\n"
ANSWER = OFFER.replace("o=- 1", "o=- 9")
CANDIDATE = {
    "candidate": "candidate:1 1 udp 2122260223 192.168.1.20 50000 typ host",
    "sdpMid": "0",
    "sdpMLineIndex": 0,
}


def enable(ws: Workspace, **fields: Any) -> None:
    response = ws.patch("/companies/current/live-policy", {"enabled": True, **fields})
    assert response.status_code == 200, response.text


def working(agent: AgentClient) -> None:
    assert agent.heartbeat(presence="active", session_id=str(uuid.uuid4())).status_code == 200


@contextmanager
def agent_socket(client: TestClient, agent: AgentClient) -> Iterator[Any]:
    with client.websocket_connect("/api/agent/live", headers=auth(agent.token)) as sock:
        assert sock.receive_json()["type"] == "hello"
        yield sock


@contextmanager
def viewer_socket(client: TestClient, session_id: str, token: str) -> Iterator[Any]:
    with client.websocket_connect(f"/api/live/sessions/{session_id}/ws?token={token}") as sock:
        ready = sock.receive_json()
        assert ready["type"] == "ready", ready
        sock.ready = ready  # type: ignore[attr-defined]
        yield sock


def start(ws: Workspace, employee_id: str, token: str | None = None) -> Any:
    return ws.post("/live/sessions", {"employee_id": employee_id}, token=token)


def hub(client: TestClient) -> LiveHub:
    return client.app.state.live_hub  # type: ignore[attr-defined,no-any-return]


def wait_for(predicate: Any, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.05)
    raise AssertionError("condition not met in time")


def session_doc(sync_db: Any, session_id: str) -> dict[str, Any]:
    return sync_db["live_sessions"].find_one({"_id": ObjectId(session_id)})  # type: ignore[no-any-return]


@contextmanager
def fast_timers(client: TestClient, **values: int) -> Iterator[None]:
    h = hub(client)
    original = h._settings
    h._settings = original.model_copy(update=values)
    try:
        yield
    finally:
        h._settings = original


# --------------------------------------------------------------------------- policy and discovery


def test_policy_is_off_by_default_and_requests_are_denied_and_audited(ws: Workspace, sync_db: Any) -> None:
    member, agent = enrol_member(ws, "Lia Live")
    policy = ws.get("/companies/current/live-policy", token=member.token).json()
    assert policy == {"enabled": False, "max_session_minutes": 30}
    assert (
        ws.patch("/companies/current/live-policy", {"enabled": True}, token=member.token).status_code == 403
    )
    assert agent.heartbeat().json()["policy"]["live"]["enabled"] is False

    denied = start(ws, member.employee_id)
    assert denied.status_code == 403 and denied.json()["error"]["code"] == "live_view_disabled"
    entry = sync_db["audit_logs"].find_one(
        {"action": "live.session_denied", "subject_employee_id": ObjectId(member.employee_id)}
    )
    assert entry is not None and entry["metadata"]["reason"] == "disabled"
    assert ws.patch("/companies/current/live-policy", {"max_session_minutes": 0}).status_code == 422


def test_discovery_reflects_agent_connection_and_work_sessions(ws: Workspace, client: TestClient) -> None:
    enable(ws)
    member, agent = enrol_member(ws, "Dee Discover")

    def row() -> dict[str, Any]:
        rows = ws.get("/live/employees").json()["employees"]
        return next(r for r in rows if r["employee"]["id"] == member.employee_id)

    assert row()["availability"] == "offline" and row()["online"] is False
    with agent_socket(client, agent):
        assert row()["availability"] == "not_working"
        working(agent)
        current = row()
        assert current["availability"] == "available" and current["presence"] == "active"
        assert current["device"]["name"] == "Test laptop"
    assert row()["availability"] == "offline"

    assert ws.get("/live/employees", token=member.token).status_code == 403  # employees can't browse


# --------------------------------------------------------------------------- authorisation


def test_only_authorised_viewers_in_scope(ws: Workspace, client: TestClient) -> None:
    enable(ws)
    manager = ws.member("Mo Manager", role="MANAGER")
    report, report_agent = enrol_member(ws, "Ray Report", manager_employee_id=manager.employee_id)
    outsider, outsider_agent = enrol_member(ws, "Oz Outside")
    working(report_agent)
    working(outsider_agent)

    with agent_socket(client, report_agent), agent_socket(client, outsider_agent):
        assert start(ws, outsider.employee_id, token=report.token).status_code == 403  # no permission
        assert start(ws, outsider.employee_id, token=manager.token).status_code == 404  # out of scope
        visible = {
            r["employee"]["id"] for r in ws.get("/live/employees", token=manager.token).json()["employees"]
        }
        assert report.employee_id in visible and outsider.employee_id not in visible

        rival = str(register(client, company_name="Rival Live")["access_token"])
        assert start(ws, report.employee_id, token=rival).status_code == 404

        session = start(ws, report.employee_id, token=manager.token)
        assert session.status_code == 201, session.text
        sid = session.json()["id"]
        # Someone else can't take over the stream's signalling channel.
        try:
            with client.websocket_connect(f"/api/live/sessions/{sid}/ws?token={ws.admin.token}") as sock:
                sock.receive_json()
            raise AssertionError("expected the socket to be refused")
        except WebSocketDisconnect as exc:
            assert exc.code == 4404
        busy = start(ws, report.employee_id)
        assert busy.status_code == 409 and busy.json()["error"]["code"] == "already_live"
        # The same viewer asking again rejoins their own session.
        assert start(ws, report.employee_id, token=manager.token).json()["id"] == sid
        assert (
            ws.client.post(f"/api/live/sessions/{sid}/stop", headers=auth(manager.token)).json()["status"]
            == "ended"
        )


def test_offline_and_not_working_are_refused(ws: Workspace, client: TestClient) -> None:
    enable(ws)
    member, agent = enrol_member(ws, "Nell Nowork")
    offline = start(ws, member.employee_id)
    assert offline.status_code == 409 and offline.json()["error"]["code"] == "agent_offline"
    with agent_socket(client, agent):
        idle = start(ws, member.employee_id)
        assert idle.status_code == 409 and idle.json()["error"]["code"] == "not_working"


def test_agent_socket_requires_a_device_token(ws: Workspace, client: TestClient) -> None:
    for headers in ({}, auth(ws.admin.token), auth("garbage")):
        try:
            with client.websocket_connect("/api/agent/live", headers=headers) as sock:
                sock.receive_json()
            raise AssertionError("expected refusal")
        except WebSocketDisconnect as exc:
            assert exc.code == 4401


def test_discovery_includes_department_and_team_for_filters(ws: Workspace, client: TestClient) -> None:
    enable(ws)
    dept = ws.post("/departments", {"name": "Support"}).json()
    team = ws.post("/teams", {"name": "Tier 1", "department_id": dept["id"]}).json()
    member, _agent = enrol_member(ws, "Fil Ter", department_id=dept["id"], team_id=team["id"])
    row = next(
        r for r in ws.get("/live/employees").json()["employees"] if r["employee"]["id"] == member.employee_id
    )
    assert row["department"] == {"id": dept["id"], "name": "Support"}
    assert row["team"] == {"id": team["id"], "name": "Tier 1"}


def test_session_log_is_scoped_and_complete(ws: Workspace, client: TestClient) -> None:
    enable(ws)
    manager = ws.member("Lou Logger", role="MANAGER")
    report, report_agent = enrol_member(ws, "Rae Report", manager_employee_id=manager.employee_id)
    outsider, outsider_agent = enrol_member(ws, "Ola Outside")
    working(report_agent)
    working(outsider_agent)
    with agent_socket(client, report_agent), agent_socket(client, outsider_agent):
        mine = start(ws, report.employee_id, token=manager.token).json()
        ws.client.post(f"/api/live/sessions/{mine['id']}/stop", headers=auth(manager.token))
        other = start(ws, outsider.employee_id).json()
        ws.client.post(f"/api/live/sessions/{other['id']}/stop", headers=auth(ws.admin.token))

    everything = ws.get("/live/sessions").json()["items"]
    assert [s["id"] for s in everything][:2] == [other["id"], mine["id"]]  # newest first
    entry = everything[1]
    assert entry["employee"]["id"] == report.employee_id and entry["viewer_name"] == "Lou Logger"
    assert entry["device"]["name"] == "Test laptop" and entry["created_at"] and entry["ended_at"]
    assert entry["end_reason"] == "viewer_stopped"

    scoped = ws.get("/live/sessions", token=manager.token).json()["items"]
    assert [s["id"] for s in scoped] == [mine["id"]]  # nothing about people outside the reporting line
    assert ws.get("/live/sessions", token=manager.token, employee_id=outsider.employee_id).status_code == 404
    one = ws.get("/live/sessions", employee_id=report.employee_id).json()["items"]
    assert [s["id"] for s in one] == [mine["id"]]
    assert ws.get("/live/sessions", token=report.token).status_code == 403


def test_media_route_is_pluggable(ws: Workspace, client: TestClient) -> None:
    """An SFU would plug in here: the hub hands the viewer's negotiation to the session's media route."""

    class Recorder:
        name = "test-route"

        def __init__(self) -> None:
            self.offers: list[str] = []
            self.candidates: list[Any] = []

        async def viewer_offer(self, hub: Any, rt: Any, sdp: str) -> bool:
            self.offers.append(sdp)
            return True

        async def viewer_candidate(self, hub: Any, rt: Any, candidate: Any) -> None:
            self.candidates.append(candidate)

    enable(ws)
    member, agent = enrol_member(ws, "Ro Ute")
    working(agent)
    h = hub(client)
    original, recorder = h.route, Recorder()
    h.route = recorder
    try:
        with agent_socket(client, agent):
            created = start(ws, member.employee_id).json()
            assert created["media_route"] == "test-route"
            with viewer_socket(client, created["id"], ws.admin.token) as viewer:
                assert viewer.ready["media_route"] == "test-route"
                viewer.send_json({"type": "offer", "sdp": OFFER})
                viewer.send_json({"type": "candidate", "candidate": CANDIDATE})
                viewer.send_json({"type": "ping"})
                assert viewer.receive_json() == {"type": "pong"}
                # Pings are answered by the viewer's own process; negotiation travels via the broker to the
                # session's owner, so it is not ordered behind the pong.
                wait_for(lambda: recorder.offers == [OFFER] and recorder.candidates == [CANDIDATE])
                viewer.send_json({"type": "stop"})
                assert viewer.receive_json()["type"] == "ended"
    finally:
        h.route = original


# --------------------------------------------------------------------------- signalling


def test_full_signalling_flow_and_audit(ws: Workspace, client: TestClient, sync_db: Any) -> None:
    enable(ws, max_session_minutes=15)
    member, agent = enrol_member(ws, "Sig Nal")
    working(agent)
    with agent_socket(client, agent) as agent_ws:
        created = start(ws, member.employee_id).json()
        assert created["status"] == "requested" and created["viewer_name"]
        sid = created["id"]
        with viewer_socket(client, sid, ws.admin.token) as viewer:
            assert viewer.ready["agent_online"] is True and viewer.ready["ice_servers"] == []
            assert viewer.ready["media_route"] == "p2p" and created["media_route"] == "p2p"

            viewer.send_json({"type": "offer", "sdp": OFFER})
            offer = agent_ws.receive_json()
            assert offer["type"] == "offer" and offer["session_id"] == sid and offer["sdp"] == OFFER
            assert offer["viewer_name"] == created["viewer_name"]

            viewer.send_json({"type": "candidate", "candidate": CANDIDATE})
            assert agent_ws.receive_json() == {"type": "candidate", "session_id": sid, "candidate": CANDIDATE}

            agent_ws.send_json({"type": "answer", "session_id": sid, "sdp": ANSWER})
            assert viewer.receive_json() == {"type": "answer", "sdp": ANSWER}
            agent_ws.send_json(
                {"type": "candidate", "session_id": sid, "candidate": None}
            )  # end of candidates
            assert viewer.receive_json() == {"type": "candidate", "candidate": None}

            viewer.send_json({"type": "state", "state": "connected"})
            wait_for(lambda: session_doc(sync_db, sid)["status"] == "live")
            assert ws.get(f"/live/sessions/{sid}").json()["connected_at"] is not None
            assert (
                ws.get("/me/monitoring", token=member.token).json()["live_viewer"] == created["viewer_name"]
            )

            # Malformed or unexpected messages are rejected without dropping the session.
            viewer.send_text("not json")
            assert viewer.receive_json() == {"type": "error", "code": "invalid_message"}
            viewer.send_json({"type": "offer", "sdp": OFFER, "extra": 1})
            assert viewer.receive_json()["code"] == "invalid_message"
            viewer.send_json({"type": "ping"})
            assert viewer.receive_json() == {"type": "pong"}

            time.sleep(1.1)
            viewer.send_json({"type": "stop"})
            assert viewer.receive_json()["type"] == "ended"
            assert agent_ws.receive_json() == {"type": "stop", "session_id": sid, "reason": "viewer_stopped"}

    doc = session_doc(sync_db, sid)
    assert doc["status"] == "ended" and doc["end_reason"] == "viewer_stopped" and doc["duration_seconds"] >= 1
    actions = [e["action"] for e in sync_db["audit_logs"].find({"target_id": sid}).sort("created_at", 1)]
    assert actions == ["live.session_requested", "live.session_connected", "live.session_ended"]
    ended = sync_db["audit_logs"].find_one({"target_id": sid, "action": "live.session_ended"})
    assert ended["metadata"]["reason"] == "viewer_stopped" and ended["subject_employee_id"] == ObjectId(
        member.employee_id
    )
    # The audit trail alone answers: who watched whom, on which device, from when to when, which session.
    assert ended["actor_user_id"] == ObjectId(ws.admin.user_id)
    assert ended["metadata"]["device_id"] == str(doc["device_id"])
    assert ended["metadata"]["started_at"] and ended["metadata"]["ended_at"]
    assert ended["metadata"]["media_route"] == "p2p"


def test_agent_can_end_a_stream_and_policy_off_ends_all(
    ws: Workspace, client: TestClient, sync_db: Any
) -> None:
    enable(ws)
    member, agent = enrol_member(ws, "Ada Agentend")
    working(agent)
    with agent_socket(client, agent) as agent_ws:
        sid = start(ws, member.employee_id).json()["id"]
        with viewer_socket(client, sid, ws.admin.token) as viewer:
            agent_ws.send_json({"type": "ended", "session_id": sid, "reason": "work_session_stopped"})
            assert viewer.receive_json()["reason"] == "work_session_stopped"
        assert agent_ws.receive_json()["type"] == "stop"

        sid2 = start(ws, member.employee_id).json()["id"]
        with viewer_socket(client, sid2, ws.admin.token) as viewer:
            ws.patch("/companies/current/live-policy", {"enabled": False})
            assert viewer.receive_json()["reason"] == "live_view_disabled"
    assert session_doc(sync_db, sid2)["end_reason"] == "live_view_disabled"


# --------------------------------------------------------------------------- reconnection and timeouts


def test_viewer_reconnects_within_grace_otherwise_session_ends(
    ws: Workspace, client: TestClient, sync_db: Any
) -> None:
    enable(ws)
    member, agent = enrol_member(ws, "Rhea Reconnect")
    working(agent)
    with fast_timers(client, live_reconnect_grace_seconds=1), agent_socket(client, agent) as agent_ws:
        sid = start(ws, member.employee_id).json()["id"]
        with viewer_socket(client, sid, ws.admin.token) as viewer:
            viewer.send_json({"type": "state", "state": "connected"})
            wait_for(lambda: session_doc(sync_db, sid)["status"] == "live")
        assert agent_ws.receive_json() == {"type": "pause", "session_id": sid}
        wait_for(lambda: session_doc(sync_db, sid)["status"] == "interrupted")

        with viewer_socket(client, sid, ws.admin.token) as viewer:  # back within the grace period
            assert viewer.ready["status"] == "interrupted"
            viewer.send_json({"type": "offer", "sdp": OFFER})  # renegotiate
            assert agent_ws.receive_json()["type"] == "offer"
            viewer.send_json({"type": "state", "state": "connected"})
            wait_for(lambda: session_doc(sync_db, sid)["status"] == "live")
        assert agent_ws.receive_json()["type"] == "pause"
        assert agent_ws.receive_json() == {"type": "stop", "session_id": sid, "reason": "viewer_disconnected"}
    doc = session_doc(sync_db, sid)
    assert doc["end_reason"] == "viewer_disconnected" and doc["reconnects"] == 1


def test_agent_reconnection_and_connect_timeout(ws: Workspace, client: TestClient, sync_db: Any) -> None:
    enable(ws)
    member, agent = enrol_member(ws, "Aria Again")
    working(agent)
    with fast_timers(client, live_reconnect_grace_seconds=5, live_connect_timeout_seconds=30):
        with agent_socket(client, agent):
            sid = start(ws, member.employee_id).json()["id"]
            with viewer_socket(client, sid, ws.admin.token) as viewer:
                viewer.send_json({"type": "state", "state": "connected"})
                wait_for(lambda: session_doc(sync_db, sid)["status"] == "live")
        # Both sides dropped: the session is interrupted, and both come back within the grace period.
        wait_for(lambda: session_doc(sync_db, sid)["status"] == "interrupted")
        with agent_socket(client, agent), viewer_socket(client, sid, ws.admin.token) as viewer:
            assert viewer.ready["agent_online"] is True
            viewer.send_json({"type": "stop"})
            assert viewer.receive_json()["type"] == "ended"

    with fast_timers(client, live_connect_timeout_seconds=1), agent_socket(client, agent):
        sid = start(ws, member.employee_id).json()["id"]
        wait_for(lambda: session_doc(sync_db, sid)["status"] == "ended", timeout=5)
        assert session_doc(sync_db, sid)["end_reason"] == "connect_timeout"


def test_viewer_is_told_when_the_agent_drops_and_returns(ws: Workspace, client: TestClient) -> None:
    enable(ws)
    member, agent = enrol_member(ws, "Pip Peer")
    working(agent)
    with fast_timers(client, live_reconnect_grace_seconds=10):
        first = client.websocket_connect("/api/agent/live", headers=auth(agent.token))
        agent_ws = first.__enter__()
        assert agent_ws.receive_json()["type"] == "hello"
        sid = start(ws, member.employee_id).json()["id"]
        with viewer_socket(client, sid, ws.admin.token) as viewer:
            first.__exit__(None, None, None)
            assert viewer.receive_json() == {"type": "peer_left"}
            with agent_socket(client, agent):
                assert viewer.receive_json() == {"type": "peer_ready"}
                viewer.send_json({"type": "stop"})
                assert viewer.receive_json()["type"] == "ended"


# --------------------------------------------------------------------------- ICE servers


def test_ice_servers_mint_short_lived_turn_credentials(settings: Any) -> None:
    assert ice_servers(settings, "u1") == []
    configured = settings.model_copy(
        update={
            "live_stun_urls": "stun:stun.example.com:3478",
            "live_turn_urls": "turn:turn.example.com:3478?transport=udp, turns:turn.example.com:5349",
            "live_turn_secret": SecretStr("turn-shared-secret"),
        }
    )
    stun, turn = ice_servers(configured, "user-42")
    assert stun.urls == ["stun:stun.example.com:3478"] and stun.username is None
    assert len(turn.urls) == 2 and turn.username and turn.username.endswith(":user-42")
    assert int(turn.username.split(":")[0]) > time.time() and turn.credential


def test_tokens_in_websocket_urls_are_redacted_from_logs() -> None:
    import logging

    from app.core.logging import SecretRedactionFilter

    record = logging.LogRecord(
        "uvicorn.error",
        logging.INFO,
        "",
        0,
        '%s - "WebSocket %s" [accepted]',
        ("1.2.3.4:0", "/api/live/sessions/x/ws?token=eyJabc.def&v=1"),
        None,
    )
    SecretRedactionFilter().filter(record)
    assert (
        record.getMessage()
        == '1.2.3.4:0 - "WebSocket /api/live/sessions/x/ws?token=[redacted]&v=1" [accepted]'
    )


def test_dev_console_mailer_keeps_its_links() -> None:
    import logging

    from app.core.logging import SecretRedactionFilter

    email = logging.LogRecord(
        "app.services.email_service", logging.INFO, "", 0, "link: /verify-email?token=abc", (), None
    )
    SecretRedactionFilter().filter(email)
    assert email.getMessage().endswith("token=abc")
