from __future__ import annotations

from typing import Any

from bson import ObjectId
from fastapi.testclient import TestClient

from app.core.security import hash_password
from app.utils.time import utcnow
from tests.conftest import CapturingEmailSender, register, unique_email


def _auth(token: object) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_register_creates_company_and_admin(client: TestClient) -> None:
    body = register(client, company_name="Globex Corporation")
    assert body["user"]["role"] == "COMPANY_ADMIN"  # type: ignore[index]
    assert body["user"]["email_verified"] is False  # type: ignore[index]
    assert body["company"]["slug"].startswith("globex-corporation")  # type: ignore[index]
    assert "USER_MANAGE" in body["permissions"]  # type: ignore[operator]
    assert body["access_token"]
    assert client.cookies.get("wp_refresh")


def test_register_duplicate_email_conflicts(client: TestClient) -> None:
    email = unique_email()
    register(client, email=email)
    response = client.post(
        "/api/auth/register",
        json={
            "company_name": "Other",
            "full_name": "Bob",
            "email": email.upper(),
            "password": "Another1Pass",
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "email_taken"


def test_register_validation_errors(client: TestClient) -> None:
    response = client.post(
        "/api/auth/register",
        json={"company_name": "X", "full_name": "Bob", "email": "not-an-email", "password": "short"},
    )
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    fields = {d["field"] for d in error["details"]}
    assert {"company_name", "email", "password"} <= fields


def test_login_me_and_wrong_password(client: TestClient) -> None:
    created = register(client)
    email = created["user"]["email"]  # type: ignore[index]
    client.cookies.clear()

    bad = client.post("/api/auth/login", json={"email": email, "password": "WrongPassword1"})
    assert bad.status_code == 401
    assert bad.json()["error"]["code"] == "invalid_credentials"

    unknown = client.post("/api/auth/login", json={"email": unique_email(), "password": "WrongPassword1"})
    assert unknown.status_code == 401
    assert unknown.json()["error"]["code"] == "invalid_credentials"

    ok = client.post("/api/auth/login", json={"email": email, "password": created["_password"]})
    assert ok.status_code == 200
    token = ok.json()["access_token"]

    me = client.get("/api/auth/me", headers=_auth(token))
    assert me.status_code == 200
    assert me.json()["user"]["email"] == email
    assert me.json()["user"]["last_login_at"] is not None


def test_protected_routes_require_token(client: TestClient) -> None:
    assert client.get("/api/auth/me").status_code == 401
    response = client.get("/api/auth/me", headers=_auth("garbage"))
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_token"


def test_refresh_rotation_and_reuse_detection(client: TestClient) -> None:
    register(client)
    original = client.cookies.get("wp_refresh")

    first = client.post("/api/auth/refresh")
    assert first.status_code == 200
    rotated = client.cookies.get("wp_refresh")
    assert rotated and rotated != original

    # Replaying the old token is treated as theft and revokes the whole family.
    client.cookies.set("wp_refresh", original, path="/api/auth")  # type: ignore[arg-type]
    replay = client.post("/api/auth/refresh")
    assert replay.status_code == 401
    assert replay.json()["error"]["code"] == "refresh_token_reused"

    client.cookies.set("wp_refresh", rotated, path="/api/auth")
    assert client.post("/api/auth/refresh").status_code == 401


def test_refresh_without_cookie(client: TestClient) -> None:
    response = client.post("/api/auth/refresh")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "missing_refresh_token"


def test_logout_revokes_refresh_token(client: TestClient) -> None:
    register(client)
    token = client.cookies.get("wp_refresh")
    assert client.post("/api/auth/logout").status_code == 204
    client.cookies.set("wp_refresh", token, path="/api/auth")  # type: ignore[arg-type]
    assert client.post("/api/auth/refresh").status_code == 401


def test_password_reset_flow(client: TestClient, email_sender: CapturingEmailSender) -> None:
    created = register(client)
    email = created["user"]["email"]  # type: ignore[index]
    old_refresh = client.cookies.get("wp_refresh")

    # Unknown e-mails get the same response (no enumeration) and send nothing.
    sent_before = len(email_sender.messages)
    unknown = client.post("/api/auth/forgot-password", json={"email": unique_email()})
    assert unknown.status_code == 202
    assert len(email_sender.messages) == sent_before

    assert client.post("/api/auth/forgot-password", json={"email": email}).status_code == 202
    token = email_sender.last_token()

    done = client.post("/api/auth/reset-password", json={"token": token, "password": "BrandNewPass9"})
    assert done.status_code == 200
    again = client.post("/api/auth/reset-password", json={"token": token, "password": "BrandNewPass9"})
    assert again.status_code == 400

    # Existing sessions are revoked after a reset.
    client.cookies.set("wp_refresh", old_refresh, path="/api/auth")  # type: ignore[arg-type]
    assert client.post("/api/auth/refresh").status_code == 401

    login = client.post("/api/auth/login", json={"email": email, "password": "BrandNewPass9"})
    assert login.status_code == 200


def test_email_verification_flow(client: TestClient, email_sender: CapturingEmailSender) -> None:
    created = register(client)
    token = email_sender.last_token()
    access = created["access_token"]

    assert client.post("/api/auth/verify-email", json={"token": "x" * 32}).status_code == 400
    assert client.post("/api/auth/verify-email", json={"token": token}).status_code == 200

    me = client.get("/api/auth/me", headers=_auth(access)).json()
    assert me["user"]["email_verified"] is True
    resend = client.post("/api/auth/resend-verification", headers=_auth(access))
    assert resend.json()["error"]["code"] == "email_already_verified"


def test_change_password(client: TestClient) -> None:
    created = register(client)
    access = created["access_token"]
    wrong = client.post(
        "/api/auth/change-password",
        json={"current_password": "Nope12345678", "new_password": "Changed1Password"},
        headers=_auth(access),
    )
    assert wrong.status_code == 400
    ok = client.post(
        "/api/auth/change-password",
        json={"current_password": created["_password"], "new_password": "Changed1Password"},
        headers=_auth(access),
    )
    assert ok.status_code == 200
    assert ok.json()["access_token"]


def test_profile_update(client: TestClient) -> None:
    access = register(client)["access_token"]
    response = client.patch("/api/users/me", json={"full_name": "Ada Lovelace"}, headers=_auth(access))
    assert response.status_code == 200
    assert response.json()["full_name"] == "Ada Lovelace"


def test_roles_endpoint_requires_user_manage(client: TestClient, sync_db: Any) -> None:
    admin = register(client)
    access = admin["access_token"]
    roles = client.get("/api/roles", headers=_auth(access))
    assert roles.status_code == 200
    assert roles.json()["roles"][0]["key"] == "SUPER_ADMIN"
    assert len(roles.json()["permissions"]) == 12

    # An EMPLOYEE in the same company is forbidden.
    company_id = ObjectId(admin["company"]["id"])  # type: ignore[index]
    employee_email = unique_email("employee")
    sync_db["users"].insert_one(
        {
            "_id": ObjectId(),
            "company_id": company_id,
            "email": employee_email,
            "full_name": "Eve Employee",
            "password_hash": hash_password("Employee1Pass"),
            "role": "EMPLOYEE",
            "status": "active",
            "email_verified": True,
            "created_at": utcnow(),
            "updated_at": utcnow(),
        }
    )
    client.cookies.clear()
    login = client.post("/api/auth/login", json={"email": employee_email, "password": "Employee1Pass"})
    assert login.status_code == 200
    assert login.json()["permissions"] == []
    forbidden = client.get("/api/roles", headers=_auth(login.json()["access_token"]))
    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "insufficient_permissions"


def test_suspended_user_cannot_sign_in(client: TestClient, sync_db: Any) -> None:
    created = register(client)
    sync_db["users"].update_one({"email": created["user"]["email"]}, {"$set": {"status": "suspended"}})  # type: ignore[index]
    access = created["access_token"]
    assert client.get("/api/auth/me", headers=_auth(access)).status_code == 401
    login = client.post(
        "/api/auth/login",
        json={"email": created["user"]["email"], "password": created["_password"]},  # type: ignore[index]
    )
    assert login.status_code == 403
    assert login.json()["error"]["code"] == "account_suspended"
