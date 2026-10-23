"""Prod build: on-demand screenshot download requests — queue, package a ZIP, signed requester-bound download."""

from __future__ import annotations

import io
import zipfile
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from tests.org_helpers import Workspace, auth
from tests.test_agent_api import enrol_member
from tests.test_screenshots import enable, start_session, today, upload


def _process(client: TestClient) -> int:
    worker = client.app.state.background.screenshot_requests  # type: ignore[attr-defined]
    return int(client.portal.call(worker.run_pending))  # type: ignore[attr-defined]


def test_a_request_packages_the_days_screenshots_into_a_signed_zip(
    ws: Workspace, client: TestClient
) -> None:
    enable(ws)
    member, agent = enrol_member(ws, "Shona Shots")
    session = start_session(agent, minutes_ago=60)
    # Two captures spaced beyond the 10-minute interval, both earlier today.
    assert upload(agent, session, at=datetime.now(UTC) - timedelta(minutes=40)).status_code == 200
    assert upload(agent, session, at=datetime.now(UTC) - timedelta(minutes=20)).status_code == 200

    raised = ws.post("/screenshots/requests", {"employee_id": member.employee_id, "day": today()})
    assert raised.status_code == 202, raised.text
    assert raised.json()["status"] in {"queued", "preparing"} and raised.json()["download_url"] is None

    assert _process(client) == 1
    row = ws.get("/screenshots/requests").json()[0]
    assert row["status"] == "ready" and row["screenshot_count"] == 2
    assert row["employee_name"] == "Shona Shots" and row["filename"].endswith(".zip")
    assert row["download_url"]

    # The signed, requester-bound URL returns a real ZIP holding the two images and a manifest.
    download = client.get(row["download_url"])
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/zip"
    assert "attachment" in download.headers["content-disposition"]
    archive = zipfile.ZipFile(io.BytesIO(download.content))
    names = archive.namelist()
    assert "manifest.txt" in names and sum(1 for n in names if n.endswith(".webp")) == 2


def test_a_day_with_no_captures_is_reported_empty_not_downloadable(
    ws: Workspace, client: TestClient
) -> None:
    enable(ws)
    member, _agent = enrol_member(ws, "Nora None")
    yesterday = (datetime.now(UTC).date() - timedelta(days=1)).isoformat()
    raised = ws.post("/screenshots/requests", {"employee_id": member.employee_id, "day": yesterday})
    assert raised.status_code == 202
    assert _process(client) == 1
    row = ws.get("/screenshots/requests").json()[0]
    assert row["status"] == "empty" and row["screenshot_count"] == 0 and row["download_url"] is None


def test_requests_are_scoped_permissioned_and_reject_future_dates(
    ws: Workspace, client: TestClient
) -> None:
    enable(ws)
    member, _ = enrol_member(ws, "Vera View")
    # An employee without the View screenshots permission cannot raise a request.
    plain = ws.member("Pablo Plain")
    assert (
        ws.post(
            "/screenshots/requests",
            {"employee_id": member.employee_id, "day": today()},
            token=plain.token,
        ).status_code
        == 403
    )
    # A future date is rejected.
    tomorrow = (datetime.now(UTC).date() + timedelta(days=1)).isoformat()
    assert ws.post("/screenshots/requests", {"employee_id": member.employee_id, "day": tomorrow}).status_code == 400
    # An unknown employee is a 404 (also covers out-of-scope ids).
    assert ws.post("/screenshots/requests", {"employee_id": "012345678901234567890123", "day": today()}).status_code == 404


def test_a_ready_download_can_be_deleted(ws: Workspace, client: TestClient) -> None:
    enable(ws)
    member, agent = enrol_member(ws, "Della Delete")
    session = start_session(agent, minutes_ago=60)
    assert upload(agent, session, at=datetime.now(UTC) - timedelta(minutes=30)).status_code == 200
    rid = ws.post("/screenshots/requests", {"employee_id": member.employee_id, "day": today()}).json()["id"]
    assert _process(client) == 1
    assert ws.client.delete(f"/api/screenshots/requests/{rid}", headers=auth(ws.admin.token)).status_code == 204
    assert ws.get("/screenshots/requests").json() == []
