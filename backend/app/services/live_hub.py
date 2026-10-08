"""Live viewing signalling hub: relays WebRTC offer/answer/ICE between a viewer and an agent, across API processes.

The API never touches media: video flows peer to peer (or through TURN). This hub owns the lifecycle of a live
session:

* **Links:** each agent keeps one signalling WebSocket; each viewer opens one per session. A link that reconnects
  replaces the old one, even if the old one is held by another process.
* **Relay:** messages are validated (closed schemas, size limits, rate limit) and forwarded only between the two
  parties of the same session.
* **Timeouts:** a session must connect within `live_connect_timeout_seconds`, and always ends at its `expires_at`.
* **Reconnection:** if either side drops, the session is *interrupted*. If that side returns within
  `live_reconnect_grace_seconds`, the viewer is told to renegotiate; otherwise it ends.
* **Audit:** requested (in the REST service), connected, ended (with reason and duration).

**Scaling.** The viewer's socket, the agent's socket and the REST request that created the session can each land
on a different API process. Coordination goes through the broker (Redis):

* the process that creates a session *owns* it: it runs the state machine and timers, and records ownership in
  `live:owner:{session}` (expiring, refreshed while alive);
* the process holding an agent's socket records it in `live:agent:{device}` (expiring, refreshed);
* sockets talk to the owner over `live:from-viewer:{session}` / `live:from-agent:{device}`, and the owner answers
  over `live:to-viewer:{session}` / `live:to-agent:{device}`; commands from other processes (e.g. "stop" from a REST
  call) go to `live:control:{session}`;
* if a process dies, its registry entries expire; a cluster-wide sweeper (one process at a time, via a lease) ends
  sessions whose owner is gone, and agents' sockets reconnect to a live process.

Session status and timestamps are persisted in MongoDB at every transition, so nothing critical lives only in the
memory of one process.
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from bson import ObjectId
from fastapi import WebSocket
from pymongo.asynchronous.database import AsyncDatabase

from app.auth.permissions import Permission
from app.core.broker import Broker, MemoryBroker
from app.core.config import Settings
from app.models.live import ACTIVE_STATUSES, STOP_REASONS, LiveEventType, LiveSession, LiveStatus
from app.models.notification import NotificationType
from app.repositories.audit_log import AuditLogRepository
from app.repositories.live import LiveSessionEventRepository, LiveSessionRepository
from app.schemas.live import IceServer
from app.services.audit_service import AuditService
from app.services.live_ice import IceServerProvider
from app.services.live_media import MediaRoute, PeerToPeerRoute
from app.services.notifications.notifier import AlertEvent, Notifier, NullNotifier
from app.utils.time import utcnow

logger = logging.getLogger(__name__)

MAX_MESSAGE_BYTES = 128_000
MAX_MESSAGES_PER_MINUTE = 600
#: Registry entries live this long without a refresh; refreshed every REFRESH_SECONDS.
REGISTRY_TTL_SECONDS = 45.0
REFRESH_SECONDS = 15.0
SWEEP_SECONDS = 30.0


def ice_servers(settings: Settings, identity: str) -> list[IceServer]:
    """STUN as configured, plus TURN with short-lived credentials when configured (see `IceServerProvider`)."""
    return IceServerProvider(settings).servers(identity)


class RateLimiter:
    """Per-socket message limit (state of one connection, so it rightly lives with the socket)."""

    def __init__(self, per_minute: int) -> None:
        self._per_minute = per_minute
        self._window = time.monotonic()
        self._count = 0

    def allow(self) -> bool:
        now = time.monotonic()
        if now - self._window >= 60:
            self._window, self._count = now, 0
        self._count += 1
        return self._count <= self._per_minute


@dataclass(eq=False)
class Link:
    websocket: WebSocket
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    id: str = field(default_factory=lambda: uuid.uuid4().hex)

    async def send(self, message: dict[str, Any]) -> bool:
        try:
            async with self.lock:
                await self.websocket.send_json(message)
            return True
        except Exception:  # the socket is already gone
            return False

    async def close(self, code: int = 1000, reason: str = "") -> None:
        with contextlib.suppress(Exception):
            await self.websocket.close(code=code, reason=reason)


@dataclass(eq=False)
class AgentLink(Link):
    company_id: ObjectId = field(default_factory=ObjectId)
    device_id: ObjectId = field(default_factory=ObjectId)
    employee_id: ObjectId = field(default_factory=ObjectId)


@dataclass
class Runtime:
    """A session's state machine, held by its owner process."""

    session_id: ObjectId
    company_id: ObjectId
    employee_id: ObjectId
    device_id: ObjectId
    viewer_user_id: ObjectId
    viewer_name: str
    expires_at: datetime
    status: LiveStatus = LiveStatus.REQUESTED
    connected_at: datetime | None = None
    #: Seconds of media accumulated across reconnections.
    live_seconds: float = 0.0
    live_since: float | None = None
    reconnects: int = 0
    #: The viewer socket currently attached (wherever it is), by link id.
    viewer_link: str | None = None
    #: The agent socket last seen attaching, by link id (None: connected before the session started).
    agent_link: str | None = None
    timers: dict[str, asyncio.Task[None]] = field(default_factory=dict)


class LiveHub:
    def __init__(
        self,
        settings: Settings,
        db: AsyncDatabase[dict[str, Any]],
        route: MediaRoute | None = None,
        broker: Broker | None = None,
    ) -> None:
        self._settings = settings
        #: STUN, plus TURN when configured. Swap or extend here to add another TURN source.
        self.ice = IceServerProvider(settings)
        self._db = db
        self.route: MediaRoute = route or PeerToPeerRoute()
        self.broker: Broker = broker or MemoryBroker()
        #: Set by the app at start-up; tests and tools may leave it unset.
        self.notifier: Notifier = NullNotifier()
        self._agents: dict[ObjectId, AgentLink] = {}  # agent sockets connected to this process
        self._viewers: dict[ObjectId, Link] = {}  # viewer sockets connected to this process, by session
        self._sessions: dict[ObjectId, Runtime] = {}  # sessions this process owns
        self._background: set[asyncio.Task[None]] = set()
        self._maintenance: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------ helpers
    @property
    def _repo(self) -> LiveSessionRepository:
        return LiveSessionRepository(self._db)

    @property
    def _audit(self) -> AuditService:
        return AuditService(AuditLogRepository(self._db))

    @property
    def _events(self) -> LiveSessionEventRepository:
        return LiveSessionEventRepository(self._db)

    async def record_event(
        self,
        rt: Runtime | LiveSession,
        event: LiveEventType,
        *,
        actor_role: str = "system",
        actor_id: ObjectId | None = None,
        **metadata: Any,
    ) -> None:
        """Add a step to the session's timeline. A failed write is logged; it never interrupts the stream."""
        session_id = rt.session_id if isinstance(rt, Runtime) else rt.id
        try:
            await self._events.record(
                rt.company_id, session_id, event, actor_role=actor_role, actor_id=actor_id, metadata=metadata
            )
        except Exception:
            logger.warning("Could not record %s for live session %s", event.value, session_id, exc_info=True)

    def ice_servers(self, identity: str) -> list[dict[str, Any]]:
        return [s.model_dump(exclude_none=True) for s in self.ice.servers(identity)]

    async def is_online(self, device_id: ObjectId) -> bool:
        return await self.broker.get(f"live:agent:{device_id}") is not None

    async def online_devices(self, device_ids: list[ObjectId]) -> set[ObjectId]:
        values = await self.broker.get_many([f"live:agent:{d}" for d in device_ids])
        return {d for d, v in zip(device_ids, values, strict=True) if v is not None}

    def runtime(self, session_id: ObjectId) -> Runtime | None:
        """The session's state, if this process owns it."""
        return self._sessions.get(session_id)

    def _timer(self, rt: Runtime, name: str, delay: float, action: Callable[[], Awaitable[None]]) -> None:
        self._cancel(rt, name)

        async def fire() -> None:
            await asyncio.sleep(max(0.0, delay))
            rt.timers.pop(name, None)
            await action()

        rt.timers[name] = asyncio.create_task(fire(), name=f"live-{rt.session_id}-{name}")

    @staticmethod
    def _cancel(rt: Runtime, name: str) -> None:
        task = rt.timers.pop(name, None)
        if task and task is not asyncio.current_task():
            task.cancel()

    async def _set(self, rt: Runtime, status: LiveStatus, side: str | None = None, **changes: Any) -> None:
        """Persist a status change and add it to the timeline. `side` says what dropped (agent, viewer or media)."""
        previous = rt.status
        first_connection = status == LiveStatus.LIVE and "connected_at" in changes
        rt.status = status
        await self._repo.set_status(rt.company_id, rt.session_id, {"status": status, **changes})
        if status == previous:
            return
        if status == LiveStatus.CONNECTING:
            await self.record_event(
                rt,
                LiveEventType.CONNECTING,
                actor_role="viewer",
                actor_id=rt.viewer_user_id,
                after=previous.value,
            )
        elif status == LiveStatus.LIVE:
            kind = LiveEventType.STARTED if first_connection else LiveEventType.RECONNECTED
            await self.record_event(
                rt,
                kind,
                actor_role="viewer",
                actor_id=rt.viewer_user_id,
                reconnects=rt.reconnects,
                media_route=self.route.name,
            )
        elif status == LiveStatus.INTERRUPTED:
            await self.record_event(
                rt,
                LiveEventType.DISCONNECTED,
                actor_role="agent" if side == "agent" else "viewer" if side == "viewer" else "system",
                actor_id=rt.viewer_user_id if side == "viewer" else None,
                side=side or "media",
                grace_seconds=self._settings.live_reconnect_grace_seconds,
            )

    async def _to_viewer(self, rt: Runtime, message: dict[str, Any]) -> None:
        await self.broker.publish(f"live:to-viewer:{rt.session_id}", {"send": message})

    async def send_to_agent(self, rt: Runtime, message: dict[str, Any]) -> bool:
        if not await self.is_online(rt.device_id):
            return False
        return await self.broker.publish(f"live:to-agent:{rt.device_id}", {"send": message}) > 0

    def _pause_clock(self, rt: Runtime) -> None:
        if rt.live_since is not None:
            rt.live_seconds += time.monotonic() - rt.live_since
            rt.live_since = None

    def detach_soon(self, cleanup: Awaitable[None]) -> None:
        """Run disconnect cleanup as its own task: the socket handler may be cancelled, the cleanup must not be."""

        async def run() -> None:
            await cleanup

        task = asyncio.create_task(run())
        self._background.add(task)
        task.add_done_callback(self._background.discard)

    # ------------------------------------------------------------------ lifecycle
    async def startup(self) -> None:
        closed = await self.sweep_orphans()
        if closed:
            logger.info("Closed %d live session(s) whose process is gone", closed)
        self._maintenance = asyncio.create_task(self._maintain(), name="live-hub-maintenance")

    async def shutdown(self) -> None:
        if self._maintenance:
            self._maintenance.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._maintenance
        # A clean shutdown (deploy, restart, scale-in) hands sessions over instead of ending them: media keeps
        # flowing peer to peer, and the viewer's and agent's sockets reconnect to another process, which adopts it.
        for session_id in list(self._sessions):
            await self._release(session_id)
        for device_id, link in list(self._agents.items()):
            await self.broker.delete(f"live:agent:{device_id}", only_if=self.broker.node_id)
            await link.close(code=1012, reason="Server restarting")

    async def _maintain(self) -> None:
        """Keep this process's registry entries alive; one process at a time sweeps orphaned sessions."""
        last_sweep = 0.0
        while True:
            await asyncio.sleep(REFRESH_SECONDS)
            try:
                for device_id in list(self._agents):
                    await self.broker.set(
                        f"live:agent:{device_id}", self.broker.node_id, REGISTRY_TTL_SECONDS
                    )
                for session_id in list(self._sessions):
                    await self.broker.set(
                        f"live:owner:{session_id}", self.broker.node_id, REGISTRY_TTL_SECONDS
                    )
                if time.monotonic() - last_sweep >= SWEEP_SECONDS and await self.broker.lease(
                    "live-sweeper", SWEEP_SECONDS * 2
                ):
                    last_sweep = time.monotonic()
                    await self.sweep_orphans()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Live hub maintenance failed; will retry")

    async def sweep_orphans(self) -> int:
        """End sessions whose owning process is gone (its registry entry expired)."""
        ended = 0
        now = utcnow()
        grace = timedelta(seconds=self._settings.live_reconnect_grace_seconds)
        async for doc in self._db[LiveSessionRepository.collection_name].find(
            {"status": {"$in": list(ACTIVE_STATUSES)}},
            {"_id": 1, "company_id": 1, "device_id": 1, "handover_at": 1},
        ):
            sid = doc["_id"]
            if sid in self._sessions or await self.broker.get(f"live:owner:{sid}") is not None:
                continue
            handover_at = doc.get("handover_at")
            if handover_at is not None and now - handover_at < grace:
                continue  # released by a process that shut down cleanly; waiting to be adopted
            await self._repo.set_status(
                doc["company_id"],
                sid,
                {"status": LiveStatus.ENDED, "ended_at": now, "end_reason": "server_restart"},
            )
            await self.broker.publish(
                f"live:to-agent:{doc['device_id']}",
                {"send": {"type": "stop", "session_id": str(sid), "reason": "server_restart"}},
            )
            await self.broker.publish(f"live:to-viewer:{sid}", {"close": [1000, "Session ended"]})
            ended += 1
        return ended

    async def open_session(self, session: LiveSession) -> Runtime:
        """Start running a new session in this process (its owner)."""
        rt = Runtime(
            session_id=session.id,
            company_id=session.company_id,
            employee_id=session.employee_id,
            device_id=session.device_id,
            viewer_user_id=session.viewer_user_id,
            viewer_name=session.viewer_name,
            expires_at=session.expires_at,
        )
        await self._run(rt)
        self._timer(
            rt, "connect", self._settings.live_connect_timeout_seconds, lambda: self._connect_timeout(rt)
        )
        return rt

    async def _release(self, session_id: ObjectId) -> None:
        """Stop running a session here without ending it, so another process can adopt it."""
        rt = self._sessions.pop(session_id, None)
        if rt is None:
            return
        for name in list(rt.timers):
            self._cancel(rt, name)
        self._pause_clock(rt)
        await self._repo.set_status(
            rt.company_id,
            rt.session_id,
            {
                "status": LiveStatus.INTERRUPTED,
                "handover_at": utcnow(),
                "live_seconds": rt.live_seconds,
                "reconnects": rt.reconnects,
            },
        )
        await self.broker.unsubscribe(f"live:from-viewer:{session_id}")
        await self.broker.unsubscribe(f"live:control:{session_id}")
        if not any(r.device_id == rt.device_id for r in self._sessions.values()):
            await self.broker.unsubscribe(f"live:from-agent:{rt.device_id}")
        await self.broker.delete(f"live:owner:{session_id}", only_if=self.broker.node_id)
        await self.record_event(rt, LiveEventType.DISCONNECTED, side="server", reason="handover")
        logger.info("Live session %s handed over (this process is stopping)", session_id)

    async def _adopt(self, session_id: ObjectId) -> bool:
        """Run a session whose owner is gone (released on shutdown, or crashed) here. One process wins."""
        if session_id in self._sessions:
            return True
        if not await self.broker.lease(f"live-adopt:{session_id}", 10):
            # Another process is adopting it right now; it owns the session in a moment.
            for _ in range(40):
                if await self.broker.get(f"live:owner:{session_id}") is not None:
                    return True
                await asyncio.sleep(0.05)
            return False
        if await self.broker.get(f"live:owner:{session_id}") is not None:
            return True
        doc = await self._db[LiveSessionRepository.collection_name].find_one(
            {"_id": session_id, "status": {"$in": list(ACTIVE_STATUSES)}}
        )
        if doc is None:
            return False
        session = LiveSession.from_document(doc)
        if session.expires_at <= utcnow():
            return False
        rt = Runtime(
            session_id=session.id,
            company_id=session.company_id,
            employee_id=session.employee_id,
            device_id=session.device_id,
            viewer_user_id=session.viewer_user_id,
            viewer_name=session.viewer_name,
            expires_at=session.expires_at,
            status=LiveStatus.INTERRUPTED,
            connected_at=session.connected_at,
            live_seconds=session.live_seconds,
            reconnects=session.reconnects,
        )
        await self._run(rt)
        await self._repo.set_status(
            rt.company_id, rt.session_id, {"status": LiveStatus.INTERRUPTED, "handover_at": None}
        )
        # Both sides must be back, with media flowing again, within the grace period.
        self._timer(
            rt,
            "media_grace",
            self._settings.live_reconnect_grace_seconds,
            functools.partial(self._grace_end, rt.session_id, "server_restart"),
        )
        logger.info("Live session %s adopted by this process", session_id)
        return True

    async def _run(self, rt: Runtime) -> None:
        """Own `rt` in this process: registry entry, channel subscriptions and the hard-stop timer."""
        first_for_device = not any(r.device_id == rt.device_id for r in self._sessions.values())
        self._sessions[rt.session_id] = rt
        await self.broker.set(f"live:owner:{rt.session_id}", self.broker.node_id, REGISTRY_TTL_SECONDS)
        await self.broker.subscribe(
            f"live:from-viewer:{rt.session_id}", functools.partial(self._on_viewer_event, rt)
        )
        await self.broker.subscribe(f"live:control:{rt.session_id}", functools.partial(self._on_control, rt))
        if first_for_device:
            await self.broker.subscribe(
                f"live:from-agent:{rt.device_id}", functools.partial(self._on_agent_event, rt.device_id)
            )
        remaining = (rt.expires_at - utcnow()).total_seconds()
        self._timer(
            rt, "expire", remaining, functools.partial(self._grace_end, rt.session_id, "max_duration")
        )

    async def _connect_timeout(self, rt: Runtime) -> None:
        if rt.status != LiveStatus.LIVE:
            await self.end(rt.session_id, "connect_timeout")

    async def end(self, session_id: ObjectId, reason: str, actor_user_id: ObjectId | None = None) -> bool:
        """Idempotent. Ends the session wherever it runs. False only if no live process is running it."""
        if session_id not in self._sessions:
            if await self.broker.get(f"live:owner:{session_id}") is None:
                # Released and not adopted yet (or its process died): take it over to end it properly.
                if not await self._adopt(session_id):
                    return False
                return await self._end_local(session_id, reason, actor_user_id)
            await self.broker.publish(
                f"live:control:{session_id}",
                {"end": reason, "actor": str(actor_user_id) if actor_user_id else None},
            )
            # The owner records the outcome; wait (briefly) so the caller can report the final state.
            for _ in range(60):
                doc = await self._db[LiveSessionRepository.collection_name].find_one(
                    {"_id": session_id}, {"status": 1}
                )
                if doc is None or doc.get("status") == LiveStatus.ENDED:
                    break
                await asyncio.sleep(0.05)
            return True
        return await self._end_local(session_id, reason, actor_user_id)

    async def _end_local(self, session_id: ObjectId, reason: str, actor_user_id: ObjectId | None) -> bool:
        rt = self._sessions.pop(session_id, None)
        if rt is None:
            return False
        for name in list(rt.timers):
            self._cancel(rt, name)
        self._pause_clock(rt)
        await self.broker.delete(f"live:owner:{session_id}", only_if=self.broker.node_id)
        await self.broker.unsubscribe(f"live:from-viewer:{session_id}")
        await self.broker.unsubscribe(f"live:control:{session_id}")
        if not any(r.device_id == rt.device_id for r in self._sessions.values()):
            await self.broker.unsubscribe(f"live:from-agent:{rt.device_id}")
        now = utcnow()
        duration = round(rt.live_seconds) if rt.connected_at else None
        await self._set(
            rt,
            LiveStatus.ENDED,
            ended_at=now,
            end_reason=reason,
            duration_seconds=duration,
            reconnects=rt.reconnects,
        )
        if rt.connected_at:
            self._notify_live(rt, started=False, reason=reason, duration=duration)
        await self.record_event(
            rt,
            LiveEventType.STOPPED if reason in STOP_REASONS else LiveEventType.FAILED,
            actor_role="viewer" if actor_user_id is not None else "system",
            actor_id=actor_user_id,
            reason=reason,
            duration_seconds=duration,
            reconnects=rt.reconnects,
        )
        await self.send_to_agent(rt, {"type": "stop", "session_id": str(rt.session_id), "reason": reason})
        await self.broker.publish(
            f"live:to-viewer:{session_id}",
            {
                "send": {"type": "ended", "reason": reason, "duration_seconds": duration},
                "close": [1000, "Session ended"],
            },
        )
        await self._audit.record(
            "live.session_ended",
            company_id=rt.company_id,
            actor_user_id=actor_user_id,
            target_type="live_session",
            target_id=str(rt.session_id),
            subject_employee_id=rt.employee_id,
            metadata={
                "reason": reason,
                "viewer": rt.viewer_name,
                "device_id": str(rt.device_id),
                "started_at": rt.connected_at.isoformat() if rt.connected_at else None,
                "ended_at": now.isoformat(),
                "duration_seconds": duration,
                "reconnects": rt.reconnects,
                "media_route": self.route.name,
            },
        )
        logger.info("Live session %s ended (%s)", rt.session_id, reason)
        return True

    async def _on_control(self, rt: Runtime, message: dict[str, Any]) -> None:
        if "end" in message:
            actor = message.get("actor")
            await self._end_local(rt.session_id, str(message["end"]), ObjectId(actor) if actor else None)

    def _notify_live(
        self, rt: Runtime, *, started: bool, reason: str = "", duration: int | None = None
    ) -> None:
        """The person viewed always hears about it (transparency); administrators too, for oversight."""
        if started:
            title = f"{rt.viewer_name} is viewing {{employee}}'s screen live"
            body = "Live screen viewing started. Video is not recorded; the session is in the audit log."
        else:
            minutes = (duration or 0) // 60
            title = f"{rt.viewer_name} stopped viewing {{employee}}'s screen"
            body = f"The live view lasted {minutes} min{'' if minutes == 1 else 's'} ({reason.replace('_', ' ')})."
        self.notifier.emit(
            AlertEvent(
                company_id=rt.company_id,
                type=NotificationType.LIVE_SESSION_STARTED
                if started
                else NotificationType.LIVE_SESSION_ENDED,
                title=title,
                body=body,
                employee_id=rt.employee_id,
                link="/live",
                subject=f"live:{rt.session_id}",
                include_employee=True,
                permission=Permission.POLICY_MANAGE,
                exclude_user_ids=[rt.viewer_user_id],
                data={"session_id": str(rt.session_id)},
            )
        )

    # ------------------------------------------------------------------ agent sockets (any process)
    async def attach_agent(self, link: AgentLink) -> None:
        device = link.device_id
        # Tell any other process holding an older socket for this device to close it.
        await self.broker.publish(f"live:to-agent:{device}", {"replaced_by": link.id})
        previous = self._agents.get(device)
        self._agents[device] = link
        if previous and previous is not link:
            await previous.close(code=4000, reason="Replaced by a newer connection")
        await self.broker.subscribe(f"live:to-agent:{device}", functools.partial(self._on_to_agent, device))
        await self.broker.set(f"live:agent:{device}", self.broker.node_id, REGISTRY_TTL_SECONDS)
        await self.broker.publish(f"live:from-agent:{device}", {"kind": "attached", "link": link.id})

    async def detach_agent(self, link: AgentLink) -> None:
        device = link.device_id
        if self._agents.get(device) is not link:
            return
        del self._agents[device]
        await self.broker.unsubscribe(f"live:to-agent:{device}")
        await self.broker.delete(f"live:agent:{device}", only_if=self.broker.node_id)
        await self.broker.publish(f"live:from-agent:{device}", {"kind": "detached", "link": link.id})

    async def from_agent(self, link: AgentLink, message: dict[str, Any]) -> None:
        if message["type"] == "ping":
            await link.send({"type": "pong"})
            return
        await self.broker.publish(
            f"live:from-agent:{link.device_id}", {"kind": "message", "link": link.id, "message": message}
        )

    async def _on_to_agent(self, device_id: ObjectId, message: dict[str, Any]) -> None:
        link = self._agents.get(device_id)
        if link is None:
            return
        replaced_by = message.get("replaced_by")
        if replaced_by:
            if replaced_by != link.id:  # a newer socket attached (possibly to another process)
                del self._agents[device_id]
                await self.broker.unsubscribe(f"live:to-agent:{device_id}")
                await link.close(code=4000, reason="Replaced by a newer connection")
            return
        await link.send(message["send"])

    # ------------------------------------------------------------------ agent events (owner process)
    def _for_device(self, device_id: ObjectId) -> list[Runtime]:
        return [rt for rt in self._sessions.values() if rt.device_id == device_id]

    async def _on_agent_event(self, device_id: ObjectId, event: dict[str, Any]) -> None:
        kind, link_id = event["kind"], event.get("link")
        for rt in self._for_device(device_id):
            if kind == "attached":
                rt.agent_link = link_id
                self._cancel(rt, "agent_grace")
                if rt.status == LiveStatus.INTERRUPTED:
                    await self._to_viewer(rt, {"type": "peer_ready"})  # the viewer sends a fresh offer
            elif kind == "detached":
                if rt.agent_link not in (None, link_id):
                    continue  # an older socket going away after its replacement arrived
                rt.agent_link = None
                self._pause_clock(rt)
                await self._set(rt, LiveStatus.INTERRUPTED, side="agent")
                await self._to_viewer(rt, {"type": "peer_left"})
                self._timer(
                    rt,
                    "agent_grace",
                    self._settings.live_reconnect_grace_seconds,
                    functools.partial(self._grace_end, rt.session_id, "agent_disconnected"),
                )
            elif kind == "message":
                await self._agent_message(rt, event["message"])

    async def _grace_end(self, session_id: ObjectId, reason: str) -> None:
        await self.end(session_id, reason)

    async def _agent_message(self, rt: Runtime, message: dict[str, Any]) -> None:
        if message.get("session_id") != str(rt.session_id):
            return  # another session of this device, or garbage: drop silently
        kind = message["type"]
        if kind == "answer":
            if rt.status == LiveStatus.REQUESTED:
                await self._set(rt, LiveStatus.CONNECTING)
            await self._to_viewer(rt, {"type": "answer", "sdp": message["sdp"]})
        elif kind == "candidate":
            await self._to_viewer(rt, {"type": "candidate", "candidate": message["candidate"]})
        elif kind == "ended":
            await self.end(rt.session_id, message["reason"])

    # ------------------------------------------------------------------ viewer sockets (any process)
    async def viewable(
        self, session_id: ObjectId, company_id: ObjectId, user_id: ObjectId
    ) -> LiveSession | None:
        """The session, if this user requested it and a live process is running it."""
        session = await self._repo.get_by_id(company_id, session_id)
        if session is None or session.viewer_user_id != user_id or session.status == LiveStatus.ENDED:
            return None
        owned = session_id in self._sessions or await self.broker.get(f"live:owner:{session_id}") is not None
        # No owner: its process shut down (or died) and the viewer is back first; adopt the session here.
        if not owned and not await self._adopt(session_id):
            return None
        return session

    async def attach_viewer(self, session_id: ObjectId, link: Link) -> None:
        await self.broker.publish(f"live:to-viewer:{session_id}", {"replaced_by": link.id})
        previous = self._viewers.get(session_id)
        self._viewers[session_id] = link
        if previous and previous is not link:
            await previous.close(code=4000, reason="Opened in another window")
        await self.broker.subscribe(
            f"live:to-viewer:{session_id}", functools.partial(self._on_to_viewer, session_id)
        )
        await self.broker.publish(f"live:from-viewer:{session_id}", {"kind": "attached", "link": link.id})

    async def detach_viewer(self, session_id: ObjectId, link: Link) -> None:
        if self._viewers.get(session_id) is not link:
            return
        del self._viewers[session_id]
        await self.broker.unsubscribe(f"live:to-viewer:{session_id}")
        await self.broker.publish(f"live:from-viewer:{session_id}", {"kind": "detached", "link": link.id})

    async def from_viewer(self, session_id: ObjectId, link: Link, message: dict[str, Any]) -> None:
        if message["type"] == "ping":
            await link.send({"type": "pong"})
            return
        await self.broker.publish(
            f"live:from-viewer:{session_id}", {"kind": "message", "link": link.id, "message": message}
        )

    async def _on_to_viewer(self, session_id: ObjectId, message: dict[str, Any]) -> None:
        link = self._viewers.get(session_id)
        if link is None:
            return
        replaced_by = message.get("replaced_by")
        if replaced_by:
            if replaced_by != link.id:
                del self._viewers[session_id]
                await self.broker.unsubscribe(f"live:to-viewer:{session_id}")
                await link.close(code=4000, reason="Opened in another window")
            return
        if "send" in message:
            await link.send(message["send"])
        if "close" in message:
            code, reason = message["close"]
            await link.close(code=int(code), reason=str(reason))

    # ------------------------------------------------------------------ viewer events (owner process)
    async def _on_viewer_event(self, rt: Runtime, event: dict[str, Any]) -> None:
        if rt.session_id not in self._sessions:
            return
        kind, link_id = event["kind"], event.get("link")
        if kind == "attached":
            replaced = rt.viewer_link is not None and rt.viewer_link != link_id
            if rt.status == LiveStatus.INTERRUPTED or replaced:
                rt.reconnects += 1
            rt.viewer_link = link_id
            self._cancel(rt, "viewer_grace")
            await self._to_viewer(
                rt,
                {
                    "type": "ready",
                    "session_id": str(rt.session_id),
                    "status": rt.status,
                    "agent_online": await self.is_online(rt.device_id),
                    "ice_servers": self.ice_servers(str(rt.viewer_user_id)),
                    "expires_at": rt.expires_at.isoformat(),
                    "media_route": self.route.name,
                },
            )
        elif kind == "detached":
            if rt.viewer_link != link_id:
                return  # an older window closing after a newer one attached
            rt.viewer_link = None
            self._pause_clock(rt)
            await self._set(rt, LiveStatus.INTERRUPTED, side="viewer")
            await self.send_to_agent(rt, {"type": "pause", "session_id": str(rt.session_id)})
            self._timer(
                rt,
                "viewer_grace",
                self._settings.live_reconnect_grace_seconds,
                functools.partial(self._grace_end, rt.session_id, "viewer_disconnected"),
            )
        elif kind == "message" and link_id == rt.viewer_link:
            await self._viewer_message(rt, event["message"])

    async def _viewer_message(self, rt: Runtime, message: dict[str, Any]) -> None:
        kind = message["type"]
        if kind == "stop":
            await self.end(rt.session_id, "viewer_stopped", actor_user_id=rt.viewer_user_id)
        elif kind == "offer":
            if not await self.is_online(rt.device_id):
                await self._to_viewer(rt, {"type": "peer_left"})
                return
            sent = await self.route.viewer_offer(self, rt, message["sdp"])
            if sent and rt.status in (LiveStatus.REQUESTED, LiveStatus.INTERRUPTED):
                await self._set(rt, LiveStatus.CONNECTING)
        elif kind == "candidate":
            await self.route.viewer_candidate(self, rt, message["candidate"])
        elif kind == "state":
            await self._viewer_state(rt, message["state"])

    async def _viewer_state(self, rt: Runtime, state: str) -> None:
        if state == "connected" and rt.status != LiveStatus.LIVE:
            first = rt.connected_at is None
            changes: dict[str, Any] = {"reconnects": rt.reconnects}
            if first:
                rt.connected_at = utcnow()
                changes["connected_at"] = rt.connected_at
            rt.live_since = time.monotonic()
            self._cancel(rt, "connect")
            self._cancel(rt, "media_grace")
            await self._set(rt, LiveStatus.LIVE, **changes)
            if first and rt.connected_at is not None:
                self._notify_live(rt, started=True)
                await self._audit.record(
                    "live.session_connected",
                    company_id=rt.company_id,
                    actor_user_id=rt.viewer_user_id,
                    target_type="live_session",
                    target_id=str(rt.session_id),
                    subject_employee_id=rt.employee_id,
                    metadata={
                        "viewer": rt.viewer_name,
                        "device_id": str(rt.device_id),
                        "started_at": rt.connected_at.isoformat(),
                    },
                )
        elif state in ("disconnected", "failed") and rt.status == LiveStatus.LIVE:
            # Media path lost while both sockets are up: the viewer renegotiates (ICE restart via a new offer).
            self._pause_clock(rt)
            rt.reconnects += 1
            await self._set(rt, LiveStatus.INTERRUPTED, side="media", reconnects=rt.reconnects)
            self._timer(
                rt,
                "media_grace",
                self._settings.live_reconnect_grace_seconds,
                functools.partial(self._grace_end, rt.session_id, "connection_lost"),
            )
