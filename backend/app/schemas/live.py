"""Live screen viewing: policy, discovery, sessions and the signalling messages."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.live import LiveEventType, LiveStatus
from app.schemas.common import APIModel
from app.schemas.organization import EmployeeRef, Ref

MAX_SDP = 100_000
MAX_CANDIDATE = 2_000

Availability = Literal["available", "offline", "not_working", "in_session", "disabled"]


class LivePolicyOut(APIModel):
    enabled: bool
    max_session_minutes: int


class LivePolicyUpdate(APIModel):
    enabled: bool | None = None
    max_session_minutes: int | None = Field(default=None, ge=1, le=240)


class IceServer(APIModel):
    urls: list[str]
    username: str | None = None
    credential: str | None = None


class LiveSessionRef(APIModel):
    id: str
    status: LiveStatus
    viewer_name: str
    #: The session belongs to the requesting viewer (they can rejoin it).
    mine: bool


class LiveDevice(APIModel):
    id: str
    name: str
    os: str
    #: The agent's last heartbeat.
    last_seen_at: datetime | None = None


class LiveEmployee(APIModel):
    employee: EmployeeRef
    department: Ref | None
    team: Ref | None
    device: LiveDevice | None
    #: The agent's signalling channel is connected.
    online: bool
    #: A work session is running ("active" or "idle"), or None.
    presence: Literal["active", "idle"] | None
    current_app: str | None
    status_since: datetime | None
    live_session: LiveSessionRef | None
    availability: Availability


class LiveEmployeeList(APIModel):
    enabled: bool
    max_session_minutes: int
    employees: list[LiveEmployee]


class LiveSessionCreate(APIModel):
    employee_id: str = Field(pattern=r"^[0-9a-f]{24}$")
    #: Optional: a specific registered device of this employee. Without it, their working, online device is used.
    device_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{24}$")


#: Where the WebRTC connection stands, derived from the session status.
SessionConnectionState = Literal["waiting_for_peer", "negotiating", "connected", "reconnecting", "closed"]

CONNECTION_STATE: dict[LiveStatus, SessionConnectionState] = {
    LiveStatus.REQUESTED: "waiting_for_peer",
    LiveStatus.CONNECTING: "negotiating",
    LiveStatus.LIVE: "connected",
    LiveStatus.INTERRUPTED: "reconnecting",
    LiveStatus.ENDED: "closed",
}


class LiveSessionOut(APIModel):
    id: str
    status: LiveStatus
    employee: EmployeeRef
    device: LiveDevice | None
    viewer_name: str
    created_at: datetime
    connected_at: datetime | None
    expires_at: datetime
    ended_at: datetime | None
    end_reason: str | None
    duration_seconds: int | None
    reconnects: int
    media_route: str
    connection_state: SessionConnectionState


class LiveSessionList(APIModel):
    items: list[LiveSessionOut]


class LiveSessionEventOut(APIModel):
    id: str
    event: LiveEventType
    actor_role: str
    actor_id: str | None
    metadata: dict[str, Any]
    timestamp: datetime


class LiveSessionEventList(APIModel):
    session_id: str
    items: list[LiveSessionEventOut]


# --------------------------------------------------------------------------- signalling messages
class _Message(BaseModel):
    model_config = ConfigDict(extra="forbid")


class IceCandidate(_Message):
    candidate: str = Field(max_length=MAX_CANDIDATE)
    sdpMid: str | None = Field(default=None, max_length=64)
    sdpMLineIndex: int | None = Field(default=None, ge=0, le=64)
    usernameFragment: str | None = Field(default=None, max_length=256)


ConnectionState = Literal["new", "connecting", "connected", "disconnected", "failed", "closed"]


class ViewerOffer(_Message):
    type: Literal["offer"]
    sdp: str = Field(max_length=MAX_SDP)


class ViewerCandidate(_Message):
    type: Literal["candidate"]
    candidate: IceCandidate | None


class ViewerState(_Message):
    type: Literal["state"]
    state: ConnectionState


class ViewerStop(_Message):
    type: Literal["stop"]


class Ping(_Message):
    type: Literal["ping"]


ViewerMessage = Annotated[
    ViewerOffer | ViewerCandidate | ViewerState | ViewerStop | Ping, Field(discriminator="type")
]


class AgentAnswer(_Message):
    type: Literal["answer"]
    session_id: str = Field(max_length=24)
    sdp: str = Field(max_length=MAX_SDP)


class AgentCandidate(_Message):
    type: Literal["candidate"]
    session_id: str = Field(max_length=24)
    candidate: IceCandidate | None


class AgentState(_Message):
    type: Literal["state"]
    session_id: str = Field(max_length=24)
    state: ConnectionState


class AgentEnded(_Message):
    type: Literal["ended"]
    session_id: str = Field(max_length=24)
    reason: Literal[
        "work_session_stopped",
        "not_working",
        "capture_failed",
        "agent_error",
        "max_duration",
        "signed_out",
        "agent_stopped",
    ]


AgentMessage = Annotated[
    AgentAnswer | AgentCandidate | AgentState | AgentEnded | Ping, Field(discriminator="type")
]
