"""Phase 18: duplicate and concurrent requests (double clicks, retries, two tabs) must not create duplicates or
corrupt state. Requests are fired in parallel through the real application."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from bson import ObjectId
from fastapi.testclient import TestClient

from tests.conftest import unique_email
from tests.org_helpers import Workspace, auth
from tests.test_agent_api import enrol_member
from tests.test_live import agent_socket, working
from tests.test_live import enable as enable_live


def together(n: int, call: Callable[[], Any]) -> list[Any]:
    with ThreadPoolExecutor(max_workers=n) as pool:
        return list(pool.map(lambda _: call(), range(n)))


def test_registering_the_same_email_twice_at_once(client: TestClient) -> None:
    email = unique_email("race")
    body = {"company_name": "Race Co", "full_name": "Ray Race", "email": email, "password": "Sup3rSecretPass"}
    statuses = Counter(
        r.status_code for r in together(6, lambda: client.post("/api/auth/register", json=body))
    )
    assert statuses[201] == 1 and statuses[409] == 5, statuses


def test_adding_the_same_employee_twice_at_once(ws: Workspace, client: TestClient, sync_db: Any) -> None:
    email = unique_email("dup")
    statuses = Counter(
        r.status_code
        for r in together(
            5,
            lambda: client.post(
                "/api/employees", json={"full_name": "Dee Dup", "email": email}, headers=auth(ws.admin.token)
            ),
        )
    )
    assert statuses[201] == 1, statuses
    assert sync_db["employees"].count_documents({"email": email}) == 1


def test_an_invitation_can_only_be_accepted_once(ws: Workspace, client: TestClient) -> None:
    ws.employee("Ivy Invite", invite=True)
    token = ws.mail.last_token()
    results = together(
        5,
        lambda: client.post(
            "/api/auth/invitations/accept", json={"token": token, "password": "Member1Password"}
        ),
    )
    assert Counter(r.status_code for r in results)[200] == 1


def test_one_live_session_per_person_even_when_requested_at_once(
    ws: Workspace, client: TestClient, sync_db: Any
) -> None:
    enable_live(ws)
    member, agent = enrol_member(ws, "Lena Live")
    working(agent)
    with agent_socket(client, agent):
        results = together(
            5,
            lambda: client.post(
                "/api/live/sessions", json={"employee_id": member.employee_id}, headers=auth(ws.admin.token)
            ),
        )
        # The same viewer double-clicking gets one and the same session back.
        assert {r.status_code for r in results} == {201}, [r.text for r in results]
        ids = {r.json()["id"] for r in results}
        assert len(ids) == 1
        created = results
        active = sync_db["live_sessions"].count_documents(
            {"employee_id": ObjectId(member.employee_id), "status": {"$ne": "ended"}}
        )
        assert active == 1
        ws.post(f"/live/sessions/{created[0].json()['id']}/stop", {})


def test_marking_notifications_read_twice_is_harmless(ws: Workspace, client: TestClient) -> None:
    results = together(
        4,
        lambda: client.post(
            "/api/notifications/mark", json={"all": True, "read": True}, headers=auth(ws.admin.token)
        ),
    )
    assert {r.status_code for r in results} == {200}
    assert ws.get("/notifications/unread-count").json()["unread"] == 0


def test_many_people_at_once_get_their_own_data(ws: Workspace, client: TestClient) -> None:
    """Concurrent users: each sees exactly their own session and nobody else's."""
    members = [ws.member(f"Concurrent {i}") for i in range(8)]

    def me(token: str) -> Any:
        return client.get("/api/auth/me", headers=auth(token)).json()["user"]["id"]

    with ThreadPoolExecutor(max_workers=8) as pool:
        seen = list(pool.map(me, [m.token for m in members] * 5))
    assert seen == [m.user_id for m in members] * 5


def test_different_viewers_racing_for_one_screen(ws: Workspace, client: TestClient, sync_db: Any) -> None:
    enable_live(ws)
    member, agent = enrol_member(ws, "Rex Raced")
    viewers = [ws.member(f"Viewer {i}", role="COMPANY_ADMIN") for i in range(3)]  # everyone in scope
    working(agent)
    with agent_socket(client, agent), ThreadPoolExecutor(max_workers=4) as pool:
        results = list(
            pool.map(
                lambda v: client.post(
                    "/api/live/sessions", json={"employee_id": member.employee_id}, headers=auth(v.token)
                ),
                [ws.admin, *viewers[:3]],
            )
        )
        statuses = Counter(r.status_code for r in results)
        assert statuses[201] == 1 and statuses[409] == 3, statuses
        assert all(r.json()["error"]["code"] in ("already_live",) for r in results if r.status_code == 409)
        winner = next(r for r in results if r.status_code == 201).json()["id"]
        assert (
            sync_db["live_sessions"].count_documents(
                {"employee_id": ObjectId(member.employee_id), "status": {"$ne": "ended"}}
            )
            == 1
        )
        ws.post(f"/live/sessions/{winner}/stop", {})
