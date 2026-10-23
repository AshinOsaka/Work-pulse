"""Phase (prod): the browser-extension bridge — loopback only, domain-only, fresh-window semantics."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

import pytest

from app.activity.extension import DomainStore, ExtensionBridge


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_store_returns_a_reported_host_only_while_it_is_fresh() -> None:
    clock = FakeClock()
    store = DomainStore(clock=clock, fresh_seconds=30.0)
    assert store.current() is None and store.connected is False
    store.report("github.com")
    assert store.current() == "github.com" and store.connected is True
    clock.now += 29
    assert store.current() == "github.com"  # still fresh
    clock.now += 2
    assert store.current() is None and store.connected is False  # lapsed -> fall back to UI Automation
    store.report(None)  # a non-web tab / browser unfocused clears it
    assert store.current() is None


@pytest.fixture
def bridge() -> Any:
    store = DomainStore()
    b = ExtensionBridge(store, port=0)  # port 0 -> an ephemeral free port, so tests never collide
    assert b.start() is True
    try:
        yield b, store
    finally:
        b.stop()


def _post(port: int, body: dict[str, Any], *, token: str | None = None) -> int:
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["X-WorkPulse-Token"] = token
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/domain", data=json.dumps(body).encode(), headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=2) as res:  # noqa: S310 (loopback, fixed scheme)
            return int(res.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)


def test_posting_a_domain_sanitises_it_and_stores_only_the_host(bridge: Any) -> None:
    b, store = bridge
    assert _post(b.port, {"domain": "https://www.GitHub.com/a/b?x=1#f"}) == 204
    assert store.current() == "github.com"  # scheme, www., path, query and case all dropped
    assert _post(b.port, {"domain": "edge://settings"}) == 204
    assert store.current() is None  # a browser internal page is not a website


def test_incognito_and_bad_requests_never_record_a_domain(bridge: Any) -> None:
    b, store = bridge
    store.report("github.com")
    assert _post(b.port, {"domain": "secret.example.com", "incognito": True}) == 204
    assert store.current() is None  # incognito is refused as defence in depth

    req = urllib.request.Request(f"http://127.0.0.1:{b.port}/nope", data=b"{}", method="POST")
    try:
        urllib.request.urlopen(req, timeout=2)  # noqa: S310
        status = 200
    except urllib.error.HTTPError as exc:
        status = exc.code
    assert status == 404  # only /domain is a write endpoint


def test_health_endpoint_identifies_the_agent(bridge: Any) -> None:
    b, _store = bridge
    with urllib.request.urlopen(f"http://127.0.0.1:{b.port}/health", timeout=2) as res:
        assert res.status == 200
        assert json.loads(res.read())["app"] == "workpulse-agent"


def test_a_token_is_required_when_the_agent_sets_one() -> None:
    store = DomainStore()
    b = ExtensionBridge(store, port=0, token="s3cret")
    assert b.start() is True
    try:
        assert _post(b.port, {"domain": "github.com"}) == 403  # no token
        assert _post(b.port, {"domain": "github.com"}, token="wrong") == 403
        assert _post(b.port, {"domain": "github.com"}, token="s3cret") == 204
        assert store.current() == "github.com"
    finally:
        b.stop()
