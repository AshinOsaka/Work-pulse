"""Live screen viewing: policy, online employees, sessions, and the two signalling WebSockets.

* Viewer: ``/live/sessions/{id}/ws?token=<access token>`` — browsers can't set headers on WebSockets.
* Agent:  ``/agent/live`` with ``Authorization: Bearer <device token>``.
"""

from __future__ import annotations

import json
import logging
from typing import Annotated, Any

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect, status
from pydantic import TypeAdapter, ValidationError

from app.api.deps import LiveServiceDep, RequestMetaDep
from app.auth.dependencies import CurrentPrincipal, require_permissions, resolve_principal
from app.auth.device_auth import resolve_device
from app.auth.permissions import Permission
from app.auth.principal import Principal
from app.core.exceptions import AppError
from app.schemas.live import (
    AgentMessage,
    LiveEmployeeList,
    LivePolicyOut,
    LivePolicyUpdate,
    LiveSessionCreate,
    LiveSessionEventList,
    LiveSessionList,
    LiveSessionOut,
    ViewerMessage,
)
from app.services.live_hub import (
    MAX_MESSAGE_BYTES,
    MAX_MESSAGES_PER_MINUTE,
    AgentLink,
    Link,
    LiveHub,
    RateLimiter,
)
from app.websocket.auth import websocket_credentials
from app.websocket.guard import session_guard
from app.websocket.router import WS_TRY_AGAIN_LATER

logger = logging.getLogger(__name__)

router = APIRouter(tags=["live"])

LiveViewer = Annotated[Principal, Depends(require_permissions(Permission.LIVE_STREAM_VIEW))]
_viewer_messages: TypeAdapter[Any] = TypeAdapter(ViewerMessage)
_agent_messages: TypeAdapter[Any] = TypeAdapter(AgentMessage)

WS_UNAUTHORIZED = 4401
WS_FORBIDDEN = 4403
WS_NOT_FOUND = 4404


# --------------------------------------------------------------------------- REST
@router.get(
    "/companies/current/live-policy",
    response_model=LivePolicyOut,
    summary="Live viewing policy (all members)",
)
async def get_live_policy(principal: CurrentPrincipal, service: LiveServiceDep) -> LivePolicyOut:
    return await service.get_policy(principal)


@router.patch("/companies/current/live-policy", response_model=LivePolicyOut)
async def update_live_policy(
    payload: LivePolicyUpdate,
    principal: Annotated[Principal, Depends(require_permissions(Permission.POLICY_MANAGE))],
    service: LiveServiceDep,
    meta: RequestMetaDep,
) -> LivePolicyOut:
    """Turning live viewing off ends every stream in progress."""
    return await service.update_policy(principal, payload, meta)


@router.get(
    "/live/employees", response_model=LiveEmployeeList, summary="Employees in scope with live availability"
)
async def live_employees(principal: LiveViewer, service: LiveServiceDep) -> LiveEmployeeList:
    return await service.employees(principal)


@router.post("/live/sessions", response_model=LiveSessionOut, status_code=status.HTTP_201_CREATED)
async def start_live_session(
    payload: LiveSessionCreate, principal: LiveViewer, service: LiveServiceDep, meta: RequestMetaDep
) -> LiveSessionOut:
    """Request a stream (audited). Then open the session WebSocket and send a WebRTC offer."""
    return await service.start(principal, payload.employee_id, meta, payload.device_id)


@router.get("/live/sessions", response_model=LiveSessionList, summary="Live session log (newest first)")
async def list_live_sessions(
    principal: LiveViewer,
    service: LiveServiceDep,
    employee_id: Annotated[str | None, Query(pattern=r"^[0-9a-f]{24}$")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> LiveSessionList:
    return await service.history(principal, employee_id, limit)


@router.get("/live/sessions/{session_id}", response_model=LiveSessionOut)
async def get_live_session(session_id: str, principal: LiveViewer, service: LiveServiceDep) -> LiveSessionOut:
    return await service.get(principal, session_id)


@router.get(
    "/live/sessions/{session_id}/events",
    response_model=LiveSessionEventList,
    summary="The session's timeline (requested, authorized, connecting, started, disconnected, stopped…)",
)
async def live_session_events(
    session_id: str, principal: LiveViewer, service: LiveServiceDep
) -> LiveSessionEventList:
    return await service.events(principal, session_id)


@router.post("/live/sessions/{session_id}/stop", response_model=LiveSessionOut)
async def stop_live_session(
    session_id: str, principal: LiveViewer, service: LiveServiceDep
) -> LiveSessionOut:
    return await service.stop(principal, session_id)


# --------------------------------------------------------------------------- signalling
async def _receive(
    websocket: WebSocket, limiter: RateLimiter, adapter: TypeAdapter[Any]
) -> dict[str, Any] | None:
    """One validated message, or None for a message that was rejected (the caller keeps listening)."""
    raw = await websocket.receive_text()
    if len(raw) > MAX_MESSAGE_BYTES or not limiter.allow():
        await websocket.send_json({"type": "error", "code": "message_rejected"})
        return None
    try:
        message = adapter.validate_python(json.loads(raw))
    except (ValueError, ValidationError):
        await websocket.send_json({"type": "error", "code": "invalid_message"})
        return None
    data: dict[str, Any] = message.model_dump()
    if isinstance(data.get("candidate"), dict):  # forward exactly what the browser/agent understands
        data["candidate"] = {k: v for k, v in data["candidate"].items() if v is not None}
    return data


@router.websocket("/live/sessions/{session_id}/ws")
@router.websocket("/live/signaling/{session_id}")
async def viewer_socket(websocket: WebSocket, session_id: str) -> None:
    hub: LiveHub = websocket.app.state.live_hub
    token, subprotocol = websocket_credentials(websocket)
    if not token:
        await websocket.close(code=WS_UNAUTHORIZED, reason="Authentication required")
        return
    try:
        principal = await resolve_principal(token, websocket.app.state.settings, websocket.app.state.mongo.db)
        oid = ObjectId(session_id)
    except (AppError, InvalidId, TypeError):
        await websocket.close(code=WS_UNAUTHORIZED, reason="Invalid token")
        return
    if Permission.LIVE_STREAM_VIEW not in principal.permissions:
        await websocket.close(code=WS_FORBIDDEN, reason="Not allowed")
        return
    # Only the requesting viewer may join, and only while a live process is running the session.
    if await hub.viewable(oid, principal.company_id, principal.user_id) is None:
        await websocket.close(code=WS_NOT_FOUND, reason="Session not available")
        return

    await websocket.accept(subprotocol=subprotocol)
    link = Link(websocket)
    try:
        await hub.attach_viewer(oid, link)
    except Exception:
        await link.close(code=WS_TRY_AGAIN_LATER, reason="Live viewing temporarily unavailable")
        return
    limiter = RateLimiter(MAX_MESSAGES_PER_MINUTE)
    try:
        # Signing out (or being suspended) mid-stream closes the viewer socket, which ends the stream.
        async with session_guard(websocket, principal):
            while True:
                message = await _receive(websocket, limiter, _viewer_messages)
                if message is not None:
                    await hub.from_viewer(oid, link, message)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        hub.detach_soon(hub.detach_viewer(oid, link))


@router.websocket("/agent/live")
async def agent_socket(websocket: WebSocket) -> None:
    hub: LiveHub = websocket.app.state.live_hub
    header = websocket.headers.get("authorization", "")
    token = header[7:] if header.lower().startswith("bearer ") else ""
    if not token:
        await websocket.close(code=WS_UNAUTHORIZED, reason="Device authentication required")
        return
    try:
        ctx = await resolve_device(token, websocket.app.state.settings, websocket.app.state.mongo.db)
    except AppError as exc:
        await websocket.close(code=WS_UNAUTHORIZED, reason=exc.code)
        return

    await websocket.accept()
    link = AgentLink(
        websocket, company_id=ctx.company_id, device_id=ctx.device.id, employee_id=ctx.employee.id
    )
    try:
        await hub.attach_agent(link)
    except Exception:
        # Redis unreachable: the agent reconnects with back-off.
        await link.close(code=WS_TRY_AGAIN_LATER, reason="Live viewing temporarily unavailable")
        return
    await link.send({"type": "hello", "device_id": str(ctx.device.id)})
    limiter = RateLimiter(MAX_MESSAGES_PER_MINUTE)
    try:
        while True:
            message = await _receive(websocket, limiter, _agent_messages)
            if message is not None:
                await hub.from_agent(link, message)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        hub.detach_soon(hub.detach_agent(link))
