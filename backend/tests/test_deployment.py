"""Phase 19: production readiness — configuration guard, e-mail delivery, index upgrades, metrics, error tracking."""

from __future__ import annotations

import asyncio
import socketserver
import threading
import time
from collections.abc import Iterator
from email import message_from_bytes
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from pymongo import ASCENDING, AsyncMongoClient, IndexModel
from starlette.websockets import WebSocketDisconnect

from app.core.config import Settings
from app.core.observability import clear_error_reporters, register_error_reporter
from app.repositories.base import CASE_INSENSITIVE, sync_indexes
from app.services.email_service import EmailDeliveryError, EmailMessage, SmtpEmailSender
from tests.conftest import register, unique_email

SECRET = "x" * 48
SAFE_PRODUCTION: dict[str, Any] = {
    "jwt_secret": SECRET,
    "environment": "production",
    "frontend_url": "https://workpulse.example.com",
    "refresh_cookie_secure": True,
    "email_backend": "smtp",
    "smtp_host": "smtp.example.com",
    "storage_encryption_key": "a" * 44,
    "redis_url": "redis://:pw@redis:6379/0",
}


# --- Configuration guard -------------------------------------------------------------------------------------------


def test_safe_production_settings_start() -> None:
    assert Settings(**SAFE_PRODUCTION).configuration_problems() == []


@pytest.mark.parametrize(
    ("override", "expected"),
    [
        ({"frontend_url": "http://workpulse.example.com"}, "FRONTEND_URL"),
        ({"refresh_cookie_secure": False}, "REFRESH_COOKIE_SECURE"),
        ({"email_backend": "console"}, "EMAIL_BACKEND=console"),
        ({"storage_encryption_key": None}, "STORAGE_ENCRYPTION_KEY"),
        ({"redis_url": None}, "REDIS_URL"),
        ({"debug": True}, "DEBUG"),
        ({"cors_origins": "*"}, "CORS_ORIGINS"),
        ({"smtp_security": "none", "smtp_username": "mailer"}, "SMTP_SECURITY=none"),
    ],
)
def test_unsafe_production_settings_refuse_to_start(override: dict[str, Any], expected: str) -> None:
    with pytest.raises(ValidationError, match=expected):
        Settings(**(SAFE_PRODUCTION | override))


def test_every_problem_is_listed_at_once() -> None:
    with pytest.raises(ValidationError) as caught:
        Settings(jwt_secret=SECRET, environment="production", refresh_cookie_secure=False)
    message = str(caught.value)
    for name in (
        "FRONTEND_URL",
        "REFRESH_COOKIE_SECURE",
        "EMAIL_BACKEND",
        "STORAGE_ENCRYPTION_KEY",
        "REDIS_URL",
    ):
        assert name in message


def test_configuration_errors_never_echo_secrets() -> None:
    with pytest.raises(ValidationError) as caught:
        Settings(**(SAFE_PRODUCTION | {"email_backend": "console", "jwt_secret": "s3cr3t-" * 8}))
    assert "s3cr3t" not in str(caught.value) and "input_value" not in str(caught.value)
    with pytest.raises(ValidationError) as weak:
        Settings(jwt_secret="short-but-secret")
    assert "short-but-secret" not in str(weak.value)


def test_broken_combinations_are_refused_in_every_environment() -> None:
    with pytest.raises(ValidationError, match="BACKGROUND_JOBS=false needs REDIS_URL"):
        Settings(jwt_secret=SECRET, background_jobs=False)
    with pytest.raises(ValidationError, match="LIVE_TURN_URLS and LIVE_TURN_SECRET"):
        Settings(jwt_secret=SECRET, live_turn_urls="turn:turn.example.com:3478")
    with pytest.raises(ValidationError, match="SMTP_HOST"):
        Settings(jwt_secret=SECRET, email_backend="smtp")
    # Development defaults stay valid.
    assert Settings(jwt_secret=SECRET).configuration_problems() == []


# --- SMTP --------------------------------------------------------------------------------------------------------


class _SmtpHandler(socketserver.StreamRequestHandler):
    """Just enough SMTP (RFC 5321) to receive a message: what a relay sees from SmtpEmailSender."""

    def handle(self) -> None:
        inbox: list[dict[str, Any]] = self.server.inbox  # type: ignore[attr-defined]
        envelope: dict[str, Any] = {"rcpt": []}
        self.wfile.write(b"220 test ESMTP\r\n")
        while line := self.rfile.readline():
            command = line.decode().strip()
            verb = command.split(" ", 1)[0].upper()
            if verb in ("EHLO", "HELO"):
                self.wfile.write(b"250-test\r\n250 8BITMIME\r\n")
            elif verb == "MAIL":
                envelope["from"] = command
                self.wfile.write(b"250 OK\r\n")
            elif verb == "RCPT":
                envelope["rcpt"].append(command)
                self.wfile.write(b"250 OK\r\n")
            elif verb == "DATA":
                self.wfile.write(b"354 go ahead\r\n")
                data = b""
                while (chunk := self.rfile.readline()) != b".\r\n":
                    data += chunk
                envelope["message"] = message_from_bytes(data)
                inbox.append(envelope)
                envelope = {"rcpt": []}
                self.wfile.write(b"250 queued\r\n")
            elif verb == "QUIT":
                self.wfile.write(b"221 bye\r\n")
                return
            else:
                self.wfile.write(b"250 OK\r\n")


@pytest.fixture
def smtp_server() -> Iterator[tuple[int, list[dict[str, Any]]]]:
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _SmtpHandler)
    server.inbox = []  # type: ignore[attr-defined]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server.server_address[1], server.inbox  # type: ignore[attr-defined]
    server.shutdown()
    server.server_close()


def _smtp_settings(port: int) -> Settings:
    return Settings(
        jwt_secret=SECRET,
        email_backend="smtp",
        smtp_host="127.0.0.1",
        smtp_port=port,
        smtp_security="none",
        smtp_timeout_seconds=5,
        email_from="WorkPulse <no-reply@workpulse.example.com>",
    )


def test_smtp_sender_delivers_a_real_message(smtp_server: tuple[int, list[dict[str, Any]]]) -> None:
    port, inbox = smtp_server
    sender = SmtpEmailSender(_smtp_settings(port))
    asyncio.run(
        sender.send(EmailMessage(to="ana@example.com", subject="Reset your password", text="Hello, Ana"))
    )
    assert len(inbox) == 1
    message = inbox[0]["message"]
    assert "ana@example.com" in inbox[0]["rcpt"][0]
    assert message["Subject"] == "Reset your password"
    assert message["From"] == "WorkPulse <no-reply@workpulse.example.com>"
    assert message["Message-ID"].endswith("@workpulse.example.com>")
    assert message.get_payload(decode=True).decode().strip() == "Hello, Ana"


def test_smtp_failure_is_a_retryable_error() -> None:
    with socketserver.TCPServer(("127.0.0.1", 0), socketserver.BaseRequestHandler) as probe:
        closed_port = probe.server_address[1]  # free after the block: nothing listens there
    sender = SmtpEmailSender(_smtp_settings(closed_port))
    with pytest.raises(EmailDeliveryError) as caught:
        asyncio.run(sender.send(EmailMessage(to="a@example.com", subject="s", text="t")))
    assert caught.value.status_code == 503 and caught.value.code == "email_unavailable"


class _FailingSender:
    async def send(self, message: EmailMessage) -> None:
        raise EmailDeliveryError()


def test_mail_outage_does_not_reveal_which_accounts_exist(app_client: TestClient) -> None:
    email = unique_email("enum")
    register(app_client, email=email)
    app = app_client.app
    original = app.state.email_sender  # type: ignore[attr-defined]
    app.state.email_sender = _FailingSender()  # type: ignore[attr-defined]
    try:
        known = app_client.post("/api/auth/forgot-password", json={"email": email})
        unknown = app_client.post("/api/auth/forgot-password", json={"email": unique_email("nobody")})
    finally:
        app.state.email_sender = original  # type: ignore[attr-defined]
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()


def test_failed_invitation_keeps_the_employee_and_says_so(app_client: TestClient) -> None:
    owner = register(app_client)
    headers = {"Authorization": f"Bearer {owner['access_token']}"}
    app = app_client.app
    original = app.state.email_sender  # type: ignore[attr-defined]
    app.state.email_sender = _FailingSender()  # type: ignore[attr-defined]
    email = unique_email("invitee")
    try:
        r = app_client.post(
            "/api/employees",
            json={"full_name": "Ivo Invite", "email": email, "invite": True},
            headers=headers,
        )
    finally:
        app.state.email_sender = original  # type: ignore[attr-defined]
    assert r.status_code == 503, r.text
    assert r.json()["error"]["code"] == "email_unavailable"
    assert "account was created" in r.json()["error"]["message"]
    listed = app_client.get("/api/employees", params={"page_size": 100}, headers=headers).json()["items"]
    listed = [e for e in listed if e["email"] == email]
    assert [e["email"] for e in listed] == [email]
    # Resending works once mail is back (no "email already taken" dead end).
    resent = app_client.post(f"/api/employees/{listed[0]['id']}/invite", json={}, headers=headers)
    assert resent.status_code == 200, resent.text


# --- Index upgrades ----------------------------------------------------------------------------------------------


def test_index_definition_changes_are_applied_on_upgrade(settings: Settings) -> None:
    async def scenario() -> dict[str, Any]:
        client: AsyncMongoClient[dict[str, Any]] = AsyncMongoClient(settings.mongodb_url)
        collection = client[settings.mongodb_db][f"upgrade_{time.time_ns()}"]
        try:
            names = IndexModel([("name", ASCENDING)], name="by_name", collation=CASE_INSENSITIVE)
            # Release 1.
            await sync_indexes(
                collection,
                [
                    IndexModel([("created_at", ASCENDING)], name="ttl", expireAfterSeconds=100),
                    IndexModel([("a", ASCENDING)], name="lookup"),
                    names,
                ],
            )
            await collection.insert_one({"name": "x", "a": 1, "b": 2})
            before = await collection.index_information()
            # Release 2: TTL changed, keys of "lookup" changed, "by_name" unchanged.
            await sync_indexes(
                collection,
                [
                    IndexModel([("created_at", ASCENDING)], name="ttl", expireAfterSeconds=200),
                    IndexModel([("b", ASCENDING)], name="lookup"),
                    names,
                ],
            )
            after = await collection.index_information()
            return {"before": before, "after": after}
        finally:
            await collection.drop()
            await client.close()

    result = asyncio.run(scenario())
    after = result["after"]
    assert after["ttl"]["expireAfterSeconds"] == 200
    assert after["lookup"]["key"] == [("b", 1)]
    assert after["by_name"]["collation"]["strength"] == 2
    # Unchanged: running the same definitions again is a no-op.
    assert result["before"]["by_name"]["key"] == after["by_name"]["key"]


# --- Health, metrics, error tracking --------------------------------------------------------------------------------


def test_liveness_and_readiness_probes(client: TestClient) -> None:
    assert client.get("/api/health/live").json() == {"status": "ok"}
    ready = client.get("/api/health/ready")
    assert ready.status_code == 200 and ready.json()["checks"]["database"]["status"] == "ok"


def test_metrics_use_route_templates(client: TestClient) -> None:
    owner = register(client)
    headers = {"Authorization": f"Bearer {owner['access_token']}"}
    client.get("/api/employees/6abe26abe454354a328eaf57", headers=headers)
    client.get("/api/auth/me", headers=headers)
    body = client.get("/metrics").text
    employee_lines = [line for line in body.splitlines() if 'route="/api/employees/{employee_id}"' in line]
    assert any(line.startswith("workpulse_http_requests_total") for line in employee_lines), body[-3000:]
    assert 'route="/api/auth/me"' in body
    assert "6abe26abe454354a328eaf57" not in body  # raw ids never become labels
    assert "workpulse_http_request_duration_seconds_bucket" in body
    assert 'workpulse_build_info{environment="test"' in body


def test_metrics_can_require_a_token(settings: Settings) -> None:
    from app.main import create_app

    app = create_app(settings.model_copy(update={"metrics_token": SecretStr("scrape-token")}))
    with TestClient(app) as protected:
        assert protected.get("/metrics").status_code == 401
        assert protected.get("/metrics", headers={"Authorization": "Bearer wrong"}).status_code == 401
        ok = protected.get("/metrics", headers={"Authorization": "Bearer scrape-token"})
        assert ok.status_code == 200 and "workpulse_http_requests_total" in ok.text


def _gauge(body: str, channel: str) -> float:
    prefix = f'workpulse_websocket_connections{{channel="{channel}"}} '
    return next((float(line[len(prefix) :]) for line in body.splitlines() if line.startswith(prefix)), 0.0)


def test_open_websockets_are_counted(client: TestClient) -> None:
    owner = register(client)
    before = _gauge(client.get("/metrics").text, "app")
    with client.websocket_connect(f"/api/ws?token={owner['access_token']}"):
        assert _gauge(client.get("/metrics").text, "app") == before + 1
    deadline = time.time() + 5
    while _gauge(client.get("/metrics").text, "app") != before and time.time() < deadline:
        time.sleep(0.05)
    assert _gauge(client.get("/metrics").text, "app") == before


class _Capture:
    def __init__(self) -> None:
        self.exceptions: list[tuple[BaseException, dict[str, Any]]] = []
        self.messages: list[tuple[str, dict[str, Any]]] = []

    def capture_exception(self, exc: BaseException, context: dict[str, Any]) -> None:
        self.exceptions.append((exc, context))

    def capture_message(self, message: str, context: dict[str, Any]) -> None:
        self.messages.append((message, context))


@pytest.fixture
def reporter() -> Iterator[_Capture]:
    capture = _Capture()
    register_error_reporter(capture)
    yield capture
    clear_error_reporters()


def test_unhandled_errors_reach_the_error_tracker(settings: Settings, reporter: _Capture) -> None:
    from app.main import create_app

    app = create_app(settings)

    @app.get("/api/__boom")
    async def boom() -> None:
        raise RuntimeError("kaboom")

    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/api/__boom")
    assert r.status_code == 500 and r.json()["error"]["code"] == "internal_error"
    assert "kaboom" not in r.text  # never leaked to the client
    errors = [exc for exc, _ in reporter.exceptions if isinstance(exc, RuntimeError)]
    assert errors and str(errors[0]) == "kaboom"
    context = next(ctx for exc, ctx in reporter.exceptions if exc is errors[0])
    assert context["request_id"] == r.headers["x-request-id"]


def test_browser_errors_are_reported_without_secrets(client: TestClient, reporter: _Capture) -> None:
    r = client.post(
        "/api/client-errors",
        json={
            "kind": "error",
            "message": "TypeError: x is undefined at /reset-password?token=abc123",
            "page": "/reset-password?token=abc123",
            "source": "https://app.example.com/assets/index.js?v=1",
            "stack": "at f (index.js:1:2)",
            "release": "0.1.0",
        },
    )
    assert r.status_code == 202
    message, context = reporter.messages[-1]
    assert "abc123" not in message and "token=[redacted]" in message
    assert context["page"] == "/reset-password" and context["source"].endswith("index.js")
    assert 'workpulse_client_errors_total{kind="error"}' in client.get("/metrics").text


def test_browser_error_reports_are_validated_and_rate_limited(settings: Settings) -> None:
    from app.main import create_app

    assert client_error_limit(settings) > 0
    app = create_app(settings.model_copy(update={"rate_limits_enabled": True, "client_errors_per_hour": 3}))
    with TestClient(app) as c:
        assert (
            c.post("/api/client-errors", json={"kind": "nope", "message": "m", "page": "/"}).status_code
            == 422
        )
        too_long = {"kind": "error", "message": "m" * 1001, "page": "/"}
        assert c.post("/api/client-errors", json=too_long).status_code == 422
        statuses = [
            c.post("/api/client-errors", json={"kind": "error", "message": f"m{i}", "page": "/"}).status_code
            for i in range(5)
        ]
    assert statuses[:3] == [202, 202, 202] and statuses[3:] == [429, 429]


def client_error_limit(settings: Settings) -> int:
    return settings.client_errors_per_hour


def test_worker_health_check_follows_the_heartbeat(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from app import worker

    beat = tmp_path / "alive"
    monkeypatch.setattr(worker, "HEARTBEAT_FILE", beat)
    assert worker.check() == 1  # never started
    beat.write_text(str(time.time()))
    assert worker.check() == 0
    beat.write_text(str(time.time() - worker.HEARTBEAT_STALE_SECONDS - 1))
    assert worker.check() == 1  # stuck or stopped


def test_browsers_authenticate_websockets_without_tokens_in_urls(client: TestClient) -> None:
    owner = register(client)
    token = owner["access_token"]
    with client.websocket_connect("/api/ws", subprotocols=["workpulse.v1", f"bearer.{token}"]) as sock:
        assert sock.accepted_subprotocol == "workpulse.v1"  # the token itself is never echoed
        assert sock.receive_json()["type"] == "connection.ready"
    bad = ["workpulse.v1", "bearer.not-a-token"]
    with pytest.raises(WebSocketDisconnect), client.websocket_connect("/api/ws", subprotocols=bad) as sock:
        sock.receive_json()
    # Older clients that still use ?token= keep working.
    with client.websocket_connect(f"/api/ws?token={token}") as sock:
        assert sock.receive_json()["type"] == "connection.ready"
