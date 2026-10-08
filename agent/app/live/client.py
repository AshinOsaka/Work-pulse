"""Live-viewing signalling client: a persistent WebSocket from the agent to the API.

Runs its own asyncio event loop in a background thread (aiortc is asyncio-based; the rest of the
agent is thread-based). Authenticates with the device token in the `Authorization` header. The
connection is kept open while signed in and re-established with exponential back-off; a refused
token is refreshed once before backing off. The API learns the agent is reachable for live
viewing purely from this connection being open.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import threading
from collections.abc import Callable
from concurrent.futures import Future
from typing import Any

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed, InvalidStatus, WebSocketException

from app.auth.device_auth import DeviceAuthenticator, NotSignedInError
from app.live.streamer import LiveStreamer
from app.sync.api_client import ApiError, ApiUnavailable, backoff_delay

logger = logging.getLogger(__name__)

MAX_BACKOFF = 60.0


def signalling_url(api_url: str) -> str:
    base = api_url.rstrip("/")
    if base.startswith("https://"):
        base = "wss://" + base[len("https://") :]
    elif base.startswith("http://"):
        base = "ws://" + base[len("http://") :]
    return f"{base}/agent/live"


class LiveClient:
    def __init__(self, api_url: str, auth: DeviceAuthenticator, streamer: LiveStreamer) -> None:
        self._url = signalling_url(api_url)
        self._auth = auth
        self.streamer = streamer
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._task: asyncio.Task[None] | None = None
        self._socket: ClientConnection | None = None
        self._send_lock: asyncio.Lock | None = None
        self.connected = False
        self.on_status: Callable[[], None] = lambda: None

    # ------------------------------------------------------------------ lifecycle (any thread)
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        ready = threading.Event()

        def run() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._loop = loop
            self._send_lock = asyncio.Lock()
            self._task = loop.create_task(self._run())
            ready.set()
            with contextlib.suppress(asyncio.CancelledError):
                loop.run_until_complete(self._task)
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()

        self._thread = threading.Thread(target=run, name="workpulse-live", daemon=True)
        self._thread.start()
        ready.wait(5)

    def stop(self, reason: str = "signed_out", timeout: float = 5.0) -> None:
        loop, task = self._loop, self._task
        if loop is None or task is None or loop.is_closed():
            return

        async def shutdown() -> None:
            await self.streamer.end_all(reason, self._send if self.connected else None)
            task.cancel()

        with contextlib.suppress(Exception):
            asyncio.run_coroutine_threadsafe(shutdown(), loop).result(timeout)
        if self._thread:
            self._thread.join(timeout)
        self._loop = self._task = self._thread = None
        self.connected = False

    def end_all(self, reason: str) -> None:
        """End every stream (e.g. the work session stopped). Safe to call from any thread."""
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        future: Future[None] = asyncio.run_coroutine_threadsafe(
            self.streamer.end_all(reason, self._send if self.connected else None), loop
        )
        with contextlib.suppress(Exception):
            future.result(5)

    # ------------------------------------------------------------------ connection loop
    async def _token(self, refresh: bool) -> str | None:
        loop = asyncio.get_running_loop()
        if refresh:
            self._auth.invalidate_token()
        try:
            return await loop.run_in_executor(None, self._auth.token)
        except (NotSignedInError, ApiError, ApiUnavailable):
            return None

    async def _run(self) -> None:
        failures = 0
        refresh = False
        while True:
            token = await self._token(refresh) if self._auth.signed_in else None
            if token:
                try:
                    async with connect(
                        self._url,
                        additional_headers={"Authorization": f"Bearer {token}"},
                        open_timeout=10,
                        ping_interval=20,
                        ping_timeout=20,
                        max_size=512_000,
                    ) as socket:
                        self._socket = socket
                        self.connected = True
                        failures, refresh = 0, False
                        self.on_status()
                        logger.info("Live-view signalling connected")
                        await self._listen(socket)
                except InvalidStatus as exc:
                    refresh = exc.response.status_code in (401, 403)
                except ConnectionClosed as exc:
                    refresh = exc.rcvd is not None and exc.rcvd.code == 4401
                except (OSError, TimeoutError, WebSocketException) as exc:
                    # Includes handshakes cut short while the server or proxy restarts.
                    logger.debug("Live-view signalling unavailable: %s", exc)
                except Exception:  # never let the reconnect loop die
                    logger.exception("Unexpected live-view signalling error")
                finally:
                    if self.connected:
                        logger.info("Live-view signalling disconnected")
                    self._socket = None
                    self.connected = False
                    # The server keeps a session alive for a grace period: a quick reconnect resumes it.
                    await self.streamer.end_all("agent_error", None)
                    self.on_status()
            failures += 1
            await asyncio.sleep(min(MAX_BACKOFF, max(1.0, backoff_delay(failures, base=1.0, cap=MAX_BACKOFF))))

    async def _listen(self, socket: ClientConnection) -> None:
        async for raw in socket:
            try:
                message = json.loads(raw)
            except ValueError:
                continue
            if isinstance(message, dict) and message.get("type") not in ("hello", "pong", "error"):
                try:
                    await self.streamer.handle(message, self._send)
                except Exception:
                    logger.exception("Live-view message %s failed", message.get("type"))

    async def _send(self, message: dict[str, Any]) -> None:
        socket, lock = self._socket, self._send_lock
        if socket is None or lock is None:
            return
        async with lock:
            with contextlib.suppress(ConnectionClosed):
                await socket.send(json.dumps(message))
