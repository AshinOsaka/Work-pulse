"""Phase 16: sessions and revocation, two-step verification (TOTP + recovery codes), and their audit trail."""

from __future__ import annotations

import base64
import time
from collections.abc import Iterator
from typing import Any

import pytest
from cryptography.exceptions import InvalidTag
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core import totp
from app.core.config import Settings
from tests.org_helpers import Workspace, auth
from tests.test_agent_api import device_info

PASSWORD = "Member1Password"


def login(client: TestClient, email: str, password: str = PASSWORD, agent: str = "pytest-browser") -> Any:
    return client.post(
        "/api/auth/login", json={"email": email, "password": password}, headers={"User-Agent": agent}
    )


def device(client: TestClient, email: str, agent: str) -> tuple[str, str]:
    """Sign in as a separate browser: returns its access token and refresh cookie (the shared jar is cleared)."""
    client.cookies.clear()
    response = login(client, email, agent=agent)
    assert response.status_code == 200, response.text
    cookie = client.cookies.get("wp_refresh")
    assert cookie
    client.cookies.clear()
    return response.json()["access_token"], cookie


def refresh(client: TestClient, cookie: str) -> Any:
    client.cookies.clear()
    client.cookies.set("wp_refresh", cookie, path="/api/auth")
    return client.post("/api/auth/refresh")


def actions(sync_db: Any, user_id: str) -> list[str]:
    from bson import ObjectId

    return [d["action"] for d in sync_db["audit_logs"].find({"actor_user_id": ObjectId(user_id)})]


def now_code(secret: str, offset: int = 0) -> str:
    return totp.code_at(secret, totp.current_step(time.time()) + offset)


@pytest.fixture
def fast_session_checks(client: TestClient) -> Iterator[None]:
    settings: Settings = client.app.state.settings  # type: ignore[attr-defined]
    previous = settings.session_check_seconds
    settings.session_check_seconds = 0.1
    yield
    settings.session_check_seconds = previous


# --------------------------------------------------------------------------- TOTP primitives
def test_totp_matches_the_rfc_6238_test_vectors() -> None:
    secret = base64.b32encode(b"12345678901234567890").decode()
    for unix_time, expected in [
        (59, "94287082"),
        (1111111109, "07081804"),
        (1111111111, "14050471"),
        (1234567890, "89005924"),
        (2000000000, "69279037"),
    ]:
        assert totp.code_at(secret, unix_time // 30, digits=8) == expected


def test_totp_drift_replay_and_recovery_code_handling() -> None:
    secret = totp.new_secret()
    now = 1_700_000_000.0
    step = totp.current_step(now)
    assert totp.matching_step(secret, totp.code_at(secret, step), now) == step
    assert totp.matching_step(secret, totp.code_at(secret, step - 1), now) == step - 1  # 30 s of clock drift
    assert totp.matching_step(secret, totp.code_at(secret, step - 2), now) is None
    assert totp.matching_step(secret, totp.code_at(secret, step), now, last_used_step=step) is None  # replay
    assert totp.matching_step(secret, "12a456", now) is None
    codes = totp.new_recovery_codes()
    assert len(set(codes)) == 10 and all(len(c) == 9 and c[4] == "-" for c in codes)
    assert totp.hash_recovery_code(codes[0].upper().replace("-", " ")) == totp.hash_recovery_code(codes[0])
    key = b"k" * 32
    sealed = totp.encrypt_secret(key, secret, "user-a")
    assert secret not in sealed and totp.decrypt_secret(key, sealed, "user-a") == secret
    with pytest.raises(InvalidTag):  # bound to the account: can't be moved to another user
        totp.decrypt_secret(key, sealed, "user-b")


# --------------------------------------------------------------------------- sessions
def test_sessions_are_listed_and_revocation_is_immediate(
    ws: Workspace, client: TestClient, sync_db: Any
) -> None:
    member = ws.member("Sam Sessions")
    laptop_token, laptop_cookie = device(
        client, member.email, "Mozilla/5.0 (Windows NT 10.0) Chrome/130.0 Safari/537.36"
    )
    phone_token, phone_cookie = device(
        client, member.email, "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0) Safari/604.1"
    )

    sessions = client.get("/api/auth/sessions", headers=auth(laptop_token)).json()
    current = [s for s in sessions if s["current"]]
    assert len(current) == 1 and current[0]["device"] == "Chrome on Windows"
    assert any(s["device"] == "Safari on iOS" and not s["current"] for s in sessions)

    # Sign out everywhere else: the phone's access token stops working at once, not when it expires.
    revoked = client.post("/api/auth/sessions/revoke-others", headers=auth(laptop_token)).json()
    assert revoked["revoked"] >= 2  # the phone and the invitation sign-in
    denied = client.get("/api/auth/me", headers=auth(phone_token))
    assert denied.status_code == 401 and denied.json()["error"]["code"] == "session_revoked"
    assert refresh(client, phone_cookie).status_code == 401  # its refresh cookie is dead too
    assert client.get("/api/auth/me", headers=auth(laptop_token)).status_code == 200

    # Refresh keeps the same session; signing it out by id ends it.
    refreshed = refresh(client, laptop_cookie).json()["access_token"]
    (only,) = client.get("/api/auth/sessions", headers=auth(refreshed)).json()
    assert only["current"] and only["id"] == current[0]["id"]
    assert client.delete(f"/api/auth/sessions/{only['id']}", headers=auth(refreshed)).status_code == 204
    assert client.get("/api/auth/me", headers=auth(refreshed)).status_code == 401
    assert {"auth.login", "auth.sessions_revoked", "auth.session_revoked"} <= set(
        actions(sync_db, member.user_id)
    )


def test_logout_ends_the_session_and_is_audited(ws: Workspace, client: TestClient, sync_db: Any) -> None:
    member = ws.member("Lou Logout")
    client.cookies.clear()
    token = login(client, member.email).json()["access_token"]
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/auth/me", headers=auth(token)).status_code == 401
    assert "auth.logout" in actions(sync_db, member.user_id)


def test_password_change_ends_every_other_session(ws: Workspace, client: TestClient) -> None:
    member = ws.member("Pat Password")
    old, _ = device(client, member.email, "pytest-other-browser")
    changed = client.post(
        "/api/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "Brand2NewPassword"},
        headers=auth(member.token),
    )
    assert changed.status_code == 200
    assert client.get("/api/auth/me", headers=auth(old)).status_code == 401
    assert client.get("/api/auth/me", headers=auth(member.token)).status_code == 401
    assert client.get("/api/auth/me", headers=auth(changed.json()["access_token"])).status_code == 200


def test_admin_can_sign_someone_out_everywhere(ws: Workspace, client: TestClient, sync_db: Any) -> None:
    member = ws.member("Max Lost-Laptop")
    manager = ws.member("Meg Manager", role="MANAGER")
    assert ws.post(f"/users/{member.user_id}/sessions/revoke", {}, token=manager.token).status_code == 403
    revoked = ws.post(f"/users/{member.user_id}/sessions/revoke", {})
    assert revoked.status_code == 200 and revoked.json()["revoked"] >= 1
    assert client.get("/api/auth/me", headers=auth(member.token)).status_code == 401
    assert ws.post(f"/users/{ws.admin.user_id}/sessions/revoke", {}).status_code == 400  # not yourself
    entry = sync_db["audit_logs"].find_one({"action": "user.sessions_revoked", "target_id": member.user_id})
    assert entry is not None


def test_realtime_and_live_sockets_close_when_the_session_ends(
    ws: Workspace, client: TestClient, fast_session_checks: None
) -> None:
    member = ws.member("Wes Socket")
    with client.websocket_connect(f"/api/ws?token={member.token}") as sock:
        assert sock.receive_json()["type"] == "connection.ready"
        assert ws.post(f"/users/{member.user_id}/sessions/revoke", {}).status_code == 200
        with pytest.raises(WebSocketDisconnect) as closed:
            for _ in range(50):
                sock.receive_json()
        assert closed.value.code == 4401


# --------------------------------------------------------------------------- two-step verification
def enable_mfa(client: TestClient, token: str) -> tuple[str, list[str]]:
    assert (
        client.post("/api/auth/mfa/setup", json={"password": "wrong"}, headers=auth(token)).status_code == 400
    )
    setup = client.post("/api/auth/mfa/setup", json={"password": PASSWORD}, headers=auth(token)).json()
    assert setup["uri"].startswith("otpauth://totp/WorkPulse%3A") and setup["qr_svg"].startswith(
        "data:image/svg+xml"
    )
    secret = setup["secret"]
    bad = client.post("/api/auth/mfa/enable", json={"code": "000000"}, headers=auth(token))
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "invalid_mfa_code"
    enabled = client.post("/api/auth/mfa/enable", json={"code": now_code(secret)}, headers=auth(token))
    assert enabled.status_code == 200
    return secret, enabled.json()["codes"]


def test_two_step_sign_in_with_codes_and_recovery_codes(
    ws: Workspace, client: TestClient, sync_db: Any
) -> None:
    member = ws.member("Tia Two-Step")
    secret, recovery = enable_mfa(client, member.token)
    assert len(recovery) == 10
    me = client.get("/api/auth/me", headers=auth(member.token)).json()
    assert me["user"]["mfa_enabled"] is True

    stored = sync_db["users"].find_one({"email": member.email})
    assert secret not in str(stored) and not any(
        code in str(stored) for code in recovery
    )  # encrypted / hashed

    client.cookies.clear()
    first = login(client, member.email)
    body = first.json()
    assert first.status_code == 200 and body["mfa_required"] is True and "access_token" not in body
    assert "set-cookie" not in first.headers  # no session before the second step
    # The challenge is not an access token.
    assert client.get("/api/auth/me", headers=auth(body["challenge"])).status_code == 401

    wrong = client.post("/api/auth/mfa/verify", json={"challenge": body["challenge"], "code": "123456"})
    assert wrong.status_code == 401 and wrong.json()["error"]["code"] == "invalid_mfa_code"
    # The code used to switch it on can't be replayed; the next one works.
    replay = client.post(
        "/api/auth/mfa/verify", json={"challenge": body["challenge"], "code": now_code(secret)}
    )
    assert replay.status_code == 401
    ok = client.post(
        "/api/auth/mfa/verify", json={"challenge": body["challenge"], "code": now_code(secret, 1)}
    )
    assert ok.status_code == 200 and ok.json()["access_token"]
    sessions = client.get("/api/auth/sessions", headers=auth(ok.json()["access_token"])).json()
    assert next(s for s in sessions if s["current"])["mfa"] is True

    # A recovery code works exactly once.
    challenge = login(client, member.email).json()["challenge"]
    used = client.post("/api/auth/mfa/verify", json={"challenge": challenge, "code": recovery[0].upper()})
    assert used.status_code == 200
    again = client.post("/api/auth/mfa/verify", json={"challenge": challenge, "code": recovery[0]})
    assert again.status_code == 401
    trail = actions(sync_db, member.user_id)
    assert {"auth.mfa_enabled", "auth.mfa_failed", "auth.login"} <= set(trail)
    login_entry = sync_db["audit_logs"].find_one(
        {"action": "auth.login", "metadata.second_factor": "recovery_code", "actor_user_id": stored["_id"]}
    )
    assert login_entry is not None


def test_device_sign_in_needs_an_enrolment_code_when_two_step_is_on(
    ws: Workspace, client: TestClient
) -> None:
    member = ws.member("Dev Agent")
    enable_mfa(client, member.token)
    refused = client.post(
        "/api/agent/register", json={"email": member.email, "password": PASSWORD, "device": device_info()}
    )
    assert refused.status_code == 403 and refused.json()["error"]["code"] == "mfa_enrollment_required"


def test_turning_off_resetting_and_regenerating(ws: Workspace, client: TestClient, sync_db: Any) -> None:
    member = ws.member("Ria Reset")
    secret, _ = enable_mfa(client, member.token)
    headers = auth(member.token)
    no_code = client.post(
        "/api/auth/mfa/disable", json={"password": PASSWORD, "code": "000000"}, headers=headers
    )
    assert no_code.status_code == 400
    fresh = client.post(
        "/api/auth/mfa/recovery-codes",
        json={"password": PASSWORD, "code": now_code(secret, 1)},
        headers=headers,
    )
    assert fresh.status_code == 200 and len(fresh.json()["codes"]) == 10
    disabled = client.post(
        "/api/auth/mfa/disable",
        json={"password": PASSWORD, "code": fresh.json()["codes"][0]},
        headers=headers,
    )
    assert disabled.status_code == 204
    assert sync_db["users"].find_one({"email": member.email})["mfa_secret"] is None

    # An administrator can reset it for someone who lost their phone (and it's audited).
    enable_mfa(client, member.token)
    lead = ws.member("Lee Lead", role="TEAM_LEAD")
    assert ws.post(f"/users/{member.user_id}/mfa/reset", {}, token=lead.token).status_code == 403
    reset = ws.post(f"/users/{member.user_id}/mfa/reset", {})
    assert reset.status_code == 200 and reset.json()["mfa_enabled"] is False
    assert sync_db["audit_logs"].find_one({"action": "user.mfa_reset", "target_id": member.user_id})
    client.cookies.clear()
    assert "access_token" in login(client, member.email).json()  # password alone again
