"""An admin's change to someone's role or sections reaches that person's open app at once."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.org_helpers import Workspace


def test_role_and_section_changes_are_pushed_to_the_person(ws: Workspace, client: TestClient) -> None:
    member = ws.member("Basith Pushed")
    with client.websocket_connect(f"/api/ws?token={member.token}") as socket:
        assert socket.receive_json()["type"] == "connection.ready"

        changed = ws.client.patch(
            f"/api/users/{member.user_id}/role",
            json={"role": "MANAGER"},
            headers={"Authorization": f"Bearer {ws.admin.token}"},
        )
        assert changed.status_code == 200, changed.text
        assert socket.receive_json()["type"] == "session.changed"
        # The server already applies the new role: the refreshed session says Manager.
        me = ws.get("/auth/me", token=member.token).json()
        assert me["user"]["role"] == "MANAGER"

        hidden = ws.put(f"/employees/{member.employee_id}/access", {"hidden_sections": ["time-claims"]})
        assert hidden.status_code == 200, hidden.text
        assert socket.receive_json()["type"] == "session.changed"
