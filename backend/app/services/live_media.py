"""Where a live session's media is negotiated: the seam for introducing an SFU later.

Today every session is **peer to peer**: the viewer's offer and ICE candidates go to the employee's agent,
and the agent's answer and candidates come back. Video then flows agent → browser directly (or via TURN).

An SFU deployment would add a second route without touching the session lifecycle in `LiveHub`
(authorisation, timeouts, reconnection, audit stay the same):

* the agent publishes its screen to the SFU once (an offer *to the SFU*, not to a browser);
* each viewer's offer is sent to the SFU, which answers with a subscription to that published track;
* so N viewers cost the agent one upload instead of N, and recordings or relays can hook in at the SFU.

The route a session uses is stored on the session (`media_route`) and told to the viewer in the `ready`
message, so clients and audit records always know which path the video took.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from app.services.live_hub import LiveHub, Runtime

PEER_TO_PEER = "p2p"


class MediaRoute(Protocol):
    """Delivers the viewer's half of the WebRTC negotiation to whatever produces the media."""

    name: str

    async def viewer_offer(self, hub: LiveHub, rt: Runtime, sdp: str) -> bool:
        """Forward an offer. Returns False when the media producer can't be reached right now."""
        ...

    async def viewer_candidate(self, hub: LiveHub, rt: Runtime, candidate: dict[str, Any] | None) -> None: ...


class PeerToPeerRoute:
    """The agent answers the viewer directly; the API only relays signalling."""

    name = PEER_TO_PEER

    async def viewer_offer(self, hub: LiveHub, rt: Runtime, sdp: str) -> bool:
        return await hub.send_to_agent(
            rt,
            {
                "type": "offer",
                "session_id": str(rt.session_id),
                "sdp": sdp,
                "viewer_name": rt.viewer_name,
                "expires_at": rt.expires_at.isoformat(),
                "ice_servers": hub.ice_servers(f"agent-{rt.device_id}"),
            },
        )

    async def viewer_candidate(self, hub: LiveHub, rt: Runtime, candidate: dict[str, Any] | None) -> None:
        await hub.send_to_agent(
            rt, {"type": "candidate", "session_id": str(rt.session_id), "candidate": candidate}
        )
