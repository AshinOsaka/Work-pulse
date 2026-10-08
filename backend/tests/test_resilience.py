"""Phase 18: infrastructure failures surface as clear, retryable errors, never as "unexpected error" crashes.

The real stack was also tested by stopping the MongoDB and Redis containers mid-use (see docs/qa.md); these tests pin
the behaviour by injecting the drivers' own exceptions.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pymongo.errors import ServerSelectionTimeoutError
from redis.exceptions import ConnectionError as RedisConnectionError
from starlette.websockets import WebSocketDisconnect

from app.core.broker import MemoryBroker
from app.repositories.user import UserRepository
from tests.org_helpers import Workspace, auth
from tests.test_agent_api import enrol_member
from tests.test_live import enable as enable_live


class DownBroker(MemoryBroker):
    """Redis that has gone away: every operation fails like redis-py does."""

    shared = True

    async def _fail(self, *args: Any, **kwargs: Any) -> Any:
        raise RedisConnectionError("Connection refused")

    ping = publish = subscribe = unsubscribe = set = get = get_many = delete = lease = hit = _fail  # type: ignore[assignment]


@pytest.fixture
def redis_down(client: TestClient) -> Iterator[None]:
    state = client.app.state  # type: ignore[attr-defined]
    hub, manager, original = state.live_hub, state.ws_manager, state.broker
    down = DownBroker()
    hub.broker, manager._broker, state.broker = down, down, down
    yield
    hub.broker, manager._broker, state.broker = original, original, original


def test_database_outage_is_a_retryable_503(
    ws: Workspace, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def unreachable(*args: Any, **kwargs: Any) -> Any:
        raise ServerSelectionTimeoutError("No servers found yet")

    monkeypatch.setattr(UserRepository, "get_by_id", unreachable)
    response = client.get("/api/auth/me", headers=auth(ws.admin.token))
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "database_unavailable"
    assert response.headers["retry-after"] == "5"


def test_redis_outage_degrades_live_features_cleanly(
    ws: Workspace, client: TestClient, redis_down: None
) -> None:
    enable_live(ws)
    member, _ = enrol_member(ws, "Odin Outage")
    # Everything that doesn't need Redis keeps working.
    assert ws.get("/employees").status_code == 200
    assert ws.get("/auth/me").status_code == 200
    # Live features say what's wrong instead of failing with "unexpected error".
    for response in (
        ws.get("/live/employees"),
        ws.post("/live/sessions", {"employee_id": member.employee_id}),
    ):
        assert response.status_code == 503, response.text
        assert response.json()["error"]["code"] == "realtime_unavailable"
    # Health shows which dependency is down.
    health = client.get("/api/health")
    assert health.status_code == 503 and health.json()["checks"]["realtime"]["status"] == "unavailable"
    assert health.json()["checks"]["database"]["status"] == "ok"
    # Sockets are told to come back later (browsers and agents reconnect with back-off).
    with (
        pytest.raises(WebSocketDisconnect) as closed,
        client.websocket_connect(f"/api/ws?token={ws.admin.token}") as sock,
    ):
        sock.receive_json()
        sock.receive_json()
    assert closed.value.code == 1013


def test_health_reports_realtime_when_shared(client: TestClient) -> None:
    body = client.get("/api/health").json()
    if client.app.state.broker.shared:  # type: ignore[attr-defined]
        assert body["checks"]["realtime"]["status"] == "ok"
    else:  # single-process mode has no Redis to check
        assert "realtime" not in body["checks"]
