"""Phase 7: live viewing on the agent — screen track, WebRTC answering (real loopback), safeguards, signalling client."""

from __future__ import annotations

import asyncio
import json
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.mediastreams import MediaStreamError
from websockets.asyncio.server import ServerConnection, serve

from app.agent import Agent
from app.live.client import LiveClient, signalling_url
from app.live.streamer import LiveStreamer
from app.live.track import ScreenTrack, SyntheticFrameSource, fit
from tests.conftest import PASSWORD, FakeApi


def expires(seconds: float = 600) -> str:
    return (datetime.now(UTC) + timedelta(seconds=seconds)).isoformat()


def test_frames_fit_1080p_with_even_dimensions() -> None:
    assert fit(1920, 1080) == (1920, 1080)
    assert fit(3840, 2160) == (1920, 1080)
    assert fit(2560, 1080) == (1920, 810)
    assert fit(1366, 768) == (1366, 768)
    assert fit(1365, 767) == (1364, 766)
    assert fit(1080, 1920) == (606, 1080)  # portrait monitor


def test_track_is_paced_and_timestamped() -> None:
    async def run() -> list[Any]:
        track = ScreenTrack(SyntheticFrameSource(3000, 1000), fps=20)
        frames = [await track.recv() for _ in range(4)]
        track.stop()
        with pytest.raises(MediaStreamError):
            await track.recv()
        return frames

    started = time.monotonic()
    frames = asyncio.run(run())
    assert time.monotonic() - started >= 0.14  # 4 frames at 20 fps
    assert [(f.width, f.height) for f in frames] == [(1920, 640)] * 4
    assert [f.pts for f in frames] == [0, 4500, 9000, 13500]


class Viewer:
    """A receive-only aiortc peer, standing in for the manager's browser."""

    def __init__(self) -> None:
        self.pc = RTCPeerConnection()
        self.frames: list[tuple[int, int]] = []
        self.tasks: list[asyncio.Future[None]] = []

        @self.pc.on("track")
        def on_track(track: Any) -> None:
            async def pull() -> None:
                while True:
                    try:
                        frame = await track.recv()
                    except MediaStreamError:
                        return
                    self.frames.append((frame.width, frame.height))

            self.tasks.append(asyncio.ensure_future(pull()))

    async def offer(self) -> str:
        self.pc.addTransceiver("video", direction="recvonly")
        await self.pc.setLocalDescription(await self.pc.createOffer())
        return str(self.pc.localDescription.sdp)


async def wait_until(predicate: Callable[[], bool], timeout: float = 15) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("timed out")
        await asyncio.sleep(0.05)


def test_real_webrtc_stream_from_offer_to_frames_and_stop() -> None:
    async def run() -> None:
        sent: list[dict[str, Any]] = []
        changes: list[str | None] = []
        streamer = LiveStreamer(lambda: SyntheticFrameSource(1280, 720), allowed=lambda: True)
        streamer._on_change = lambda: changes.append(streamer.active.viewer_name if streamer.active else None)

        async def send(message: dict[str, Any]) -> None:
            sent.append(message)

        viewer = Viewer()
        sdp = await viewer.offer()
        await streamer.handle(
            {
                "type": "offer",
                "session_id": "s1",
                "sdp": sdp,
                "viewer_name": "Mae Manager",
                "expires_at": expires(),
                "ice_servers": [],
            },
            send,
        )
        answer = next(m for m in sent if m["type"] == "answer")
        assert answer["session_id"] == "s1" and "m=video" in answer["sdp"]
        assert {"type": "candidate", "session_id": "s1", "candidate": None} in sent
        await viewer.pc.setRemoteDescription(RTCSessionDescription(sdp=answer["sdp"], type="answer"))

        await wait_until(lambda: len(viewer.frames) >= 5)
        assert viewer.frames[-1] == (1280, 720)
        await wait_until(lambda: {"type": "state", "session_id": "s1", "state": "connected"} in sent)
        assert streamer.active is not None and streamer.active.viewer_name == "Mae Manager"
        assert "Mae Manager" in changes

        # A browser-format trickle candidate is accepted (and a malformed one ignored).
        await streamer.handle(
            {
                "type": "candidate",
                "session_id": "s1",
                "candidate": {
                    "candidate": "candidate:1 1 udp 2122260223 127.0.0.1 50000 typ host",
                    "sdpMid": "0",
                    "sdpMLineIndex": 0,
                },
            },
            send,
        )
        await streamer.handle({"type": "candidate", "session_id": "s1", "candidate": {"candidate": "garbage"}}, send)

        await streamer.handle({"type": "stop", "session_id": "s1", "reason": "viewer_stopped"}, send)
        assert streamer.active is None and not streamer.pending
        await viewer.pc.close()

    asyncio.run(run())


def test_refuses_outside_work_and_enforces_expiry() -> None:
    async def run() -> None:
        sent: list[dict[str, Any]] = []

        async def send(message: dict[str, Any]) -> None:
            sent.append(message)

        working = False
        streamer = LiveStreamer(lambda: SyntheticFrameSource(320, 180), allowed=lambda: working)
        viewer = Viewer()
        offer = {
            "type": "offer",
            "session_id": "s2",
            "sdp": await viewer.offer(),
            "viewer_name": "V",
            "expires_at": expires(),
            "ice_servers": [],
        }
        await streamer.handle(offer, send)
        assert sent == [{"type": "ended", "session_id": "s2", "reason": "not_working"}]
        assert not streamer.pending

        working = True
        sent.clear()
        await streamer.handle(offer | {"expires_at": expires(0.5)}, send)
        assert streamer.pending
        await wait_until(lambda: {"type": "ended", "session_id": "s2", "reason": "max_duration"} in sent, timeout=5)
        assert not streamer.pending

        # A second offer for the same session replaces the connection (reconnection / ICE restart).
        sent.clear()
        await streamer.handle(offer | {"expires_at": expires()}, send)
        first = streamer._streams["s2"].pc
        await streamer.handle(offer | {"sdp": await Viewer().offer(), "expires_at": expires()}, send)
        assert streamer._streams["s2"].pc is not first and first.connectionState == "closed"
        await streamer.end_all("work_session_stopped", send)
        assert sent[-1] == {"type": "ended", "session_id": "s2", "reason": "work_session_stopped"}
        await viewer.pc.close()

    asyncio.run(run())


def test_signalling_url() -> None:
    assert signalling_url("http://localhost:8080/api") == "ws://localhost:8080/api/agent/live"
    assert signalling_url("https://wp.example.com/api/") == "wss://wp.example.com/api/agent/live"


class SignallingServer:
    """A stand-in for the API's /agent/live socket, on a background event loop."""

    def __init__(self) -> None:
        self.headers: list[str] = []
        self.received: list[dict[str, Any]] = []
        self.reject_first = True
        self.loop = asyncio.new_event_loop()
        self.port = 0
        self.sockets: list[ServerConnection] = []
        ready = threading.Event()

        async def handler(socket: ServerConnection) -> None:
            self.headers.append(socket.request.headers.get("Authorization", "") if socket.request else "")
            if self.reject_first:
                self.reject_first = False
                await socket.close(code=4401, reason="token_expired")
                return
            self.sockets.append(socket)
            await socket.send(json.dumps({"type": "hello"}))
            async for raw in socket:
                self.received.append(json.loads(raw))

        async def main() -> None:
            async with serve(handler, "127.0.0.1", 0) as server:
                self.port = server.sockets[0].getsockname()[1]
                ready.set()
                await asyncio.Future()

        threading.Thread(target=lambda: self.loop.run_until_complete(main()), daemon=True).start()
        ready.wait(5)

    def send(self, message: dict[str, Any]) -> None:
        asyncio.run_coroutine_threadsafe(self.sockets[-1].send(json.dumps(message)), self.loop).result(5)


def test_client_survives_a_server_that_drops_connections_mid_handshake(
    make_agent: Callable[..., Agent], fake_api: FakeApi
) -> None:
    import socket as socketlib

    agent = make_agent()
    agent.sign_in("ada@example.com", PASSWORD)
    listener = socketlib.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen()
    port = listener.getsockname()[1]
    accepted: list[int] = []

    def drop_connections() -> None:
        while len(accepted) < 2:
            conn, _ = listener.accept()
            accepted.append(1)
            conn.close()  # like a restarting proxy: no HTTP response at all

    threading.Thread(target=drop_connections, daemon=True).start()
    client = LiveClient(f"http://127.0.0.1:{port}", agent.auth, agent.streamer)
    client.start()
    try:
        deadline = time.monotonic() + 15
        while len(accepted) < 2 and time.monotonic() < deadline:
            time.sleep(0.05)
        assert len(accepted) == 2  # it kept retrying after the broken handshake
        assert client._thread is not None and client._thread.is_alive()
    finally:
        client.stop()
        listener.close()


def test_client_authenticates_refreshes_token_and_relays(make_agent: Callable[..., Agent], fake_api: FakeApi) -> None:
    agent = make_agent()
    agent.sign_in("ada@example.com", PASSWORD)
    agent.start_session()
    server = SignallingServer()
    client = agent.live = LiveClient(f"http://127.0.0.1:{server.port}", agent.auth, agent.streamer)
    client.start()
    try:
        deadline = time.monotonic() + 15
        while not (client.connected and server.sockets) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert client.connected
        assert len(server.headers) == 2 and server.headers[0] != server.headers[1]  # refreshed after 4401
        assert all(h.startswith("Bearer tok-") for h in server.headers)

        async def make_offer() -> str:
            return await Viewer().offer()

        server.send(
            {
                "type": "offer",
                "session_id": "s9",
                "sdp": asyncio.run(make_offer()),
                "viewer_name": "Mae",
                "expires_at": expires(),
                "ice_servers": [],
            }
        )
        deadline = time.monotonic() + 15
        while not any(m.get("type") == "answer" for m in server.received) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert any(m.get("type") == "answer" and m["session_id"] == "s9" for m in server.received)

        agent.stop_session()  # work stops: the stream ends and the server is told why
        ended = {"type": "ended", "session_id": "s9", "reason": "work_session_stopped"}
        deadline = time.monotonic() + 5
        while ended not in server.received and time.monotonic() < deadline:
            time.sleep(0.05)
        assert {"type": "ended", "session_id": "s9", "reason": "work_session_stopped"} in server.received
    finally:
        client.stop()
    assert not client.connected
