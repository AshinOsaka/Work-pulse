"""How browsers authenticate WebSockets without putting the access token in the URL.

Browsers can't set headers on a WebSocket, so the token travels as a subprotocol: the client offers
`["workpulse.v1", "bearer.<access token>"]` and the server answers with `workpulse.v1` (never echoing the token).
URLs end up in proxy error logs and browser history; the `Sec-WebSocket-Protocol` header does not.

`?token=` is still accepted for older clients and scripts. The desktop agent uses an `Authorization` header.
"""

from __future__ import annotations

from fastapi import WebSocket

SUBPROTOCOL = "workpulse.v1"
BEARER_PREFIX = "bearer."


def websocket_credentials(websocket: WebSocket) -> tuple[str | None, str | None]:
    """The access token, and the subprotocol to accept (None when the client offered none)."""
    offered: list[str] = list(websocket.scope.get("subprotocols") or [])
    for protocol in offered:
        if protocol.startswith(BEARER_PREFIX) and len(protocol) > len(BEARER_PREFIX):
            return protocol[len(BEARER_PREFIX) :], SUBPROTOCOL if SUBPROTOCOL in offered else None
    return websocket.query_params.get("token"), None
