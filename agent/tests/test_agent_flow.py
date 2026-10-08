"""Agent behaviour against a fake API: sign-in, heartbeat, sync, offline queueing, recovery, revocation."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from app.agent import Agent
from app.auth.device_auth import CredentialsRejectedError
from app.heartbeat.connection import ConnectionState
from app.sync.api_client import ApiClient, ApiError, ApiUnavailable
from tests.conftest import PASSWORD, FakeApi


def signed_in(make_agent: Callable[..., Agent]) -> Agent:
    agent = make_agent()
    agent.sign_in("ada@example.com", PASSWORD)
    return agent


def test_sign_in_stores_credentials_encrypted_and_never_the_password(
    make_agent: Callable[..., Agent], fake_api: FakeApi, tmp_path: Path
) -> None:
    agent = signed_in(make_agent)
    snap = agent.snapshot()
    assert snap.signed_in and snap.employee_name == "Ada Lovelace" and snap.company_name == "Analytical Engines Ltd"

    for file in (tmp_path / "agent").rglob("*"):
        if file.is_file():
            content = file.read_bytes()
            assert PASSWORD.encode() not in content, file
            assert fake_api.secret.encode() not in content, file

    # A fresh process restores the identity from the encrypted store.
    restarted = make_agent()
    assert restarted.snapshot().employee_name == "Ada Lovelace"


def test_wrong_password_is_reported(make_agent: Callable[..., Agent]) -> None:
    agent = make_agent()
    with pytest.raises(ApiError) as exc:
        agent.sign_in("ada@example.com", "wrong-password-1")
    assert exc.value.code == "invalid_credentials"
    assert not agent.auth.signed_in


def test_heartbeat_reports_presence_and_session(make_agent: Callable[..., Agent], fake_api: FakeApi) -> None:
    agent = signed_in(make_agent)
    assert agent.heartbeat.beat()
    assert agent.connection.state == ConnectionState.CONNECTED
    assert fake_api.heartbeats[-1]["presence"] is None

    agent.start_session()
    agent.heartbeat.beat()
    beat = fake_api.heartbeats[-1]
    assert beat["presence"] == "active" and beat["session_id"] == agent.sessions.session_id
    assert set(beat) == {"presence", "session_id", "agent_version", "sent_at", "current_app"}  # metadata only


def test_events_sync_in_order_and_idempotently(make_agent: Callable[..., Agent], fake_api: FakeApi) -> None:
    agent = signed_in(make_agent)
    agent.start_session()
    agent.stop_session()
    assert agent.sync.flush() == 3
    assert fake_api.types() == ["agent.started", "session.started", "session.stopped"]
    assert len(agent.queue) == 0
    assert agent.sync.flush() == 0


def test_offline_events_are_kept_and_synced_on_reconnect(make_agent: Callable[..., Agent], fake_api: FakeApi) -> None:
    agent = signed_in(make_agent)
    agent.heartbeat.beat()
    fake_api.down = True

    agent.start_session()
    assert not agent.heartbeat.beat()
    assert agent.connection.state == ConnectionState.OFFLINE
    assert agent.sync.flush() == 0
    agent.stop_session()
    assert len(agent.queue) == 3  # agent.started, session.started, session.stopped all retained
    assert fake_api.events == []

    fake_api.down = False
    assert agent.heartbeat.beat()  # reconnect releases back-off and wakes sync
    assert agent.connection.state == ConnectionState.CONNECTED
    assert agent.sync.flush() == 3
    assert fake_api.types() == ["agent.started", "session.started", "session.stopped"]


def test_queued_events_survive_a_restart(make_agent: Callable[..., Agent], fake_api: FakeApi, tmp_path: Path) -> None:
    agent = signed_in(make_agent)
    fake_api.down = True
    agent.start_session()
    agent.stop_session()
    agent.queue.close()

    fake_api.down = False
    restarted = make_agent(data_dir=tmp_path / "agent")
    restarted.queue.release_all()
    assert restarted.sync.flush() == 3


def test_expired_token_is_refreshed_transparently(make_agent: Callable[..., Agent], fake_api: FakeApi) -> None:
    agent = signed_in(make_agent)
    agent.start_session()
    agent.sync.flush()
    fake_api.expire_tokens()
    agent.stop_session()
    assert agent.sync.flush() == 1
    assert fake_api.types()[-1] == "session.stopped"


def test_server_errors_back_off_without_losing_events(make_agent: Callable[..., Agent], fake_api: FakeApi) -> None:
    agent = signed_in(make_agent)
    agent.sync.flush()
    agent.start_session()
    fake_api.status_override = 503
    assert agent.sync.flush() == 0
    assert len(agent.queue) == 1
    assert agent.queue.due(10) == []  # deferred by back-off
    fake_api.status_override = None
    agent.queue.release_all()
    assert agent.sync.flush() == 1


def test_invalid_event_is_isolated(make_agent: Callable[..., Agent], fake_api: FakeApi) -> None:
    agent = signed_in(make_agent)
    agent.sync.flush()
    fake_api.reject_types = {"session.stopped"}
    agent.start_session()
    agent.stop_session()
    assert agent.sync.flush() == 1  # the good event goes through, the bad one is dropped
    assert fake_api.types()[-1] == "session.started"
    assert len(agent.queue) == 0


def test_revoked_device_signs_out_and_stops_tracking(make_agent: Callable[..., Agent], fake_api: FakeApi) -> None:
    agent = signed_in(make_agent)
    agent.start_session()
    agent.heartbeat.beat()
    fake_api.revoked = True
    agent.heartbeat.beat()
    snap = agent.snapshot()
    assert snap.connection == ConnectionState.REVOKED
    assert not snap.signed_in and not agent.sessions.running
    assert len(agent.queue) == 0
    agent.heartbeat.beat()  # the reason stays visible
    assert agent.connection.state == ConnectionState.REVOKED


def test_sign_out_reports_and_clears(make_agent: Callable[..., Agent], fake_api: FakeApi) -> None:
    agent = signed_in(make_agent)
    agent.start_session()
    agent.sign_out()
    assert fake_api.types()[-2:] == ["session.stopped", "agent.stopped"]
    assert fake_api.events[-2]["reason"] == "sign_out"
    assert not agent.auth.signed_in and agent.connection.state == ConnectionState.SIGNED_OUT


def test_api_client_retries_transient_failures() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) < 3:
            return httpx.Response(503, headers={"Retry-After": "1"})
        return httpx.Response(200, json={"ok": True})

    sleeps: list[float] = []
    api = ApiClient("http://test/api", transport=httpx.MockTransport(handler), retries=2, sleep=sleeps.append)
    assert api.request("GET", "/x") == {"ok": True}
    assert len(calls) == 3 and 1.0 in sleeps

    def unreachable(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("nope", request=request)

    api = ApiClient("http://test/api", transport=httpx.MockTransport(unreachable), retries=2, sleep=lambda _s: None)
    with pytest.raises(ApiUnavailable):
        api.request("GET", "/x")

    def forbidden(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(403, json={"error": {"code": "forbidden", "message": "No"}})

    calls.clear()
    api = ApiClient("http://test/api", transport=httpx.MockTransport(forbidden), retries=2, sleep=lambda _s: None)
    with pytest.raises(ApiError):
        api.request("GET", "/x")
    assert len(calls) == 1  # client errors are never retried


def test_rejected_credentials_raise(make_agent: Callable[..., Agent], fake_api: FakeApi) -> None:
    agent = signed_in(make_agent)
    fake_api.revoked = True
    with pytest.raises(CredentialsRejectedError):
        agent.auth.token()


def test_heartbeat_interval_is_jittered(make_agent: Callable[..., Agent]) -> None:
    """Agents that reconnect together (after a server restart) must not stay in lockstep."""
    agent = make_agent()
    base = agent.config.heartbeat_interval
    intervals = {round(agent.heartbeat.interval(), 3) for _ in range(50)}
    assert len(intervals) > 10
    assert all(base * 0.9 <= i <= base * 1.1 for i in intervals)
