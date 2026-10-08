"""Authenticated WebSocket gateway.

Phase 1 provides the transport only: authentication, connection registry and
a ping/pong heartbeat. Domain events are added in later phases.

Browsers cannot set headers on WebSocket requests, so the short-lived access
token is passed as the ``token`` query parameter (query strings are excluded
from access logs).
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.auth.dependencies import resolve_principal
from app.core.exceptions import AppError
from app.websocket.auth import websocket_credentials
from app.websocket.events import EventType, WsEvent
from app.websocket.guard import session_guard
from app.websocket.manager import ConnectionManager

logger = logging.getLogger(__name__)

#: RFC 6455 "Try Again Later": the server can't serve the socket right now (e.g. Redis is unreachable).
WS_TRY_AGAIN_LATER = 1013

router = APIRouter()


@router.websocket("/ws")
async def websocket_gateway(websocket: WebSocket) -> None:
    token, subprotocol = websocket_credentials(websocket)
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Authentication required")
        return
    try:
        principal = await resolve_principal(token, websocket.app.state.settings, websocket.app.state.mongo.db)
    except AppError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid token")
        return

    manager: ConnectionManager = websocket.app.state.ws_manager
    await websocket.accept(subprotocol=subprotocol)
    try:
        await manager.register(principal.company_id, principal.user_id, websocket)
    except Exception:
        # Redis unreachable: tell the browser to come back later (it reconnects with back-off).
        logger.warning("Realtime registration failed; asking the client to retry")
        await websocket.close(code=WS_TRY_AGAIN_LATER, reason="Realtime temporarily unavailable")
        return
    await websocket.send_json(
        WsEvent(type=EventType.CONNECTION_READY, payload={"user_id": str(principal.user_id)}).model_dump(
            mode="json"
        )
    )

    try:
        async with session_guard(websocket, principal):
            await _serve(websocket)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        await manager.unregister(principal.company_id, principal.user_id, websocket)


async def _serve(websocket: WebSocket) -> None:
    """Answer pings; everything else the gateway pushes is server-to-client."""
    while True:
        raw = await websocket.receive_text()
        try:
            event = WsEvent.model_validate(json.loads(raw))
        except (ValueError, TypeError):
            await websocket.send_json(
                WsEvent(type=EventType.ERROR, payload={"code": "invalid_message"}).model_dump(mode="json")
            )
            continue

        if event.type == EventType.PING:
            await websocket.send_json(WsEvent(type=EventType.PONG).model_dump(mode="json"))
        else:
            await websocket.send_json(
                WsEvent(
                    type=EventType.ERROR,
                    payload={"code": "unsupported_event", "event": event.type},
                ).model_dump(mode="json")
            )
