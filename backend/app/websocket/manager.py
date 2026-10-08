"""Browser WebSocket connections and realtime event delivery across API processes.

Each process keeps the sockets connected *to it* (a socket can't be shared). Events are never delivered directly:
`send_to_user` / `broadcast_to_company` publish to the company's channel on the broker, and every process with
sockets for that company delivers to its own. A process subscribes to a company's channel only while it holds at
least one of that company's sockets, so traffic scales with where people are connected, not with cluster size.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any

from bson import ObjectId
from fastapi import WebSocket

from app.core.broker import Broker, MemoryBroker
from app.websocket.events import WsEvent

logger = logging.getLogger(__name__)

#: A socket that can't take a message within this time is skipped for that message (it will be closed by its own
#: handler when the connection drops); it never delays delivery to everyone else.
SEND_TIMEOUT_SECONDS = 5.0


def company_channel(company_id: ObjectId) -> str:
    return f"ws:company:{company_id}"


class ConnectionManager:
    def __init__(self, broker: Broker | None = None) -> None:
        self._broker: Broker = broker or MemoryBroker()
        self._connections: dict[ObjectId, dict[ObjectId, set[WebSocket]]] = defaultdict(
            lambda: defaultdict(set)
        )
        self._lock = asyncio.Lock()

    async def register(self, company_id: ObjectId, user_id: ObjectId, websocket: WebSocket) -> None:
        async with self._lock:
            first = company_id not in self._connections
            self._connections[company_id][user_id].add(websocket)
            if first:
                await self._broker.subscribe(company_channel(company_id), self._handler(company_id))

    async def unregister(self, company_id: ObjectId, user_id: ObjectId, websocket: WebSocket) -> None:
        async with self._lock:
            users = self._connections.get(company_id)
            if not users:
                return
            sockets = users.get(user_id)
            if sockets:
                sockets.discard(websocket)
                if not sockets:
                    users.pop(user_id, None)
            if not users:
                self._connections.pop(company_id, None)
                await self._broker.unsubscribe(company_channel(company_id))

    def _handler(self, company_id: ObjectId) -> Any:
        async def deliver(message: dict[str, Any]) -> None:
            users = self._connections.get(company_id, {})
            target = message.get("user_id")
            if target:
                sockets = list(users.get(ObjectId(target), ()))
            else:
                sockets = [ws for user in users.values() for ws in user]
            await self._deliver(sockets, message["event"])

        return deliver

    async def send_to_user(self, company_id: ObjectId, user_id: ObjectId, event: WsEvent) -> int:
        """Publish to every process; returns how many processes hold sockets for the company."""
        return await self._broker.publish(
            company_channel(company_id), {"user_id": str(user_id), "event": event.model_dump(mode="json")}
        )

    async def broadcast_to_company(self, company_id: ObjectId, event: WsEvent) -> int:
        return await self._broker.publish(
            company_channel(company_id), {"event": event.model_dump(mode="json")}
        )

    @staticmethod
    async def _deliver(sockets: list[WebSocket], message: dict[str, Any]) -> int:
        async def one(websocket: WebSocket) -> bool:
            try:
                await asyncio.wait_for(websocket.send_json(message), SEND_TIMEOUT_SECONDS)
                return True
            except Exception:
                logger.debug("Dropping message to a closed or slow socket")
                return False

        results = await asyncio.gather(*(one(ws) for ws in sockets))
        return sum(results)

    def connection_count(self, company_id: ObjectId | None = None) -> int:
        """Sockets connected to *this* process."""
        companies = [self._connections.get(company_id, {})] if company_id else self._connections.values()
        return sum(len(sockets) for users in companies for sockets in users.values())
