"""Browser-facing protections applied to every request: cross-site request refusal and security headers.

CSRF: the API authenticates with a bearer token that scripts on other sites can't read, so classic CSRF only
concerns the endpoints that rely on the httpOnly refresh cookie (refresh, logout) and WebSockets (which browsers
open cross-site freely). Rather than reason endpoint by endpoint, every state-changing request and every WebSocket
handshake whose `Origin` is not WorkPulse's own is refused. Clients that aren't browsers (the desktop agent, scripts)
send no `Origin` and are unaffected; the refresh cookie is also `SameSite=Lax` and scoped to the auth path.
"""

from __future__ import annotations

import json
from urllib.parse import urlsplit

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import Settings

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    # API responses are data, never documents: nothing may run or be framed even if one is opened directly.
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
}


def _origin_of(url: str) -> str | None:
    parts = urlsplit(url.strip())
    if not parts.scheme or not parts.netloc:
        return None
    return f"{parts.scheme.lower()}://{parts.netloc.lower()}"


def allowed_origins(settings: Settings) -> frozenset[str]:
    origins = {o for o in (_origin_of(u) for u in [settings.frontend_url, *settings.cors_origin_list]) if o}
    return frozenset(origins)


def origin_allowed(origin: str, host: str | None, allowed: frozenset[str]) -> bool:
    candidate = _origin_of(origin)
    if candidate is None:  # "null" (sandboxed frames, file://) and garbage
        return False
    if candidate in allowed:
        return True
    if not host:
        return False
    # Same-origin requests: the page was served from the host the request is addressed to. A reverse proxy may
    # forward the host without its port (nginx `$host`), so a port-less Host matches on the host name alone.
    netloc = urlsplit(candidate).netloc
    host = host.lower()
    return netloc == host or (":" not in host and netloc.split(":")[0] == host)


class BrowserSecurityMiddleware:
    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.allowed = allowed_origins(settings)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        origin = headers.get("origin")
        checked = scope["type"] == "websocket" or scope.get("method", "GET") not in _SAFE_METHODS
        if checked and origin is not None and not origin_allowed(origin, headers.get("host"), self.allowed):
            await self._refuse(scope, send)
            return
        if scope["type"] == "websocket":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                response_headers = MutableHeaders(scope=message)
                for name, value in _HEADERS.items():
                    if name not in response_headers:
                        response_headers[name] = value
                # Workforce data must not linger in shared or browser caches unless a route says otherwise.
                if "cache-control" not in response_headers:
                    response_headers["Cache-Control"] = "no-store"
            await send(message)

        await self.app(scope, receive, send_wrapper)

    @staticmethod
    async def _refuse(scope: Scope, send: Send) -> None:
        if scope["type"] == "websocket":
            # Closing before accepting makes the server answer the handshake with 403.
            await send({"type": "websocket.close", "code": 1008, "reason": "Origin not allowed"})
            return
        body = json.dumps(
            {
                "error": {
                    "code": "origin_not_allowed",
                    "message": "Requests from other sites are not allowed.",
                    "details": None,
                },
                "request_id": None,
            }
        ).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 403,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
