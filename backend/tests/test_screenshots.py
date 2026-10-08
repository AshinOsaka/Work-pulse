"""Phase 6: screenshot monitoring — policy, uploads, private delivery, access control, audit, retention."""

from __future__ import annotations

import asyncio
import io
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from bson import ObjectId
from fastapi.testclient import TestClient
from PIL import Image
from pymongo import AsyncMongoClient

from app.models.company import Company
from app.models.organization import Employee
from app.repositories.screenshot import ScreenshotRepository
from app.services.retention import purge_expired_screenshots
from app.services.screenshot_policy import effective_policy, in_work_hours
from tests.conftest import register
from tests.org_helpers import Workspace, auth
from tests.test_agent_api import AgentClient, enrol_member, event


def webp(width: int = 1280, height: int = 720, color: tuple[int, int, int] = (40, 90, 200)) -> bytes:
    image = Image.new("RGB", (width, height), color)
    for x in range(0, width, 40):  # some structure, so it is not trivially compressible
        image.paste((250, 250, 250), (x, 0, x + 4, height))
    out = io.BytesIO()
    image.save(out, format="WEBP", quality=60)
    return out.getvalue()


def enable(ws: Workspace, **fields: Any) -> dict[str, Any]:
    response = ws.patch(
        "/companies/current/screenshot-policy", {"enabled": True, "work_hours_only": False, **fields}
    )
    assert response.status_code == 200, response.text
    return response.json()  # type: ignore[no-any-return]


def start_session(agent: AgentClient, minutes_ago: int = 30) -> str:
    session = str(uuid.uuid4())
    agent.events(
        event("session.started", datetime.now(UTC) - timedelta(minutes=minutes_ago), session_id=session)
    )
    return session


def upload(
    agent: AgentClient,
    session: str,
    *,
    at: datetime | None = None,
    data: bytes | None = None,
    shot_id: str | None = None,
    content_type: str = "image/webp",
) -> Any:
    return agent.client.post(
        "/api/agent/screenshots",
        params={
            "id": shot_id or str(uuid.uuid4()),
            "captured_at": (at or datetime.now(UTC)).isoformat(),
            "session_id": session,
        },
        content=data if data is not None else webp(),
        headers={**auth(agent.token), "Content-Type": content_type},
    )


def today() -> str:
    return datetime.now(UTC).date().isoformat()


def fetch(client: TestClient, url: str) -> Any:
    return client.get(url)  # no Authorization header: signed URLs must work (and fail) on their own


# --------------------------------------------------------------------------- policy


def test_policy_is_off_by_default_visible_to_all_and_delivered_to_agents(ws: Workspace) -> None:
    member, agent = enrol_member(ws, "Pia Policy")
    policy = ws.get("/companies/current/screenshot-policy", token=member.token).json()
    assert policy["enabled"] is False and policy["interval_minutes"] == 10 and policy["retention_days"] == 30
    assert (
        ws.patch("/companies/current/screenshot-policy", {"enabled": True}, token=member.token).status_code
        == 403
    )

    enable(ws, interval_minutes=5)
    beat = agent.heartbeat().json()["policy"]["screenshots"]
    assert beat["enabled"] is True and beat["interval_seconds"] == 300 and beat["timezone"] == "UTC"

    assert ws.patch("/companies/current/screenshot-policy", {"interval_minutes": 0}).status_code == 422
    assert ws.patch("/companies/current/screenshot-policy", {"work_start": "25:00"}).status_code == 422
    assert ws.patch("/companies/current/screenshot-policy", {"work_days": [0]}).status_code == 422
    same = ws.patch(
        "/companies/current/screenshot-policy",
        {"work_hours_only": True, "work_start": "09:00", "work_end": "09:00"},
    )
    assert same.status_code == 400 and same.json()["error"]["code"] == "invalid_work_hours"


def test_work_hours_rule() -> None:
    company = Company(name="T", slug="t")
    employee = Employee(company_id=company.id, full_name="E", email="e@example.com", timezone="Europe/Berlin")
    policy = effective_policy(company, employee)
    monday_10_berlin = datetime(2026, 9, 28, 8, 0, tzinfo=UTC)  # 10:00 CEST
    assert in_work_hours(policy, monday_10_berlin)
    assert not in_work_hours(policy, monday_10_berlin + timedelta(hours=9))  # 19:00
    assert not in_work_hours(policy, monday_10_berlin + timedelta(days=5))  # Saturday

    company.screenshot_policy.work_start, company.screenshot_policy.work_end = "22:00", "06:00"
    night = effective_policy(company, employee)
    assert in_work_hours(night, datetime(2026, 9, 28, 21, 0, tzinfo=UTC))  # Mon 23:00
    assert in_work_hours(night, datetime(2026, 9, 29, 2, 0, tzinfo=UTC))  # Tue 04:00, shift began Monday
    assert not in_work_hours(night, datetime(2026, 9, 28, 1, 0, tzinfo=UTC))  # Mon 03:00, Sunday is off


# --------------------------------------------------------------------------- uploads


def test_upload_is_refused_unless_policy_and_session_allow_it(ws: Workspace) -> None:
    _, agent = enrol_member(ws, "Una Upload")
    session = start_session(agent)

    refused = upload(agent, session)
    assert refused.status_code == 403 and refused.json()["error"]["code"] == "screenshots_disabled"

    weekday = datetime.now(UTC).isoweekday()
    ws.patch(
        "/companies/current/screenshot-policy",
        {"enabled": True, "work_hours_only": True, "work_days": [d for d in range(1, 8) if d != weekday]},
    )
    outside = upload(agent, session)
    assert outside.status_code == 403 and outside.json()["error"]["code"] == "outside_work_hours"

    enable(ws)
    unknown = upload(agent, str(uuid.uuid4()))
    assert unknown.status_code == 409 and unknown.json()["error"]["code"] == "unknown_session"

    stale = upload(agent, session, at=datetime.now(UTC) - timedelta(days=8))
    assert stale.status_code == 400

    before = upload(agent, session, at=datetime.now(UTC) - timedelta(hours=2))
    assert before.status_code == 403 and before.json()["error"]["code"] == "outside_session"


def test_upload_validation(ws: Workspace) -> None:
    _, agent = enrol_member(ws, "Val Idate")
    session = start_session(agent)
    enable(ws)

    not_image = upload(agent, session, data=b"RIFF0000WEBPVP8 not really an image")
    assert not_image.status_code == 400 and not_image.json()["error"]["code"] == "invalid_image"
    assert upload(agent, session, content_type="text/html").status_code == 400
    assert upload(agent, session, data=b"x" * 4_100_000).status_code == 413
    assert upload(agent, session, data=webp(8, 8)).status_code == 400  # too small to be a screen

    assert upload(agent, session, at=datetime.now(UTC) - timedelta(minutes=5)).status_code == 200
    too_soon = upload(agent, session, at=datetime.now(UTC) - timedelta(minutes=5, seconds=-3))
    assert too_soon.status_code == 403 and too_soon.json()["error"]["code"] == "too_frequent"

    # PNG is accepted and normalised to WebP.
    png = io.BytesIO()
    Image.new("RGB", (800, 600), (10, 10, 10)).save(png, format="PNG")
    assert upload(agent, session, data=png.getvalue(), content_type="image/png").status_code == 200


def test_upload_stores_encrypted_objects_outside_mongo_and_is_idempotent(
    ws: Workspace, sync_db: Any, storage_dir: str
) -> None:
    member, agent = enrol_member(ws, "Ida Idempotent")
    session = start_session(agent)
    enable(ws)
    shot_id = str(uuid.uuid4())
    image = webp()

    first = upload(agent, session, shot_id=shot_id, data=image)
    assert first.status_code == 200 and first.json()["duplicate"] is False
    again = upload(agent, session, shot_id=shot_id, data=image)
    assert again.json() == {"id": first.json()["id"], "duplicate": True}

    docs = list(sync_db["screenshots"].find({"client_id": shot_id}))
    assert len(docs) == 1
    doc = docs[0]
    assert all(not isinstance(v, bytes) for v in doc.values())  # metadata only, no image bytes
    assert str(doc["company_id"]) in doc["object_key"] and doc["width"] == 1280

    stored = Path(storage_dir, doc["object_key"]).read_bytes()
    assert image not in stored and b"WEBP" not in stored[:64]  # encrypted at rest
    assert Path(storage_dir, doc["thumb_key"]).exists()
    assert doc["expires_at"] - doc["captured_at"] == timedelta(days=30)
    assert member.employee_id == str(doc["employee_id"])


# --------------------------------------------------------------------------- gallery & private delivery


def test_gallery_signed_urls_and_audit(ws: Workspace, client: TestClient, sync_db: Any) -> None:
    member, agent = enrol_member(ws, "Gail Gallery")
    session = start_session(agent)
    enable(ws)
    for minutes in (20, 10):
        assert upload(agent, session, at=datetime.now(UTC) - timedelta(minutes=minutes)).status_code == 200

    page = ws.get("/screenshots", day=today(), employee_id=member.employee_id).json()
    assert [i["employee"]["id"] for i in page["items"]] == [member.employee_id] * 2
    assert page["items"][0]["captured_at"] > page["items"][1]["captured_at"]  # newest first
    thumb_url = page["items"][0]["thumbnail_url"]

    response = fetch(client, thumb_url)
    assert response.status_code == 200 and response.headers["content-type"] == "image/webp"
    assert response.headers["cache-control"].startswith("private")
    assert "sandbox" in response.headers["content-security-policy"]
    assert Image.open(io.BytesIO(response.content)).width <= 480

    # Tampered, expired, re-targeted or unsigned URLs all fail the same way.
    parsed = urlparse(thumb_url)
    query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
    assert fetch(client, parsed.path).status_code == 422
    assert client.get(parsed.path, params={**query, "s": "0" * 64}).status_code == 404
    assert client.get(parsed.path, params={**query, "e": int(query["e"]) + 60}).status_code == 404
    assert client.get(parsed.path.replace("/thumb", "/full"), params=query).status_code == 404
    other_id = page["items"][1]["id"]
    assert client.get(parsed.path.replace(page["items"][0]["id"], other_id), params=query).status_code == 404

    detail = ws.get(f"/screenshots/{page['items'][0]['id']}").json()
    assert detail["device_name"] == "Test laptop" and detail["url_expires_in"] == 300
    full = fetch(client, detail["image_url"])
    assert full.status_code == 200 and Image.open(io.BytesIO(full.content)).size == (1280, 720)

    timeline = ws.get("/screenshots/timeline", day=today(), employee_id=member.employee_id).json()
    assert (
        timeline["total"] == 2
        and len(timeline["captures"]) == 2
        and sum(b["count"] for b in timeline["buckets"]) == 2
    )

    actions = [a["action"] for a in sync_db["audit_logs"].find({"actor_user_id": {"$exists": True}})]
    assert "screenshots.listed" in actions and "screenshot.viewed" in actions
    listed = sync_db["audit_logs"].find_one({"action": "screenshots.listed"}, sort=[("created_at", -1)])
    assert set(listed["metadata"]["ids"]) == {i["id"] for i in page["items"]}


def test_only_authorised_viewers_in_scope(ws: Workspace, client: TestClient) -> None:
    manager = ws.member("Max Manager", role="MANAGER")
    report, report_agent = enrol_member(ws, "Rory Report", manager_employee_id=manager.employee_id)
    outsider, outsider_agent = enrol_member(ws, "Otto Outside")
    enable(ws)
    upload(report_agent, start_session(report_agent))
    upload(outsider_agent, start_session(outsider_agent))
    admin_page = ws.get("/screenshots", day=today()).json()
    outsider_shot = next(i for i in admin_page["items"] if i["employee"]["id"] == outsider.employee_id)

    # Employees can't browse screenshots — not even their own.
    assert ws.get("/screenshots", token=report.token, day=today()).status_code == 403
    assert ws.get(f"/screenshots/{outsider_shot['id']}", token=report.token).status_code == 403

    # Managers: only their reporting line.
    visible = ws.get("/screenshots", token=manager.token, day=today()).json()["items"]
    assert {i["employee"]["id"] for i in visible} == {report.employee_id}
    assert ws.get(f"/screenshots/{outsider_shot['id']}", token=manager.token).status_code == 404

    # A URL signed for the admin can't be replayed under another identity.
    parsed = urlparse(outsider_shot["thumbnail_url"])
    query = {k: v[0] for k, v in parse_qs(parsed.query).items()}
    assert client.get(parsed.path, params={**query, "u": manager.user_id}).status_code == 404

    # Other tenants see nothing.
    rival = str(register(client, company_name="Rival Shots")["access_token"])
    assert ws.get("/screenshots", token=rival, day=today()).json()["items"] == []
    assert ws.get(f"/screenshots/{outsider_shot['id']}", token=rival).status_code == 404

    # Deleting needs policy rights too, and is audited.
    sid = visible[0]["id"]
    assert client.delete(f"/api/screenshots/{sid}", headers=auth(manager.token)).status_code == 403
    assert client.delete(f"/api/screenshots/{sid}", headers=auth(ws.admin.token)).status_code == 204
    assert ws.get(f"/screenshots/{sid}").status_code == 404


def test_employee_override_and_transparency(ws: Workspace) -> None:
    opted_out, out_agent = enrol_member(ws, "Oona Optout")
    opted_in, in_agent = enrol_member(ws, "Ian Optin")
    ws.patch("/companies/current/screenshot-policy", {"work_hours_only": False})

    put = ws.client.put(
        f"/api/employees/{opted_in.employee_id}/screenshot-settings",
        json={"mode": "enabled", "interval_minutes": 3},
        headers=auth(ws.admin.token),
    )
    assert put.status_code == 200 and put.json()["effective"] == put.json()["effective"] | {
        "enabled": True,
        "interval_minutes": 3,
        "source": "employee",
    }
    assert upload(in_agent, start_session(in_agent)).status_code == 200
    assert in_agent.heartbeat().json()["policy"]["screenshots"]["interval_seconds"] == 180

    enable(ws)
    ws.client.put(
        f"/api/employees/{opted_out.employee_id}/screenshot-settings",
        json={"mode": "disabled"},
        headers=auth(ws.admin.token),
    )
    assert upload(out_agent, start_session(out_agent)).json()["error"]["code"] == "screenshots_disabled"
    assert (
        ws.client.put(
            f"/api/employees/{opted_out.employee_id}/screenshot-settings",
            json={"mode": "enabled"},
            headers=auth(opted_out.token),
        ).status_code
        == 403
    )

    # Each person can see exactly how they are monitored.
    in_agent.heartbeat(presence="active", session_id=str(uuid.uuid4()))
    mine = ws.get("/me/monitoring", token=opted_in.token).json()
    assert mine["agent_connected"] is True and mine["session_active"] is True
    assert mine["screenshots"]["enabled"] is True and mine["screenshots"]["in_schedule_now"] is True
    assert mine["screenshots"]["last_captured_at"] is not None and mine["monitoring_active"] is True
    theirs = ws.get("/me/monitoring", token=opted_out.token).json()
    assert theirs["screenshots"]["enabled"] is False
    assert (
        ws.get(f"/employees/{opted_out.employee_id}/screenshot-settings", token=opted_out.token).status_code
        == 200
    )
    assert (
        ws.get(f"/employees/{opted_in.employee_id}/screenshot-settings", token=opted_out.token).status_code
        == 404
    )


def test_retention_change_and_purge(
    ws: Workspace, client: TestClient, sync_db: Any, storage_dir: str
) -> None:
    member, agent = enrol_member(ws, "Reta Retention")
    enable(ws)
    upload(agent, start_session(agent, minutes_ago=600), at=datetime.now(UTC) - timedelta(hours=3))
    doc = sync_db["screenshots"].find_one({"employee_id": ObjectId(member.employee_id)})
    assert doc is not None

    enable(ws, retention_days=7)
    doc = sync_db["screenshots"].find_one({"_id": doc["_id"]})
    assert doc["expires_at"] - doc["captured_at"] == timedelta(days=7)

    sync_db["screenshots"].update_one(
        {"_id": doc["_id"]}, {"$set": {"expires_at": datetime.now(UTC) - timedelta(seconds=1)}}
    )
    app = client.app
    removed = asyncio.run(_purge(app))
    assert removed >= 1
    assert sync_db["screenshots"].find_one({"_id": doc["_id"]}) is None
    assert (
        not Path(storage_dir, doc["object_key"]).exists() and not Path(storage_dir, doc["thumb_key"]).exists()
    )


async def _purge(app: Any) -> int:
    settings = app.state.settings
    mongo: AsyncMongoClient[dict[str, Any]] = AsyncMongoClient(settings.mongodb_url)
    try:
        return int(
            await purge_expired_screenshots(
                ScreenshotRepository(mongo[settings.mongodb_db]), app.state.object_storage
            )
        )
    finally:
        await mongo.close()
