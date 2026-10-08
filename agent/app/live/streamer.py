"""WebRTC side of live viewing: one peer connection per live session, answering the viewer's offer.

The viewer always offers (receive-only video); the agent answers with its screen track. A new
offer for a session (reconnection, ICE restart) replaces that session's peer connection with a
fresh one, which keeps renegotiation simple and robust.

Local safeguards, independent of the server: no stream unless a work session is running; every
stream ends at its `expires_at`; all streams end when work stops or the agent signs out.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from aiortc import RTCConfiguration, RTCIceServer, RTCPeerConnection, RTCSessionDescription
from aiortc.sdp import candidate_from_sdp

from app.live.track import FrameSource, ScreenTrack

logger = logging.getLogger(__name__)

Send = Callable[[dict[str, Any]], Awaitable[None]]

#: aiortc can wait forever closing a connection that is still mid-ICE; never let teardown block signalling.
CLOSE_TIMEOUT = 3.0
#: Answering includes ICE candidate gathering (and STUN/TURN round trips when configured).
ANSWER_TIMEOUT = 15.0


@dataclass
class LiveStream:
    session_id: str
    viewer_name: str
    expires_at: float
    pc: RTCPeerConnection
    track: ScreenTrack
    started_at: float = field(default_factory=time.time)
    connected: bool = False
    expiry: asyncio.Task[None] | None = None


def _ice_config(servers: list[dict[str, Any]]) -> RTCConfiguration:
    return RTCConfiguration(
        iceServers=[
            RTCIceServer(urls=s["urls"], username=s.get("username"), credential=s.get("credential")) for s in servers
        ]
    )


class LiveStreamer:
    def __init__(
        self,
        source_factory: Callable[[], FrameSource],
        *,
        allowed: Callable[[], bool],
        on_change: Callable[[], None] = lambda: None,
    ) -> None:
        self._source_factory = source_factory
        self._allowed = allowed
        self._on_change = on_change
        self._streams: dict[str, LiveStream] = {}

    # ------------------------------------------------------------------ status for the UI
    @property
    def active(self) -> LiveStream | None:
        """The stream currently showing media, if any (the employee's indicator)."""
        connected = [s for s in self._streams.values() if s.connected]
        return connected[0] if connected else None

    @property
    def pending(self) -> bool:
        return bool(self._streams)

    # ------------------------------------------------------------------ signalling input
    async def handle(self, message: dict[str, Any], send: Send) -> None:
        kind = message.get("type")
        session_id = str(message.get("session_id", ""))
        if kind == "offer":
            await self._offer(message, send)
        elif kind == "candidate":
            await self._candidate(session_id, message.get("candidate"))
        elif kind in ("pause", "stop"):
            await self.close(session_id)

    async def _offer(self, message: dict[str, Any], send: Send) -> None:
        session_id = str(message["session_id"])
        if not self._allowed():
            await send({"type": "ended", "session_id": session_id, "reason": "not_working"})
            return
        await self.close(session_id, notify=False)  # renegotiation: start from a clean connection
        expires_at = datetime.fromisoformat(str(message["expires_at"])).timestamp()
        pc = RTCPeerConnection(_ice_config(message.get("ice_servers") or []))
        track = ScreenTrack(self._source_factory())
        stream = LiveStream(session_id, str(message.get("viewer_name") or "A manager"), expires_at, pc, track)
        self._streams[session_id] = stream

        @pc.on("connectionstatechange")
        async def on_state() -> None:
            state = pc.connectionState
            if self._streams.get(session_id) is not stream:
                return
            await send({"type": "state", "session_id": session_id, "state": state})
            was = stream.connected
            stream.connected = state == "connected"
            if stream.connected != was:
                if stream.connected:
                    logger.info("Live view started by %s", stream.viewer_name)
                self._on_change()

        async def answer() -> None:
            await pc.setRemoteDescription(RTCSessionDescription(sdp=str(message["sdp"]), type="offer"))
            pc.addTrack(track)  # after the offer, so it binds to the viewer's receive-only video transceiver
            await pc.setLocalDescription(await pc.createAnswer())

        try:
            await asyncio.wait_for(answer(), ANSWER_TIMEOUT)
        except Exception:
            logger.exception("Could not answer a live-view offer")
            await self.close(session_id, notify=False)
            await send({"type": "ended", "session_id": session_id, "reason": "agent_error"})
            return
        # aiortc gathers all candidates before setLocalDescription returns: they are in the SDP.
        await send({"type": "answer", "session_id": session_id, "sdp": pc.localDescription.sdp})
        await send({"type": "candidate", "session_id": session_id, "candidate": None})
        stream.expiry = asyncio.create_task(self._expire(session_id, send))
        self._on_change()

    async def _candidate(self, session_id: str, candidate: dict[str, Any] | None) -> None:
        stream = self._streams.get(session_id)
        if stream is None or not candidate or not candidate.get("candidate"):
            return  # end-of-candidates, or a late candidate for a closed stream
        raw = str(candidate["candidate"])
        try:
            ice = candidate_from_sdp(raw.split(":", 1)[1] if raw.startswith("candidate:") else raw)
        except Exception:  # aiortc's parser asserts on malformed input
            return
        ice.sdpMid = candidate.get("sdpMid")
        ice.sdpMLineIndex = candidate.get("sdpMLineIndex")
        with contextlib.suppress(Exception):  # e.g. mDNS host names the network can't resolve
            await stream.pc.addIceCandidate(ice)

    async def _expire(self, session_id: str, send: Send) -> None:
        stream = self._streams.get(session_id)
        if stream is None:
            return
        await asyncio.sleep(max(0.0, stream.expires_at - time.time()))
        if self._streams.get(session_id) is stream:
            await self.close(session_id)
            await send({"type": "ended", "session_id": session_id, "reason": "max_duration"})

    # ------------------------------------------------------------------ teardown
    async def close(self, session_id: str, *, notify: bool = True) -> None:
        stream = self._streams.pop(session_id, None)
        if stream is None:
            return
        if stream.expiry and stream.expiry is not asyncio.current_task():
            stream.expiry.cancel()
        stream.track.stop()
        try:
            await asyncio.wait_for(stream.pc.close(), CLOSE_TIMEOUT)
        except TimeoutError:
            logger.warning("Peer connection did not close cleanly within %ss; abandoned", CLOSE_TIMEOUT)
        except Exception:
            logger.debug("Error closing peer connection", exc_info=True)
        if notify:
            logger.info("Live view ended (%s)", session_id)
        self._on_change()

    async def end_all(self, reason: str, send: Send | None) -> None:
        for session_id in list(self._streams):
            await self.close(session_id)
            if send is not None:
                with contextlib.suppress(Exception):
                    await send({"type": "ended", "session_id": session_id, "reason": reason})
