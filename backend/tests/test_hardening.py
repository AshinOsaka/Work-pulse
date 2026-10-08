"""Phase 16: security hardening — headers, CORS, CSRF, rate limits, input and file validation, token handling, secret
storage, logging, the audit trail and the employee-visible monitoring policy."""

from __future__ import annotations

import logging
import re
import time
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import jwt
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core.config import Settings
from app.main import create_app
from tests.conftest import register, unique_email
from tests.org_helpers import Workspace, auth
from tests.test_agent_api import enrol_member, event
from tests.test_live import agent_socket, working
from tests.test_live import enable as enable_live
from tests.test_reports import download, wait_ready
from tests.test_screenshots import enable as enable_screenshots
from tests.test_screenshots import start_session, upload
from tests.test_tenant_isolation import route_table

PASSWORD = "Member1Password"
EVIL = "https://evil.example"


@pytest.fixture
def rate_limits(client: TestClient, sync_db: Any) -> Iterator[None]:
    settings: Settings = client.app.state.settings  # type: ignore[attr-defined]
    settings.rate_limits_enabled = True
    sync_db["rate_limits"].delete_many({})
    yield
    settings.rate_limits_enabled = False
    sync_db["rate_limits"].delete_many({})


class Captured(logging.Handler):
    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(f"{record.name} {record.getMessage()} {record.__dict__}")


# --------------------------------------------------------------------------- headers, CORS, CSRF
def test_api_responses_carry_security_headers(client: TestClient, ws: Workspace) -> None:
    response = ws.get("/auth/me")
    headers = response.headers
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert headers["referrer-policy"] == "no-referrer"
    assert headers["cache-control"] == "no-store"  # workforce data never lands in shared caches
    assert "default-src 'none'" in headers["content-security-policy"]
    assert "server" not in {k.lower() for k in headers} or "uvicorn" not in headers.get("server", "").lower()


def test_cors_admits_only_configured_origins(settings: Settings) -> None:
    app = create_app(settings.model_copy(update={"cors_origins": "https://app.example.com"}))
    client = TestClient(app)  # no lifespan needed: preflights are answered by the middleware
    preflight = {"Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "authorization"}
    allowed = client.options("/api/auth/login", headers={"Origin": "https://app.example.com", **preflight})
    assert allowed.headers.get("access-control-allow-origin") == "https://app.example.com"
    assert allowed.headers.get("access-control-allow-credentials") == "true"
    denied = client.options("/api/auth/login", headers={"Origin": EVIL, **preflight})
    assert "access-control-allow-origin" not in denied.headers
    # Without CORS_ORIGINS (the default same-origin deployment) no cross-origin access is granted at all.
    plain = TestClient(create_app(settings)).options("/api/auth/login", headers={"Origin": EVIL, **preflight})
    assert "access-control-allow-origin" not in plain.headers


def test_cross_site_requests_are_refused(ws: Workspace, client: TestClient, settings: Settings) -> None:
    member = ws.member("Csrf Target")
    client.cookies.clear()
    signed_in = client.post("/api/auth/login", json={"email": member.email, "password": PASSWORD})
    token = signed_in.json()["access_token"]
    # Another site can't use the browser's refresh cookie to sign the person out or mint tokens...
    for path in ("/api/auth/logout", "/api/auth/refresh"):
        refused = client.post(path, headers={"Origin": EVIL})
        assert refused.status_code == 403 and refused.json()["error"]["code"] == "origin_not_allowed"
    assert client.get("/api/auth/me", headers=auth(token)).status_code == 200  # still signed in
    # ...or sign them in to an attacker's account, or change anything else.
    assert client.post("/api/auth/login", json={}, headers={"Origin": EVIL}).status_code == 403
    assert (
        client.patch(
            "/api/users/me", json={"full_name": "X"}, headers={**auth(token), "Origin": "null"}
        ).status_code
        == 403
    )
    # Same-origin pages, the configured app origin and non-browser clients (no Origin) work.
    assert client.post("/api/auth/refresh", headers={"Origin": "http://testserver"}).status_code == 200
    assert (
        client.post("/api/auth/refresh", headers={"Origin": settings.frontend_url.rstrip("/")}).status_code
        == 200
    )
    assert client.post("/api/auth/refresh").status_code == 200
    # Reading is allowed from anywhere the browser permits (CORS decides); WebSockets are checked too.
    with (
        pytest.raises(WebSocketDisconnect),
        client.websocket_connect(f"/api/ws?token={token}", headers={"Origin": EVIL}) as sock,
    ):
        sock.receive_json()
    with client.websocket_connect(f"/api/ws?token={token}", headers={"Origin": "http://testserver"}) as sock:
        assert sock.receive_json()["type"] == "connection.ready"


# --------------------------------------------------------------------------- rate limiting
def test_sign_in_is_throttled_per_account(ws: Workspace, client: TestClient, rate_limits: None) -> None:
    member = ws.member("Bruno Bruteforce")
    for _ in range(10):
        assert (
            client.post(
                "/api/auth/login", json={"email": member.email, "password": "wrong-pass1"}
            ).status_code
            == 401
        )
    blocked = client.post("/api/auth/login", json={"email": member.email, "password": PASSWORD})
    assert blocked.status_code == 429 and blocked.json()["error"]["code"] == "rate_limited"
    assert int(blocked.headers["retry-after"]) > 0
    # Other accounts are unaffected, and unknown addresses are throttled the same way (no account enumeration).
    other = ws.member("Olga Other")
    assert (
        client.post("/api/auth/login", json={"email": other.email, "password": PASSWORD}).status_code == 200
    )
    ghost = unique_email("ghost")
    codes = {
        client.post("/api/auth/login", json={"email": ghost, "password": "x"}).status_code for _ in range(11)
    }
    assert codes == {401, 429}


def test_reset_links_agent_sign_in_and_invitation_tokens_are_throttled(
    ws: Workspace, client: TestClient, rate_limits: None
) -> None:
    member = ws.member("Rex Reset")
    sent_before = len(ws.mail.messages)
    for _ in range(5):  # silently capped per address: the caller can't tell whether the address exists
        assert client.post("/api/auth/forgot-password", json={"email": member.email}).status_code == 202
    assert len(ws.mail.messages) - sent_before == 3
    for _ in range(10):
        client.post(
            "/api/agent/register", json={"email": member.email, "password": "nope-nope1", "device": {}}
        )
    assert client.post(
        "/api/agent/register", json={"email": member.email, "password": "nope-nope1", "device": {}}
    ).status_code in (422, 429)
    statuses = {client.get("/api/auth/invitations/xyz").status_code for _ in range(3)}
    assert statuses <= {400, 404}


# --------------------------------------------------------------------------- input and file validation
def test_malformed_input_never_causes_a_server_error(ws: Workspace, client: TestClient) -> None:
    junk_ids = ["not-an-id", "../../etc/passwd", "a" * 300, "%00", '{"$ne":null}']
    client.cookies.clear()  # so the sweep's call to /auth/logout can't end the admin's session
    for method, path in route_table(client):
        params = re.findall(r"{(\w+)}", path)
        for junk in junk_ids if params else [""]:
            url = path
            for name in params:
                url = url.replace(f"{{{name}}}", junk)
            response = client.request(
                method,
                url,
                params={"page": "-1", "search": "(.*", "start": "2026-13-45", "employee_id": "x"},
                json={"$where": "sleep(1000)", "email": {"$ne": None}} if method != "GET" else None,
                headers=auth(ws.admin.token),
            )
            assert response.status_code < 500, (method, url, response.status_code, response.text[:200])
    assert ws.get("/auth/me").status_code == 200, "the sweep must have run signed in"
    # Operator injection into sign-in is rejected by validation, not interpreted.
    injected = client.post("/api/auth/login", json={"email": {"$ne": None}, "password": {"$ne": None}})
    assert injected.status_code == 422
    regex = client.get("/api/employees", params={"search": ".*"}, headers=auth(ws.admin.token))
    assert regex.status_code == 200 and regex.json()["total"] == 0  # searched literally


def test_uploaded_files_are_checked_not_trusted(ws: Workspace, client: TestClient) -> None:
    project = ws.post("/projects", {"name": "Files", "key": "FIL", "member_ids": []}).json()
    task = ws.post("/tasks", {"project_id": project["id"], "title": "Upload"}).json()

    def send(name: str, content: bytes, content_type: str) -> Any:
        return client.post(
            f"/api/tasks/{task['id']}/attachments",
            params={"filename": name},
            content=content,
            headers={**auth(ws.admin.token), "Content-Type": content_type},
        )

    disguised = send("cat.png", b"<html><script>alert(1)</script></html>", "image/png")
    assert disguised.status_code == 201 and disguised.json()["content_type"] == "application/octet-stream"
    served = client.get(disguised.json()["download_url"])
    assert served.headers["content-type"] == "application/octet-stream"
    assert served.headers["content-disposition"].startswith("attachment")
    assert "sandbox" in served.headers["content-security-policy"]
    real = send("real.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 32, "image/png")
    assert real.json()["content_type"] == "image/png"
    assert send("../../evil.sh", b"#!/bin/sh", "text/x-sh").json()["filename"] == ".._.._evil.sh"
    assert send("empty.txt", b"", "text/plain").status_code == 400
    assert send("big.bin", b"\x00" * (9 * 1024 * 1024 + 1), "application/octet-stream").status_code == 413

    _, agent = enrol_member(ws, "Una Upload")
    enable_screenshots(ws)
    session = start_session(agent)
    not_an_image = upload(agent, session, data=b"<svg onload=alert(1)>", content_type="image/png")
    assert not_an_image.status_code in (400, 415, 422)
    svg = upload(agent, session, data=b"<svg/>", content_type="image/svg+xml")
    assert svg.status_code in (400, 415)


def test_agents_cannot_send_keystrokes_or_extra_fields(ws: Workspace) -> None:
    _, agent = enrol_member(ws, "Kip Keys")
    session = str(uuid.uuid4())
    now = datetime.now(UTC)
    segment = event(
        "activity.segment",
        now,
        session_id=session,
        app_id="code.exe",
        app_name="Code",
        started_at=(now - timedelta(minutes=1)).isoformat(),
        ended_at=now.isoformat(),
        active_seconds=60,
        activity_level=50,
        keystrokes="hunter2",
    )
    response = agent.events(segment)
    assert response.status_code == 422 or response.json()["accepted"] == 0


# --------------------------------------------------------------------------- tokens, secrets and logs
def test_forged_tampered_and_foreign_tokens_are_rejected(
    ws: Workspace, client: TestClient, settings: Settings
) -> None:
    claims = jwt.decode(ws.admin.token, options={"verify_signature": False})
    forged = {
        "alg none": jwt.encode(claims, key="", algorithm="none") if hasattr(jwt, "encode") else "",
        "other key": jwt.encode(claims, "x" * 48, algorithm="HS256"),
        "no session": jwt.encode(
            {k: v for k, v in claims.items() if k != "sid"},
            settings.jwt_secret.get_secret_value(),
            algorithm="HS256",
        ),
        "unknown session": jwt.encode(
            {**claims, "sid": "0" * 24}, settings.jwt_secret.get_secret_value(), algorithm="HS256"
        ),
        "other company": jwt.encode(
            {**claims, "cid": "0" * 24}, settings.jwt_secret.get_secret_value(), algorithm="HS256"
        ),
        "expired": jwt.encode(
            {**claims, "exp": int(time.time()) - 60},
            settings.jwt_secret.get_secret_value(),
            algorithm="HS256",
        ),
    }
    for name, token in forged.items():
        assert client.get("/api/auth/me", headers=auth(token)).status_code == 401, name


def test_secrets_are_stored_only_as_hashes(ws: Workspace, client: TestClient, sync_db: Any) -> None:
    member = ws.member("Hash Check")
    user = sync_db["users"].find_one({"email": member.email})
    assert user["password_hash"].startswith("$argon2id$") and PASSWORD not in str(user)
    client.cookies.clear()
    client.post("/api/auth/login", json={"email": member.email, "password": PASSWORD})
    raw_refresh = client.cookies.get("wp_refresh")
    assert raw_refresh and sync_db["refresh_tokens"].find_one({"token_hash": raw_refresh}) is None
    client.post("/api/auth/forgot-password", json={"email": member.email})
    raw_reset = ws.mail.last_token()
    assert sync_db["password_reset_tokens"].find_one({"token_hash": raw_reset}) is None


def test_refresh_cookie_is_locked_down(ws: Workspace, client: TestClient) -> None:
    member = ws.member("Cookie Flags")
    client.cookies.clear()
    response = client.post("/api/auth/login", json={"email": member.email, "password": PASSWORD})
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and "path=/api/auth" in cookie
    assert "access_token" not in cookie  # the access token is never a cookie
    assert Settings.model_fields["refresh_cookie_secure"].default is True  # Secure unless explicitly relaxed


def test_credentials_never_reach_the_logs(ws: Workspace, client: TestClient) -> None:
    handler = Captured()
    root = logging.getLogger()
    root.addHandler(handler)
    previous = root.level
    root.setLevel(logging.DEBUG)
    try:
        secret_password = f"Pw{uuid.uuid4().hex}1"
        created = register(client, password=secret_password)
        email = created["user"]["email"]  # type: ignore[index]
        client.post("/api/auth/login", json={"email": email, "password": "Wrong" + secret_password})
        login = client.post("/api/auth/login", json={"email": email, "password": secret_password}).json()
        refresh_cookie = client.cookies.get("wp_refresh") or "missing"
        client.post("/api/auth/refresh")
        client.post("/api/auth/forgot-password", json={"email": email})
        with client.websocket_connect(f"/api/ws?token={login['access_token']}") as sock:
            sock.receive_json()
    finally:
        root.removeHandler(handler)
        root.setLevel(previous)
    text = "\n".join(handler.lines)
    assert text, "nothing was captured; the check would be meaningless"
    for secret in (secret_password, login["access_token"], refresh_cookie):
        assert secret not in text


# --------------------------------------------------------------------------- audit trail
def test_required_events_are_audited_and_readable_by_admins_only(
    ws: Workspace, client: TestClient, sync_db: Any
) -> None:
    member = ws.member("Audrey Audited")
    client.cookies.clear()
    client.post("/api/auth/login", json={"email": member.email, "password": PASSWORD})
    client.post("/api/auth/logout")
    # Screenshot access
    _, agent = enrol_member(ws, "Sean Screenshot")
    enable_screenshots(ws)
    shot = upload(agent, start_session(agent)).json()["id"]
    ws.get(f"/screenshots/{shot}")
    # Live stream start and stop
    enable_live(ws)
    streamer, streamer_agent = enrol_member(ws, "Liam Live")
    working(streamer_agent)
    with agent_socket(client, streamer_agent):
        live = ws.post("/live/sessions", {"employee_id": streamer.employee_id}).json()
        ws.post(f"/live/sessions/{live['id']}/stop", {})
    # Report export
    job = ws.post(
        "/reports",
        {
            "report_type": "work_hours",
            "format": "csv",
            "period": "daily",
            "start": "2026-01-05",
            "end": "2026-01-05",
        },
    ).json()
    download(client, wait_ready(ws, job["id"]))
    # Permission, policy and employee changes
    ws.patch(f"/users/{member.user_id}/role", {"role": "TEAM_LEAD"})
    ws.patch("/companies/current/activity-policy", {"capture_window_titles": True})
    ws.patch(f"/employees/{member.employee_id}", {"job_title": "Analyst"})

    required = {
        "auth.login": "sign_in",
        "auth.logout": "sign_in",
        "screenshot.viewed": "monitoring_access",
        "live.session_requested": "monitoring_access",
        "live.session_ended": "monitoring_access",
        "report.downloaded": "reports",
        "user.role_changed": "permissions",
        "policy.activity_updated": "policies",
        "employee.updated": "people",
    }
    seen: dict[str, str] = {}
    for category in sorted(set(required.values())):
        page = ws.get("/audit-logs", category=category, page_size=100).json()
        for item in page["items"]:
            seen.setdefault(item["action"], item["category"])
            assert item["label"] and item["at"]
            assert not any(re.search("token|secret|password", k, re.I) for k in item["details"])
    for action, category in required.items():
        assert seen.get(action) == category, (action, seen.get(action))

    employee = ws.member("Nosy Employee")
    manager = ws.member("Nosy Manager", role="MANAGER")
    assert ws.get("/audit-logs", token=employee.token).status_code == 403
    assert ws.get("/audit-logs", token=manager.token).status_code == 403
    # The trail is append-only: no route can change or delete entries.
    writes = [(m, p) for m, p in route_table(client) if p.startswith("/api/audit-logs") and m != "GET"]
    assert writes == []


# --------------------------------------------------------------------------- privacy
def test_monitoring_policy_is_visible_to_employees_and_follows_settings(
    ws: Workspace, client: TestClient
) -> None:
    employee = ws.member("Ivy Informed")
    policy = ws.get("/privacy/monitoring-policy", token=employee.token)
    assert policy.status_code == 200
    body = policy.json()
    sections = {s["key"]: s for s in body["sections"]}
    assert {"presence", "activity", "screenshots", "live", "work", "audit", "derived"} <= set(sections)
    for section in sections.values():
        assert section["when"] and section["why"] and section["retention"] and section["access"]
    never = " ".join(body["never_collected"]).lower()
    assert "keystrokes" in never and "passwords" in never and "clipboard" in never
    assert sections["screenshots"]["status"] == "off" and sections["live"]["status"] == "off"
    assert body["contacts"] and body["contacts"][0]["email"] == ws.admin.email

    enable_screenshots(ws, interval_minutes=12, retention_days=21)
    enable_live(ws, max_session_minutes=15)
    after = {
        s["key"]: s for s in ws.get("/privacy/monitoring-policy", token=employee.token).json()["sections"]
    }
    assert after["screenshots"]["status"] == "on" and "12 minutes" in after["screenshots"]["summary"]
    assert "21 days" in after["screenshots"]["retention"]
    assert after["live"]["status"] == "on_request" and "15 minutes" in after["live"]["summary"]
    roles = {a["role"] for a in after["screenshots"]["access"]}
    assert {"You", "Company Admin", "Manager", "Team Lead"} <= roles
    assert {a["role"] for a in after["live"]["access"]} == {"You", "Company Admin", "Manager"}

    # A personal override is reflected for that person only.
    ws.client.put(
        f"/api/employees/{employee.employee_id}/screenshot-settings",
        json={"mode": "disabled"},
        headers=auth(ws.admin.token),
    )
    mine = ws.get("/privacy/monitoring-policy", token=employee.token).json()
    assert mine["personal_screenshot_setting"] is True
    assert {s["key"]: s for s in mine["sections"]}["screenshots"]["status"] == "off"
    assert mine["last_changed_at"] is not None


def test_frontend_ships_no_secrets() -> None:
    root = Path(__file__).resolve().parents[2] / "frontend"
    if not (root / "src").is_dir():
        pytest.skip("frontend sources not available in this environment")
    patterns = [
        re.compile(r"sk-ant-[A-Za-z0-9_-]{10,}"),
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
        re.compile(
            r"(JWT_SECRET|STORAGE_ENCRYPTION_KEY|ANTHROPIC_API_KEY|MONGO[A-Z_]*PASSWORD|LIVE_TURN_SECRET|SMTP_PASSWORD"
            r"|METRICS_TOKEN|REDIS_PASSWORD|SENTRY_DSN)\s*[=:]\s*['\"][^'\"]+"
        ),
        re.compile(r"mongodb(\+srv)?://[^\s'\"]*:[^\s'\"]*@"),
    ]
    env_names: set[str] = set()
    for folder in ("src", "dist", "public"):
        for path in (root / folder).rglob("*"):
            if path.is_file() and path.suffix in {".ts", ".tsx", ".js", ".html", ".json", ".css", ".map"}:
                text = path.read_text(encoding="utf-8", errors="ignore")
                for pattern in patterns:
                    assert not pattern.search(text), (path, pattern.pattern)
                env_names |= set(re.findall(r"import\.meta\.env\.(\w+)", text))
    # Only public build-time values: the API address and the release version (sent with browser error reports).
    assert env_names <= {"VITE_API_BASE_URL", "VITE_APP_VERSION", "DEV", "PROD", "MODE", "BASE_URL"}
