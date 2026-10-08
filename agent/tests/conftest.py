"""Test fixtures: an in-memory fake of the WorkPulse agent API and a test agent factory."""

from __future__ import annotations

import itertools
import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.activity.foreground import ForegroundApp
from app.agent import Agent
from app.config import AgentConfig
from app.screenshots.capture import CapturedImage
from app.security.protector import KeyFileProtector
from app.sync.api_client import ApiClient

PASSWORD = "Correct1Password"
POLICY: dict[str, Any] = {
    "heartbeat_interval_seconds": 60,
    "sync_interval_seconds": 30,
    "idle_threshold_seconds": 300,
    "max_batch_size": 50,
    "activity": {"track_applications": True, "capture_window_titles": False, "excluded_apps": []},
    "screenshots": {
        "enabled": False,
        "interval_seconds": 600,
        "work_hours_only": False,
        "work_start": "09:00",
        "work_end": "18:00",
        "work_days": [1, 2, 3, 4, 5],
        "timezone": "UTC",
    },
}


class FakeApi:
    """Behaves like the real agent endpoints closely enough to test the agent end to end."""

    def __init__(self) -> None:
        self.down = False
        self.status_override: int | None = None
        self.revoked = False
        self.reject_types: set[str] = set()
        self.secret = "device-secret-" + "x" * 40
        self.tokens: set[str] = set()
        self._counter = itertools.count(1)
        self.events: list[dict[str, Any]] = []
        self.heartbeats: list[dict[str, Any]] = []
        self.screenshots: list[dict[str, Any]] = []
        self.screenshot_status: int | None = None
        self.screenshot_code = "screenshots_disabled"
        self.requests: list[tuple[str, str]] = []
        self.employee = {"id": "e1", "full_name": "Ada Lovelace", "email": "ada@example.com"}
        self.company = {"id": "c1", "name": "Analytical Engines Ltd"}
        self.policy: dict[str, Any] = json.loads(json.dumps(POLICY))

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append((request.method, request.url.path))
        if self.down:
            raise httpx.ConnectError("server unreachable", request=request)
        if self.status_override:
            return httpx.Response(self.status_override, json={"error": {"code": "unavailable", "message": "Try later"}})
        if request.url.path.endswith("/agent/screenshots"):
            return self._screenshot(request)
        body = json.loads(request.content or b"{}")
        path = request.url.path.removeprefix("/api")

        if path == "/agent/register":
            if body["password"] != PASSWORD:
                return self._error(401, "invalid_credentials", "Invalid email or password.")
            return httpx.Response(200, json=self._identity() | {"device_secret": self.secret})
        if path == "/agent/token":
            if self.revoked or body["device_secret"] != self.secret:
                return self._error(401, "invalid_device_credentials", "Device credentials are invalid or revoked.")
            token = f"tok-{next(self._counter)}"
            self.tokens.add(token)
            return httpx.Response(
                200, json=self._identity() | {"access_token": token, "token_type": "bearer", "expires_in": 1800}
            )

        bearer = request.headers.get("Authorization", "").removeprefix("Bearer ")
        if self.revoked:
            return self._error(401, "device_revoked", "This device has been revoked.")
        if bearer not in self.tokens:
            return self._error(401, "token_expired", "Device token has expired.")
        if path == "/agent/heartbeat":
            self.heartbeats.append(body)
            return httpx.Response(
                200, json={"server_time": "2026-10-01T00:00:00Z", "device_status": "active", "policy": self.policy}
            )
        if path == "/agent/events":
            if any(e["type"] in self.reject_types for e in body["events"]):
                return self._error(422, "validation_error", "Request validation failed.")
            seen = {e["id"] for e in self.events}
            fresh = [e for e in body["events"] if e["id"] not in seen]
            self.events.extend(fresh)
            return httpx.Response(
                200, json={"accepted": len(fresh), "duplicates": len(body["events"]) - len(fresh), "rejected": []}
            )
        return self._error(404, "not_found", path)

    def _screenshot(self, request: httpx.Request) -> httpx.Response:
        if request.headers.get("Authorization", "").removeprefix("Bearer ") not in self.tokens:
            return self._error(401, "token_expired", "Device token has expired.")
        if self.screenshot_status:
            return self._error(self.screenshot_status, self.screenshot_code, "refused")
        params = dict(request.url.params)
        duplicate = any(s["id"] == params["id"] for s in self.screenshots)
        if not duplicate:
            self.screenshots.append(params | {"bytes": request.content, "type": request.headers["Content-Type"]})
        return httpx.Response(200, json={"id": "s" * 24, "duplicate": duplicate})

    def expire_tokens(self) -> None:
        self.tokens.clear()

    def types(self) -> list[str]:
        return [e["type"] for e in self.events]

    def _identity(self) -> dict[str, Any]:
        return {"device_id": "d" * 24, "employee": self.employee, "company": self.company, "policy": self.policy}

    @staticmethod
    def _error(status: int, code: str, message: str) -> httpx.Response:
        return httpx.Response(status, json={"error": {"code": code, "message": message, "details": None}})


class FakeIdle:
    def __init__(self) -> None:
        self.seconds = 0.0

    def idle_seconds(self) -> float:
        return self.seconds


class FakeCapturer:
    def __init__(self) -> None:
        self.calls = 0
        self.fail = False

    def capture(self) -> CapturedImage | None:
        self.calls += 1
        if self.fail:
            return None
        return CapturedImage(b"RIFF0000WEBPVP8 fake-" + str(self.calls).encode(), 1920, 1080)


class FakeProbe:
    """Foreground application under test control; records whether the title was asked for."""

    def __init__(self, app: ForegroundApp | None = None) -> None:
        self.app = app
        self.title_requests: list[bool] = []
        self.domain_requests: list[bool] = []

    def current(self, include_title: bool, include_domain: bool = False) -> ForegroundApp | None:
        self.title_requests.append(include_title)
        self.domain_requests.append(include_domain)
        if self.app is None:
            return None
        return ForegroundApp(
            self.app.app_id,
            self.app.app_name,
            self.app.title if include_title else None,
            self.app.domain if include_domain else None,
        )


@pytest.fixture
def fake_api() -> FakeApi:
    return FakeApi()


@pytest.fixture
def make_agent(tmp_path: Path, fake_api: FakeApi) -> Iterator[Callable[..., Agent]]:
    agents: list[Agent] = []

    def factory(
        data_dir: Path | None = None,
        idle: FakeIdle | None = None,
        probe: FakeProbe | None = None,
        capturer: FakeCapturer | None = None,
    ) -> Agent:
        directory = data_dir or tmp_path / "agent"
        config = AgentConfig(api_url="http://test/api", data_dir=directory)
        api = ApiClient(config.api_url, transport=httpx.MockTransport(fake_api), retries=1, sleep=lambda _s: None)
        agent = Agent(
            config,
            api=api,
            idle_detector=idle or FakeIdle(),
            protector=KeyFileProtector(directory / ".key"),
            probe=probe or FakeProbe(),
            capturer=capturer or FakeCapturer(),
        )
        agents.append(agent)
        return agent

    yield factory
    for agent in agents:
        for worker in (agent.heartbeat, agent.sync, agent.monitor, agent.screenshots):
            worker.stop(timeout=1)
