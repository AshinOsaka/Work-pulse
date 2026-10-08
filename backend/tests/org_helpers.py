"""Shared helpers for organisation-level API tests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.conftest import CapturingEmailSender, register, unique_email


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@dataclass
class Actor:
    token: str
    employee_id: str
    user_id: str
    email: str


@dataclass
class Workspace:
    client: TestClient
    admin: Actor
    mail: CapturingEmailSender

    def post(self, path: str, body: dict[str, Any], token: str | None = None) -> Any:
        return self.client.post(f"/api{path}", json=body, headers=auth(token or self.admin.token))

    def get(self, path: str, token: str | None = None, **params: Any) -> Any:
        return self.client.get(f"/api{path}", params=params, headers=auth(token or self.admin.token))

    def patch(self, path: str, body: dict[str, Any], token: str | None = None) -> Any:
        return self.client.patch(f"/api{path}", json=body, headers=auth(token or self.admin.token))

    def employee(self, name: str, **fields: Any) -> dict[str, Any]:
        response = self.post(
            "/employees", {"full_name": name, "email": unique_email(name.split()[0].lower()), **fields}
        )
        assert response.status_code == 201, response.text
        return response.json()  # type: ignore[no-any-return]

    def department(self, name: str, **fields: Any) -> dict[str, Any]:
        response = self.post("/departments", {"name": name, **fields})
        assert response.status_code == 201, response.text
        return response.json()  # type: ignore[no-any-return]

    def team(self, name: str, **fields: Any) -> dict[str, Any]:
        response = self.post("/teams", {"name": name, **fields})
        assert response.status_code == 201, response.text
        return response.json()  # type: ignore[no-any-return]

    def member(self, name: str, role: str = "EMPLOYEE", **fields: Any) -> Actor:
        """Create an employee, invite them and accept the invitation; returns a signed-in actor."""
        employee = self.employee(name, invite=True, role=role, **fields)
        token = self.mail.last_token()
        accepted = self.client.post(
            "/api/auth/invitations/accept", json={"token": token, "password": "Member1Password"}
        )
        assert accepted.status_code == 200, accepted.text
        body = accepted.json()
        return Actor(body["access_token"], employee["id"], body["user"]["id"], employee["email"])


@pytest.fixture
def ws(client: TestClient, email_sender: CapturingEmailSender) -> Workspace:
    created = register(client, company_name="Org Test Co")
    token = str(created["access_token"])
    email = created["user"]["email"]  # type: ignore[index]
    listing = client.get("/api/employees", params={"search": email}, headers=auth(token)).json()
    return Workspace(
        client,
        Actor(token, listing["items"][0]["id"], created["user"]["id"], email),  # type: ignore[index]
        email_sender,
    )
