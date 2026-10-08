"""Keeps long-lived browser WebSockets tied to a live sign-in.

A socket is authorised once, when it connects. This guard re-checks the session and the account every few seconds
and closes the socket when the session was signed out or revoked, or the person was suspended, so a revoked session
can't keep receiving realtime events or a live stream. It works across API processes (the check reads MongoDB).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from typing import Any

from fastapi import WebSocket
from pymongo.asynchronous.database import AsyncDatabase

from app.auth.principal import Principal
from app.models.user import UserStatus
from app.repositories.security import AuthSessionRepository
from app.repositories.user import UserRepository

logger = logging.getLogger(__name__)

#: Close code for "your session ended" (4000-4999 are application-defined).
WS_SESSION_ENDED = 4401


async def still_signed_in(db: AsyncDatabase[dict[str, Any]], principal: Principal) -> bool:
    if principal.session_id is None:
        return False
    session = await AuthSessionRepository(db).find_active(principal.session_id)
    if session is None or session.user_id != principal.user_id:
        return False
    user = await UserRepository(db).get_by_id(principal.company_id, principal.user_id)
    return user is not None and user.status == UserStatus.ACTIVE


async def _watch(websocket: WebSocket, principal: Principal, interval: float) -> None:
    db = websocket.app.state.mongo.db
    while True:
        await asyncio.sleep(interval)
        try:
            alive = await still_signed_in(db, principal)
        except Exception:  # a database hiccup must not drop everyone's connection
            logger.warning("Session check failed; keeping the socket for now", exc_info=True)
            continue
        if not alive:
            with contextlib.suppress(Exception):
                await websocket.close(code=WS_SESSION_ENDED, reason="Session ended")
            return


@contextlib.asynccontextmanager
async def session_guard(websocket: WebSocket, principal: Principal) -> AsyncIterator[None]:
    interval = float(websocket.app.state.settings.session_check_seconds)
    task = asyncio.create_task(_watch(websocket, principal, interval), name="ws-session-guard")
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
