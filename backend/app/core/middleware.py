"""ASGI middleware: request correlation IDs, access logging and request metrics."""

from __future__ import annotations

import logging
import re
import time
from uuid import uuid4

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.exceptions import error_response
from app.core.logging import request_id_var
from app.core.observability import (
    HTTP_DURATION,
    HTTP_REQUESTS,
    WEBSOCKET_SESSIONS,
    WEBSOCKETS,
    websocket_channel,
)

logger = logging.getLogger("workpulse.access")
error_logger = logging.getLogger("workpulse.errors")

_VALID_REQUEST_ID = re.compile(r"[A-Za-z0-9\-_.]{8,64}")
_QUIET_PATHS = ("/health/live", "/metrics")


def route_template(scope: Scope) -> str:
    """The matched route's template, e.g. "/api/employees/{employee_id}" (bounded metric labels, no raw IDs).

    Included routers are mounted, so the route's own template can be relative to the mount ("/employees/{...}");
    the mount prefix is whatever part of the real path comes before the part the route matched.
    """
    route = scope.get("route")
    template: str | None = getattr(route, "path", None)
    if route is None or template is None:
        return "unmatched"
    path: str = scope.get("path", "")
    regex = getattr(route, "path_regex", None)
    if regex is None or regex.fullmatch(path):
        return template
    for index, char in enumerate(path):
        if char == "/" and index and regex.fullmatch(path[index:]):
            return f"{path[:index]}{template}"
    return template


class RequestContextMiddleware:
    """Assigns a request ID, echoes it as `X-Request-ID` and logs each request.

    Implemented as pure ASGI middleware so it does not interfere with
    streaming responses or WebSocket connections.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "websocket":
            await self._websocket(scope, receive, send)
            return
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = Headers(scope=scope).get("x-request-id")
        request_id = incoming if incoming and _VALID_REQUEST_ID.fullmatch(incoming) else uuid4().hex
        request_id_var.set(request_id)

        started = time.perf_counter()
        status_code = 500
        response_started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code, response_started
            if message["type"] == "http.response.start":
                status_code = message["status"]
                response_started = True
                MutableHeaders(scope=message).append("X-Request-ID", request_id)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            # Handled here, inside the request's context: the 500 carries the request ID, and the error is logged
            # (and so reported to error tracking) exactly once instead of again by the server.
            error_logger.exception("Unhandled exception")
            if response_started:
                raise
            await error_response(500, "internal_error", "An unexpected error occurred.")(
                scope, receive, send_wrapper
            )
        finally:
            path: str = scope.get("path", "")
            method: str = scope.get("method", "")
            elapsed = time.perf_counter() - started
            # The route template ("/api/employees/{employee_id}"), never the raw path: bounded label cardinality.
            route = route_template(scope)
            HTTP_REQUESTS.labels(method=method, route=route, status=str(status_code)).inc()
            HTTP_DURATION.labels(method=method, route=route).observe(elapsed)
            if not path.endswith(_QUIET_PATHS):
                # Query strings are deliberately not logged (they may carry tokens).
                logger.info(
                    "%s %s %s %.1fms",
                    method,
                    path,
                    status_code,
                    elapsed * 1000,
                    extra={
                        "http_method": method,
                        "http_path": path,
                        "http_route": route,
                        "http_status": status_code,
                        "duration_ms": round(elapsed * 1000, 1),
                    },
                )

    async def _websocket(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Counts open sockets per channel (app, agent_live, live_viewer) from accept until the handler returns."""
        channel = websocket_channel(scope.get("path", ""))
        accepted = False

        async def send_wrapper(message: Message) -> None:
            nonlocal accepted
            if message["type"] == "websocket.accept" and not accepted:
                accepted = True
                WEBSOCKETS.labels(channel=channel).inc()
                WEBSOCKET_SESSIONS.labels(channel=channel).inc()
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            if accepted:
                WEBSOCKETS.labels(channel=channel).dec()
