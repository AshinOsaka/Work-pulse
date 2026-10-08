"""End-to-end against a running WorkPulse API (e.g. the docker compose stack).

    WORKPULSE_E2E_API=http://localhost:8080/api pytest tests/test_e2e.py

Skipped when the variable is not set.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

import httpx
import pytest
from PIL import Image

from app import __version__
from app.activity.foreground import ForegroundApp
from app.agent import Agent
from app.config import AgentConfig
from app.heartbeat.connection import ConnectionState
from app.screenshots.capture import CapturedImage, compress
from app.security.protector import default_protector
from app.sync.api_client import ApiClient
from tests.conftest import FakeIdle, FakeProbe

API = os.environ.get("WORKPULSE_E2E_API")


class SyntheticCapturer:
    """A real, valid WebP of a synthetic desktop, so the server's image validation is exercised."""

    def capture(self) -> CapturedImage | None:
        return compress(Image.new("RGB", (1920, 1080), (238, 240, 246)))


pytestmark = pytest.mark.skipif(not API, reason="set WORKPULSE_E2E_API to run end-to-end tests")
PASSWORD = "E2eAgentTest2026!"


@pytest.fixture
def admin() -> dict[str, Any]:
    assert API
    email = f"agent.e2e.{uuid.uuid4().hex[:8]}@example.com"
    response = httpx.post(
        f"{API}/auth/register",
        json={
            "company_name": f"Agent E2E {uuid.uuid4().hex[:5]}",
            "full_name": "Eddie Endtoend",
            "email": email,
            "password": PASSWORD,
        },
        timeout=20,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return {"email": email, "token": body["access_token"]}


def admin_get(admin: dict[str, Any], path: str, **params: Any) -> Any:
    response = httpx.get(
        f"{API}{path}", params=params, headers={"Authorization": f"Bearer {admin['token']}"}, timeout=20
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_agent_against_real_api(admin: dict[str, Any], tmp_path: Path) -> None:
    assert API
    config = AgentConfig(api_url=API, data_dir=tmp_path / "agent")
    probe = FakeProbe(ForegroundApp("code.exe", "Visual Studio Code", "secret.txt - Notepad"))
    agent = Agent(
        config,
        idle_detector=FakeIdle(),
        protector=default_protector(config.data_dir),
        probe=probe,
        capturer=SyntheticCapturer(),  # never the real screen in tests
    )
    try:
        agent.sign_in(admin["email"], PASSWORD)
        assert agent.snapshot().employee_name == "Eddie Endtoend"
        assert agent.config.heartbeat_interval > 0  # server policy applied

        assert agent.heartbeat.beat()
        assert agent.connection.state == ConnectionState.CONNECTED
        agent.start_session()
        agent.monitor.step()  # one foreground sample
        agent.heartbeat.beat()
        assert agent.sync.flush() >= 2

        presence = admin_get(admin, "/presence")
        row = presence["employees"][0]
        assert row["status"] == "active" and row["connected"] is True
        assert row["device"]["agent_version"] == __version__
        assert presence["counts"]["active"] == 1

        assert row["current_app"] == "Visual Studio Code"

        # Application activity: segments recorded on simulated time, delivered in one batch.
        now = time.time() - 600
        agent.tracker._clock = lambda: now
        session_id = agent.sessions.session_id or ""
        for app in (probe.app, ForegroundApp("chrome.exe", "Google Chrome"), probe.app):
            probe.app = app
            for _ in range(60):
                agent.tracker.sample(session_id, True)
                now += 1
        agent.tracker.close()
        before = len(agent.queue)
        assert before >= 3
        agent.sync.flush()
        assert len(agent.queue) == 0

        employee_id = row["employee"]["id"]
        today = time.strftime("%Y-%m-%d", time.gmtime(now))
        day = admin_get(admin, f"/employees/{employee_id}/activity", day=today)
        assert [s["app_id"] for s in day["segments"]][:3] == ["code.exe", "chrome.exe", "code.exe"]
        assert all(s["window_title"] is None for s in day["segments"])  # titles are off by default
        usage = {a["app_id"]: a["seconds"] for a in day["applications"]}
        assert usage["code.exe"] == pytest.approx(120, abs=3) and usage["chrome.exe"] == pytest.approx(60, abs=2)
        report = admin_get(admin, "/activity/applications", start=today, end=today)
        assert {a["app_id"] for a in report["applications"]} >= {"code.exe", "chrome.exe"}

        # Screenshots: off by default; enabled by policy, captured, uploaded, viewable only via signed URLs.
        assert not agent.snapshot().monitoring_active
        response = httpx.patch(
            f"{API}/companies/current/screenshot-policy",
            json={"enabled": True, "work_hours_only": False, "interval_minutes": 5},
            headers={"Authorization": f"Bearer {admin['token']}"},
            timeout=20,
        )
        assert response.status_code == 200, response.text
        agent.heartbeat.beat()
        assert agent.screenshot_scheduler.policy.enabled
        agent.screenshot_scheduler._clock = lambda: (int(time.time() // 300) * 300) + 299
        agent.screenshot_scheduler.tick(agent.sessions.session_id, True)
        assert agent.snapshot().monitoring_active and len(agent.spool) == 1
        assert agent.uploader.flush() == 1
        shots = admin_get(admin, "/screenshots", day=time.strftime("%Y-%m-%d", time.gmtime()), employee_id=employee_id)[
            "items"
        ]
        assert len(shots) == 1
        detail = admin_get(admin, f"/screenshots/{shots[0]['id']}")
        image = httpx.get(f"{API.removesuffix('/api')}{detail['image_url']}", timeout=20)
        assert image.status_code == 200 and image.headers["content-type"] == "image/webp"
        assert httpx.get(f"{API.removesuffix('/api')}{detail['image_url']}x", timeout=20).status_code == 404

        agent.stop_session()
        agent.sync.flush()
        feed = [item["action"] for item in admin_get(admin, "/activity/feed")]
        assert "work.session_started" in feed and "work.session_stopped" in feed and "device.enrolled" in feed
        assert admin_get(admin, "/presence")["employees"][0]["status"] == "offline"

        # Revoking the device from the web app locks the agent out immediately.
        device_id = agent.auth.credentials.device_id  # type: ignore[union-attr]
        revoke = httpx.post(
            f"{API}/devices/{device_id}/revoke",
            json={},
            headers={"Authorization": f"Bearer {admin['token']}"},
            timeout=20,
        )
        assert revoke.status_code == 200
        agent.auth.invalidate_token()
        agent.heartbeat.beat()
        assert agent.connection.state == ConnectionState.REVOKED
        assert not agent.auth.signed_in
    finally:
        for worker in (agent.heartbeat, agent.sync, agent.monitor):
            worker.stop(timeout=1)


def test_unreachable_api_keeps_events_locally(tmp_path: Path) -> None:
    config = AgentConfig(api_url="http://127.0.0.1:9/api", data_dir=tmp_path / "offline")
    agent = Agent(
        config,
        api=ApiClient(config.api_url, timeout=1, retries=0),
        idle_detector=FakeIdle(),
        capturer=SyntheticCapturer(),
    )
    assert not agent.auth.signed_in
    with pytest.raises(Exception):  # noqa: B017 - any network failure is fine here
        agent.sign_in("nobody@example.com", "irrelevant-123")


def test_live_view_end_to_end(admin: dict[str, Any], tmp_path: Path) -> None:
    """Real agent and API: signalling through nginx and FastAPI, media peer to peer over WebRTC."""
    import asyncio

    from aiortc import RTCPeerConnection, RTCSessionDescription
    from aiortc.mediastreams import MediaStreamError
    from websockets.asyncio.client import connect

    from app.live.track import SyntheticFrameSource

    assert API
    headers = {"Authorization": f"Bearer {admin['token']}"}
    config = AgentConfig(api_url=API, data_dir=tmp_path / "live-agent")
    agent = Agent(
        config,
        idle_detector=FakeIdle(),
        protector=default_protector(config.data_dir),
        capturer=SyntheticCapturer(),
        frame_source=lambda: SyntheticFrameSource(1280, 720),
    )
    try:
        agent.sign_in(admin["email"], PASSWORD)
        agent.start()
        agent.start_session()
        agent.heartbeat.beat()
        assert (
            httpx.patch(f"{API}/companies/current/live-policy", json={"enabled": True}, headers=headers).status_code
            == 200
        )

        deadline = time.monotonic() + 20
        row: dict[str, Any] = {}
        while time.monotonic() < deadline:
            rows = admin_get(admin, "/live/employees")["employees"]
            row = rows[0] if rows else {}
            if row.get("availability") == "available":
                break
            time.sleep(0.3)
        assert row["availability"] == "available" and row["online"] is True

        created = httpx.post(f"{API}/live/sessions", json={"employee_id": row["employee"]["id"]}, headers=headers)
        assert created.status_code == 201, created.text
        sid = created.json()["id"]
        # Same scheme mapping as the agent (https -> wss), so this also runs against a TLS deployment.
        ws_base = "wss://" + API[len("https://") :] if API.startswith("https://") else "ws://" + API[len("http://") :]
        ws_url = ws_base + f"/live/sessions/{sid}/ws?token={admin['token']}"

        async def view() -> tuple[list[tuple[int, int]], dict[str, Any]]:
            pc = RTCPeerConnection()
            frames: list[tuple[int, int]] = []
            tasks: list[asyncio.Future[None]] = []

            @pc.on("track")
            def on_track(track: Any) -> None:
                async def pull() -> None:
                    while True:
                        try:
                            frame = await track.recv()
                        except MediaStreamError:
                            return
                        frames.append((frame.width, frame.height))

                tasks.append(asyncio.ensure_future(pull()))

            async with connect(ws_url) as sock:
                ready = json.loads(await sock.recv())
                assert ready["type"] == "ready" and ready["agent_online"] is True
                pc.addTransceiver("video", direction="recvonly")
                await pc.setLocalDescription(await pc.createOffer())
                await sock.send(json.dumps({"type": "offer", "sdp": pc.localDescription.sdp}))
                while True:
                    message = json.loads(await sock.recv())
                    if message["type"] == "answer":
                        await pc.setRemoteDescription(RTCSessionDescription(sdp=message["sdp"], type="answer"))
                        break
                for _ in range(200):
                    if len(frames) >= 10:
                        break
                    await asyncio.sleep(0.1)
                await sock.send(json.dumps({"type": "state", "state": "connected"}))
                await asyncio.sleep(0.5)
                live = httpx.get(f"{API}/live/sessions/{sid}", headers=headers).json()
                await sock.send(json.dumps({"type": "stop"}))
                while True:
                    message = json.loads(await sock.recv())
                    if message["type"] == "ended":
                        break
            await pc.close()
            return frames, live

        frames, live = asyncio.run(view())
        assert len(frames) >= 10 and frames[-1] == (1280, 720)
        assert live["status"] == "live" and live["connected_at"]
        assert agent.snapshot().live_viewer is None  # ended
        ended = httpx.get(f"{API}/live/sessions/{sid}", headers=headers).json()
        assert ended["status"] == "ended" and ended["end_reason"] == "viewer_stopped"
    finally:
        agent.shutdown(flush_timeout=2)
