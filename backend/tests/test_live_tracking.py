"""Live Tracking foundation: the checks the live-session spec calls for, end to end through the real application.

Covers session creation and its validation (permission, tenant, employee, device, online), WebSocket
authentication and authorization on both signalling paths, stopping, the per-session event timeline, and the
STUN-only / missing-TURN configuration. Deeper signalling behaviour lives in test_live.py and test_scaling.py.
"""

from __future__ import annotations

from typing import Any

import pytest
from bson import ObjectId
from fastapi.testclient import TestClient
from pydantic import SecretStr
from starlette.websockets import WebSocketDisconnect

from app.core.config import Settings
from app.services.live_ice import IceServerProvider
from tests.conftest import CapturingEmailSender, register
from tests.org_helpers import Workspace, auth
from tests.test_agent_api import enrol_member
from tests.test_live import agent_socket, enable, working

SECRET = "x" * 48


def other_company(client: TestClient, email_sender: CapturingEmailSender) -> Workspace:
    from tests.org_helpers import Actor

    created = register(client, company_name="Other Co")
    token = str(created["access_token"])
    email = created["user"]["email"]  # type: ignore[index]
    listing = client.get("/api/employees", params={"search": email}, headers=auth(token)).json()
    return Workspace(
        client, Actor(token, listing["items"][0]["id"], created["user"]["id"], email), email_sender
    )  # type: ignore[index]


def events(ws: Workspace, session_id: str) -> list[str]:
    response = ws.get(f"/live/sessions/{session_id}/events")
    assert response.status_code == 200, response.text
    return [e["event"] for e in response.json()["items"]]


# --------------------------------------------------------------------------- 1. authorized manager can start


def test_a_manager_starts_a_session_and_the_server_decides_company_and_viewer(
    ws: Workspace, client: TestClient, sync_db: Any
) -> None:
    enable(ws)
    manager = ws.member("Mia Manager", role="MANAGER")
    member, agent = enrol_member(ws, "Ola Online")
    # A manager's scope is the departments they head.
    dept = ws.department("Field Ops", head_employee_id=manager.employee_id)
    assert ws.patch(f"/employees/{member.employee_id}", {"department_id": dept["id"]}).status_code == 200
    working(agent)
    with agent_socket(client, agent):
        # Extra fields such as company_id / manager_id are ignored: they always come from the signed-in user.
        created = client.post(
            "/api/live/sessions",
            json={"employee_id": member.employee_id, "device_id": agent.device_id},
            headers=auth(manager.token),
        )
        assert created.status_code == 201, created.text
        body = created.json()
        assert body["status"] == "requested" and body["connection_state"] == "waiting_for_peer"
        assert body["employee"]["id"] == member.employee_id and body["device"]["id"] == agent.device_id
        assert body["device"]["last_seen_at"] is not None
        doc = sync_db["live_sessions"].find_one({"_id": ObjectId(body["id"])})
        assert str(doc["viewer_user_id"]) == manager.user_id and doc["company_id"] is not None
        client.post(f"/api/live/sessions/{body['id']}/stop", headers=auth(manager.token))


# --------------------------------------------------------------------------- 2. unauthorized users


def test_people_without_live_permission_are_refused(ws: Workspace, client: TestClient) -> None:
    enable(ws)
    member, agent = enrol_member(ws, "Pat Private")
    working(agent)
    lead = ws.member("Tess Lead", role="TEAM_LEAD")
    colleague = ws.member("Cole Colleague")
    with agent_socket(client, agent):
        for actor in (lead, colleague):
            r = client.post(
                "/api/live/sessions", json={"employee_id": member.employee_id}, headers=auth(actor.token)
            )
            assert r.status_code == 403, (actor, r.text)
    assert client.post("/api/live/sessions", json={"employee_id": member.employee_id}).status_code == 401


# --------------------------------------------------------------------------- 3. tenant isolation


def test_employees_and_devices_of_another_company_are_invisible(
    ws: Workspace, client: TestClient, email_sender: CapturingEmailSender
) -> None:
    enable(ws)
    member, agent = enrol_member(ws, "Hidden Hana")
    working(agent)
    other = other_company(client, email_sender)
    enable(other)
    with agent_socket(client, agent):
        r = other.post("/live/sessions", {"employee_id": member.employee_id})
        assert r.status_code == 404 and r.json()["error"]["code"] == "employee_not_found"
        # Own employee, the other company's device: not found either.
        own, own_agent = enrol_member(other, "Own Otto")
        working(own_agent)
        with agent_socket(client, own_agent):
            r = other.post("/live/sessions", {"employee_id": own.employee_id, "device_id": agent.device_id})
            assert r.status_code == 404 and r.json()["error"]["code"] == "device_not_found"
        # A session of company A can't be read, stopped or joined from company B.
        sid = ws.post("/live/sessions", {"employee_id": member.employee_id}).json()["id"]
        assert other.get(f"/live/sessions/{sid}").status_code == 404
        assert other.get(f"/live/sessions/{sid}/events").status_code == 404
        assert other.post(f"/live/sessions/{sid}/stop", {}).status_code == 404
        foreign = f"/api/live/signaling/{sid}?token={other.admin.token}"
        with pytest.raises(WebSocketDisconnect), client.websocket_connect(foreign) as sock:
            sock.receive_json()
        ws.post(f"/live/sessions/{sid}/stop", {})


# --------------------------------------------------------------------------- 4-6. invalid input and offline devices


def test_unknown_employee_is_rejected(ws: Workspace) -> None:
    enable(ws)
    r = ws.post("/live/sessions", {"employee_id": str(ObjectId())})
    assert r.status_code == 404 and r.json()["error"]["code"] == "employee_not_found"
    assert ws.post("/live/sessions", {"employee_id": "not-an-id"}).status_code == 422


def test_a_device_that_is_not_the_employees_or_is_revoked_is_rejected(
    ws: Workspace, client: TestClient
) -> None:
    enable(ws)
    member, agent = enrol_member(ws, "Dev Device")
    _, someone_else = enrol_member(ws, "Sam Else")
    working(agent)
    with agent_socket(client, agent):
        unknown = ws.post("/live/sessions", {"employee_id": member.employee_id, "device_id": str(ObjectId())})
        assert unknown.status_code == 404 and unknown.json()["error"]["code"] == "device_not_found"
        not_theirs = ws.post(
            "/live/sessions", {"employee_id": member.employee_id, "device_id": someone_else.device_id}
        )
        assert not_theirs.status_code == 404 and not_theirs.json()["error"]["code"] == "device_not_found"
    assert ws.post(f"/devices/{agent.device_id}/revoke", {}).status_code == 200
    revoked = ws.post("/live/sessions", {"employee_id": member.employee_id, "device_id": agent.device_id})
    assert revoked.status_code == 404 and revoked.json()["error"]["code"] == "device_not_found"


def test_an_offline_device_cannot_start_a_session(ws: Workspace) -> None:
    enable(ws)
    member, agent = enrol_member(ws, "Off Line")
    working(agent)  # heartbeating, but no live signalling connection: the agent can't answer a stream
    r = ws.post("/live/sessions", {"employee_id": member.employee_id, "device_id": agent.device_id})
    assert r.status_code == 409 and r.json()["error"]["code"] == "agent_offline"


def test_live_monitoring_must_be_allowed_by_policy(ws: Workspace, client: TestClient) -> None:
    member, agent = enrol_member(ws, "Pol Icy")
    working(agent)
    with agent_socket(client, agent):
        r = ws.post("/live/sessions", {"employee_id": member.employee_id})
        assert r.status_code == 403 and r.json()["error"]["code"] == "live_view_disabled"


# --------------------------------------------------------------------------- 7-8. WebSocket authentication / authorization


@pytest.mark.parametrize("path", ["/api/live/signaling/{sid}", "/api/live/sessions/{sid}/ws"])
def test_signaling_websocket_requires_the_requesting_viewer(
    ws: Workspace, client: TestClient, path: str
) -> None:
    enable(ws)
    member, agent = enrol_member(ws, "Sig Nal")
    working(agent)
    other_admin = ws.member("Ada Other", role="COMPANY_ADMIN")
    with agent_socket(client, agent):
        sid = ws.post("/live/sessions", {"employee_id": member.employee_id}).json()["id"]
        url = path.format(sid=sid)
        for bad in (
            url,
            f"{url}?token=not-a-jwt",
            f"{url}?token={member.token}",
            f"{url}?token={other_admin.token}",
        ):
            with pytest.raises(WebSocketDisconnect), client.websocket_connect(bad) as sock:
                sock.receive_json()
        with client.websocket_connect(url, subprotocols=["workpulse.v1", f"bearer.{ws.admin.token}"]) as sock:
            ready = sock.receive_json()
            assert ready["type"] == "ready" and ready["agent_online"] is True
            sock.send_json({"type": "ping"})
            assert sock.receive_json()["type"] == "pong"
        ws.post(f"/live/sessions/{sid}/stop", {})


# --------------------------------------------------------------------------- 9-10. stop and the event timeline


def test_a_full_session_leaves_a_complete_timeline(ws: Workspace, client: TestClient, sync_db: Any) -> None:
    enable(ws)
    member, agent = enrol_member(ws, "Tim Line")
    working(agent)
    with agent_socket(client, agent) as agent_sock:
        sid = ws.post("/live/sessions", {"employee_id": member.employee_id}).json()["id"]
        with client.websocket_connect(f"/api/live/signaling/{sid}?token={ws.admin.token}") as viewer:
            viewer.receive_json()
            viewer.send_json({"type": "offer", "sdp": "v=0 offer"})
            assert agent_sock.receive_json()["type"] == "offer"
            agent_sock.send_json({"type": "answer", "session_id": sid, "sdp": "v=0 answer"})
            viewer.receive_json()
            viewer.send_json({"type": "state", "state": "connected"})
            # The media path drops and comes back.
            viewer.send_json({"type": "state", "state": "failed"})
            viewer.send_json({"type": "offer", "sdp": "v=0 again"})
            assert agent_sock.receive_json()["sdp"] == "v=0 again"
            viewer.send_json({"type": "state", "state": "connected"})
            for _ in range(50):
                if sync_db["live_sessions"].find_one({"_id": ObjectId(sid)})["reconnects"] >= 1:
                    break
            viewer.send_json({"type": "stop"})
            assert viewer.receive_json()["type"] in ("answer", "ended")
    session = ws.get(f"/live/sessions/{sid}").json()
    assert session["status"] == "ended" and session["end_reason"] == "viewer_stopped"
    assert session["connection_state"] == "closed"
    timeline = events(ws, sid)
    assert timeline[:4] == ["STREAM_REQUESTED", "STREAM_AUTHORIZED", "STREAM_CONNECTING", "STREAM_STARTED"]
    assert "STREAM_DISCONNECTED" in timeline and "STREAM_RECONNECTED" in timeline
    assert timeline[-1] == "STREAM_STOPPED"
    stopped = ws.get(f"/live/sessions/{sid}/events").json()["items"][-1]
    assert stopped["actor_role"] == "viewer" and stopped["actor_id"] == ws.admin.user_id
    assert stopped["metadata"]["reason"] == "viewer_stopped"


def test_stopping_through_the_api_ends_the_session_and_records_it(ws: Workspace, client: TestClient) -> None:
    enable(ws)
    member, agent = enrol_member(ws, "Stop Me")
    working(agent)
    with agent_socket(client, agent) as agent_sock:
        sid = ws.post("/live/sessions", {"employee_id": member.employee_id}).json()["id"]
        stopped = ws.post(f"/live/sessions/{sid}/stop", {})
        assert stopped.status_code == 200 and stopped.json()["status"] == "ended"
        assert stopped.json()["ended_at"] is not None and stopped.json()["end_reason"] == "viewer_stopped"
        message = agent_sock.receive_json()
        assert (
            message["type"] == "stop" and message["session_id"] == sid
        )  # the agent is told to stop capturing
    assert events(ws, sid)[-1] == "STREAM_STOPPED"
    # Stopping again is harmless.
    assert ws.post(f"/live/sessions/{sid}/stop", {}).json()["status"] == "ended"


def test_a_session_that_never_connects_is_recorded_as_failed(ws: Workspace, client: TestClient) -> None:
    from tests.test_live import fast_timers

    enable(ws)
    member, agent = enrol_member(ws, "Never Connects")
    working(agent)
    with agent_socket(client, agent), fast_timers(client, live_connect_timeout_seconds=0):
        sid = ws.post("/live/sessions", {"employee_id": member.employee_id}).json()["id"]
        for _ in range(100):
            if ws.get(f"/live/sessions/{sid}").json()["status"] == "ended":
                break
    failed = ws.get(f"/live/sessions/{sid}/events").json()["items"][-1]
    assert failed["event"] == "STREAM_FAILED" and failed["metadata"]["reason"] == "connect_timeout"


# --------------------------------------------------------------------------- 11-12. STUN only, TURN optional


def test_missing_turn_configuration_is_fine() -> None:
    settings = Settings(jwt_secret=SECRET, live_stun_urls="", live_turn_urls="", live_turn_secret="")
    provider = IceServerProvider(settings)
    assert provider.turn_enabled is False
    assert provider.servers("viewer-1") == []


def test_stun_only_configuration_gives_peers_stun_and_no_credentials() -> None:
    settings = Settings(jwt_secret=SECRET, live_stun_urls="stun:stun.cloudflare.com:3478", live_turn_urls="")
    servers = IceServerProvider(settings).servers("viewer-1")
    assert [s.model_dump(exclude_none=True) for s in servers] == [{"urls": ["stun:stun.cloudflare.com:3478"]}]


def test_turn_is_added_when_configured() -> None:
    settings = Settings(
        jwt_secret=SECRET,
        live_stun_urls="stun:stun.cloudflare.com:3478",
        live_turn_urls="turn:turn.example.com:3478?transport=udp",
        live_turn_secret=SecretStr("shared"),
    )
    stun, turn = IceServerProvider(settings).servers("viewer-1")
    assert stun.urls == ["stun:stun.cloudflare.com:3478"]
    assert turn.username and turn.username.endswith(":viewer-1") and turn.credential


def test_the_viewer_gets_stun_only_servers_over_signaling(ws: Workspace, client: TestClient) -> None:
    enable(ws)
    member, agent = enrol_member(ws, "Stun Only")
    working(agent)
    hub = client.app.state.live_hub  # type: ignore[attr-defined]
    original = hub.ice
    hub.ice = IceServerProvider(Settings(jwt_secret=SECRET, live_stun_urls="stun:stun.cloudflare.com:3478"))
    try:
        with agent_socket(client, agent):
            sid = ws.post("/live/sessions", {"employee_id": member.employee_id}).json()["id"]
            with client.websocket_connect(f"/api/live/signaling/{sid}?token={ws.admin.token}") as viewer:
                ready = viewer.receive_json()
                assert ready["ice_servers"] == [{"urls": ["stun:stun.cloudflare.com:3478"]}]
            ws.post(f"/live/sessions/{sid}/stop", {})
    finally:
        hub.ice = original
