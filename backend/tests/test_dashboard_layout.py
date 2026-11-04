"""A person's own dashboard arrangement: saved on their account, returned with the session, resettable."""

from __future__ import annotations

from tests.org_helpers import Workspace
from tests.test_agent_api import enrol_member


def test_layout_is_saved_returned_and_reset(ws: Workspace) -> None:
    assert ws.get("/auth/me").json()["user"]["dashboard_layout"] is None  # standard layout until changed

    body = {
        "widgets": [
            {"id": "work_hours", "area": "side", "title": "  Hours this week  "},
            {"id": "connected_now", "area": "top"},
        ]
    }
    saved = ws.put("/users/me/dashboard-layout", body)
    assert saved.status_code == 200, saved.text
    assert saved.json()["dashboard_layout"] == [
        {"id": "work_hours", "area": "side", "title": "Hours this week"},  # trimmed
        {"id": "connected_now", "area": "top", "title": None},
    ]
    assert (
        ws.get("/auth/me").json()["user"]["dashboard_layout"][0]["id"] == "work_hours"
    )  # kept on the account

    reset = ws.delete("/users/me/dashboard-layout")
    assert reset.status_code == 200 and reset.json()["dashboard_layout"] is None


def test_layout_is_validated(ws: Workspace) -> None:
    def put(widgets: list[dict[str, object]]) -> int:
        return int(ws.put("/users/me/dashboard-layout", {"widgets": widgets}).status_code)

    assert put([{"id": "work_hours", "area": "left"}]) == 422  # only top / main / side
    assert put([{"id": "Bad Id!", "area": "main"}]) == 422
    assert put([{"id": "work_hours"}, {"id": "work_hours"}]) == 422  # each widget once
    assert put([{"id": "work_hours", "title": "x" * 61}]) == 422
    assert put([{"id": f"w{i}"} for i in range(31)]) == 422
    assert put([]) == 200  # an empty dashboard is allowed


def test_each_person_has_their_own_layout(ws: Workspace) -> None:
    member, _ = enrol_member(ws, "Lena Layout", role="MANAGER")
    ws.put("/users/me/dashboard-layout", {"widgets": [{"id": "attendance", "area": "main"}]})

    assert ws.get("/auth/me", token=member.token).json()["user"]["dashboard_layout"] is None
    mine = ws.put(
        "/users/me/dashboard-layout", {"widgets": [{"id": "trend", "area": "side"}]}, token=member.token
    )
    assert mine.json()["dashboard_layout"] == [{"id": "trend", "area": "side", "title": None}]
    assert ws.get("/auth/me").json()["user"]["dashboard_layout"][0]["id"] == "attendance"  # admin's untouched
