"""The public privacy facts: readable without signing in, and never carrying workspace data."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.services.privacy_policy import NEVER_COLLECTED
from tests.org_helpers import Workspace


def test_public_privacy_facts_need_no_sign_in_and_hold_no_workspace_data(ws: Workspace, client: TestClient) -> None:
    response = client.get("/api/privacy/public")  # no Authorization header
    assert response.status_code == 200
    body = response.json()
    assert body["never_collected"] == NEVER_COLLECTED
    assert body["detailed_activity_days"] == 180
    assert body["raw_event_days"] == 90
    assert body["default_screenshot_days"] == 30
    assert body["report_file_days"] == 7
    # Nothing about any workspace, person or admin is exposed.
    assert set(body) == {
        "never_collected",
        "detailed_activity_days",
        "raw_event_days",
        "default_screenshot_days",
        "report_file_days",
        "contact_email",
    }
    assert ws.admin.email not in response.text
