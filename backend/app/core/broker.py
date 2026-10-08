"""Shared realtime state and event distribution between API processes.

Every API process ("node") connects to Redis and uses it for:

* **pub/sub:** realtime events for browser sockets, and live-viewing signalling between the node holding a viewer's
  socket, the node holding the agent's socket and the node running the session;
* **registries with expiry:** which node holds each agent's live socket, which node runs each live session
  (refreshed while alive, so a crashed node's entries expire instead of lingering);
* **leases:** one node at a time runs cluster-wide jobs (alert scanning, retention sweeps);
* **counters:** fixed-window rate limits.

`MemoryBroker` implements the same interface inside one process. It is used when `REDIS_URL` is not set (local
development, unit tests): behaviour is identical for a single process, but nothing is shared, so production
deployments with more than one API process must set `REDIS_URL`.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
import uuid
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

logger = logging.getLogger(__name__)

Handler = Callable[[dict[str, Any]], Awaitable[None]]


class Broker(Protocol):
    node_id: str
    #: True when state is shared with other processes (Redis).
    shared: bool

    async def ping(self) -> float:
        """Round-trip time in ms; raises when the broker is unreachable."""
        ...

    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def publish(self, channel: str, message: dict[str, Any]) -> int:
        """Returns the number of nodes that received it."""
        ...

    async def subscribe(self, channel: str, handler: Handler) -> None: ...
    async def unsubscribe(self, channel: str) -> None: ...
    async def set(
        self, key: str, value: str, ttl: float | None = None, *, only_if_absent: bool = False
    ) -> bool: ...
    async def get(self, key: str) -> str | None: ...
    async def get_many(self, keys: list[str]) -> list[str | None]: ...
    async def delete(self, key: str, *, only_if: str | None = None) -> None: ...
    async def lease(self, name: str, ttl: float) -> bool:
        """Hold (or renew) a cluster-wide lease. True while this node holds it."""
        ...

    async def hit(self, key: str, window: float) -> int:
        """Increment a counter that resets after `window` seconds; returns the new count."""
        ...


def _new_node_id() -> str:
    return uuid.uuid4().hex[:12]


class MemoryBroker:
    """Single-process implementation (no Redis)."""

    shared = False

    def __init__(self) -> None:
        self.node_id = _new_node_id()
        self._handlers: dict[str, Handler] = {}
        self._values: dict[str, tuple[str, float | None]] = {}
        self._counters: dict[str, tuple[int, float]] = {}
        self._pending: set[asyncio.Task[None]] = set()
        self._serial: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def start(self) -> None:
        return None

    async def ping(self) -> float:
        return 0.0

    async def stop(self) -> None:
        self._handlers.clear()
        for task in list(self._pending):
            task.cancel()

    async def publish(self, channel: str, message: dict[str, Any]) -> int:
        handler = self._handlers.get(channel)
        if handler is None:
            return 0
        # Same semantics as Redis: serialised as JSON (no shared objects), delivered asynchronously, in order per channel.
        payload = json.loads(json.dumps(message, default=str))
        lock = self._serial[channel]

        async def run() -> None:
            async with lock:
                try:
                    await handler(payload)
                except Exception:
                    logger.exception("Realtime handler for %s failed", channel)

        task = asyncio.create_task(run())
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)
        return 1

    async def subscribe(self, channel: str, handler: Handler) -> None:
        self._handlers[channel] = handler

    async def unsubscribe(self, channel: str) -> None:
        self._handlers.pop(channel, None)
        self._serial.pop(channel, None)

    def _alive(self, key: str) -> str | None:
        item = self._values.get(key)
        if item is None:
            return None
        value, expires = item
        if expires is not None and expires <= time.monotonic():
            del self._values[key]
            return None
        return value

    async def set(
        self, key: str, value: str, ttl: float | None = None, *, only_if_absent: bool = False
    ) -> bool:
        if only_if_absent and self._alive(key) is not None:
            return False
        self._values[key] = (value, time.monotonic() + ttl if ttl else None)
        return True

    async def get(self, key: str) -> str | None:
        return self._alive(key)

    async def get_many(self, keys: list[str]) -> list[str | None]:
        return [self._alive(k) for k in keys]

    async def delete(self, key: str, *, only_if: str | None = None) -> None:
        if only_if is None or self._alive(key) == only_if:
            self._values.pop(key, None)

    async def lease(self, name: str, ttl: float) -> bool:
        key = f"lease:{name}"
        holder = self._alive(key)
        if holder in (None, self.node_id):
            self._values[key] = (self.node_id, time.monotonic() + ttl)
            return True
        return False

    async def hit(self, key: str, window: float) -> int:
        count, resets = self._counters.get(key, (0, 0.0))
        now = time.monotonic()
        if resets <= now:
            count, resets = 0, now + window
        self._counters[key] = (count + 1, resets)
        return count + 1


# Renew a lease only if we still hold it; otherwise take it if free. Atomic in Redis.
_LEASE = """
local holder = redis.call('GET', KEYS[1])
if holder == ARGV[1] or not holder then
  redis.call('SET', KEYS[1], ARGV[1], 'PX', ARGV[2])
  return 1
end
return 0
"""
_DELETE_IF = """
if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('DEL', KEYS[1]) end
return 0
"""
_HIT = """
local n = redis.call('INCR', KEYS[1])
if n == 1 then redis.call('PEXPIRE', KEYS[1], ARGV[1]) end
return n
"""


class RedisBroker:
    """Redis implementation: one connection pool for commands, one pub/sub connection per node."""

    shared = True

    def __init__(self, url: str, prefix: str = "wp") -> None:
        from redis.asyncio import Redis

        self.node_id = _new_node_id()
        self._prefix = prefix
        # Commands fail fast when Redis is unreachable instead of hanging the request.
        self._redis = Redis.from_url(
            url, decode_responses=True, health_check_interval=30, socket_connect_timeout=3, socket_timeout=5
        )
        # The subscription waits for messages indefinitely, so it gets its own connection without a read timeout.
        self._subscriber = Redis.from_url(
            url, decode_responses=True, health_check_interval=30, socket_connect_timeout=3
        )
        self._pubsub = self._subscriber.pubsub(ignore_subscribe_messages=True)
        self._outage = False
        self._handlers: dict[str, Handler] = {}
        self._listener: asyncio.Task[None] | None = None
        self._lease = self._redis.register_script(_LEASE)
        self._delete_if = self._redis.register_script(_DELETE_IF)
        self._hit = self._redis.register_script(_HIT)
        self._pending: set[asyncio.Task[None]] = set()
        self._serial: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    def _k(self, key: str) -> str:
        return f"{self._prefix}:{key}"

    async def start(self) -> None:
        await self._redis.ping()
        # A placeholder subscription keeps the pub/sub connection open before the first real one.
        await self._pubsub.subscribe(self._k(f"node:{self.node_id}"))
        self._listener = asyncio.create_task(self._listen(), name="broker-listener")
        logger.info("Realtime broker connected to Redis (node %s)", self.node_id)

    async def stop(self) -> None:
        if self._listener:
            self._listener.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._listener
        with contextlib.suppress(Exception):
            await self._pubsub.aclose()  # type: ignore[no-untyped-call]
        await self._subscriber.aclose()
        await self._redis.aclose()

    async def ping(self) -> float:
        started = time.perf_counter()
        await self._redis.ping()
        return (time.perf_counter() - started) * 1000

    async def _listen(self) -> None:
        while True:
            try:
                async for raw in self._pubsub.listen():
                    if self._outage:
                        logger.info("Reconnected to Redis; realtime delivery resumed")
                        self._outage = False
                    if raw.get("type") != "message":
                        continue
                    channel = str(raw["channel"])[len(self._prefix) + 1 :]
                    handler = self._handlers.get(channel)
                    if handler is None:
                        continue
                    try:
                        message = json.loads(raw["data"])
                    except ValueError:
                        continue
                    self._dispatch(channel, handler, message)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                # One line per outage (not a traceback per retry); subscriptions are restored on reconnect.
                if not self._outage:
                    logger.warning("Lost the connection to Redis (%s); reconnecting", type(exc).__name__)
                    self._outage = True
                await asyncio.sleep(1)

    def _dispatch(self, channel: str, handler: Handler, message: dict[str, Any]) -> None:
        # Handlers run as tasks (a slow socket must not stall the listener), serialised per channel to keep order.
        async def run() -> None:
            async with self._serial[channel]:
                try:
                    await handler(message)
                except Exception:
                    logger.exception("Realtime handler for %s failed", channel)

        task = asyncio.create_task(run())
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)

    async def publish(self, channel: str, message: dict[str, Any]) -> int:
        return int(await self._redis.publish(self._k(channel), json.dumps(message, default=str)))

    async def subscribe(self, channel: str, handler: Handler) -> None:
        self._handlers[channel] = handler
        await self._pubsub.subscribe(self._k(channel))

    async def unsubscribe(self, channel: str) -> None:
        self._handlers.pop(channel, None)
        self._serial.pop(channel, None)
        await self._pubsub.unsubscribe(self._k(channel))

    async def set(
        self, key: str, value: str, ttl: float | None = None, *, only_if_absent: bool = False
    ) -> bool:
        px = int(ttl * 1000) if ttl else None
        return bool(await self._redis.set(self._k(key), value, px=px, nx=only_if_absent))

    async def get(self, key: str) -> str | None:
        value = await self._redis.get(self._k(key))
        return str(value) if value is not None else None

    async def get_many(self, keys: list[str]) -> list[str | None]:
        if not keys:
            return []
        return [str(v) if v is not None else None for v in await self._redis.mget([self._k(k) for k in keys])]

    async def delete(self, key: str, *, only_if: str | None = None) -> None:
        if only_if is None:
            await self._redis.delete(self._k(key))
        else:
            await self._delete_if(keys=[self._k(key)], args=[only_if])

    async def lease(self, name: str, ttl: float) -> bool:
        return bool(await self._lease(keys=[self._k(f"lease:{name}")], args=[self.node_id, int(ttl * 1000)]))

    async def hit(self, key: str, window: float) -> int:
        return int(await self._hit(keys=[self._k(f"hit:{key}")], args=[int(window * 1000)]))


def build_broker(url: str | None) -> Broker:
    if url:
        return RedisBroker(url)
    logger.warning(
        "REDIS_URL is not set: realtime events and live viewing work within this process only. "
        "Set REDIS_URL before running more than one API process."
    )
    return MemoryBroker()
