"""Desktop agent API contracts.

Events are a closed, discriminated union with `extra="forbid"`: the agent can
only report the explicit metadata listed here. There is deliberately no field
for keystrokes, window titles, URLs, clipboard contents or screen captures.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, ConfigDict, EmailStr, Field, model_validator

from app.models.organization import DeviceOs, DeviceStatus
from app.schemas.common import APIModel, ObjectIdStr
from app.schemas.live import LivePolicyOut
from app.schemas.screenshots import AgentScreenshotPolicy

PASSWORD_MAX_LENGTH = 128


class StrictModel(APIModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class DeviceInfo(StrictModel):
    name: str = Field(min_length=1, max_length=80)
    hostname: str = Field(min_length=1, max_length=255, pattern=r"^[A-Za-z0-9.\-_]+$")
    os: DeviceOs = DeviceOs.WINDOWS
    os_version: str | None = Field(default=None, max_length=60)
    agent_version: str = Field(max_length=20, pattern=r"^\d+\.\d+\.\d+([.\-+][0-9A-Za-z.\-]+)?$")
    # SHA-256 of a stable machine identifier, computed on the device; the raw identifier never leaves it.
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")


class AgentRegisterRequest(StrictModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)
    device: DeviceInfo


class AgentEnrollRequest(StrictModel):
    enrollment_code: str = Field(min_length=10, max_length=32)
    device: DeviceInfo


class ActivityPolicyOut(APIModel):
    track_applications: bool
    capture_window_titles: bool
    track_websites: bool = False
    excluded_apps: list[str]


class AgentPolicy(APIModel):
    heartbeat_interval_seconds: int
    sync_interval_seconds: int
    idle_threshold_seconds: int
    max_batch_size: int
    activity: ActivityPolicyOut
    screenshots: AgentScreenshotPolicy
    live: LivePolicyOut


class AgentEmployee(APIModel):
    id: str
    full_name: str
    email: str


class AgentCompany(APIModel):
    id: str
    name: str


class AgentIdentity(APIModel):
    device_id: str
    employee: AgentEmployee
    company: AgentCompany
    policy: AgentPolicy


class AgentCredentials(AgentIdentity):
    device_secret: str = Field(
        description="Shown once. The agent stores it encrypted; the server keeps only a hash."
    )


class AgentTokenRequest(StrictModel):
    device_id: ObjectIdStr
    device_secret: str = Field(min_length=32, max_length=128)


class AgentTokenResponse(AgentIdentity):
    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105
    expires_in: int


class HeartbeatRequest(StrictModel):
    """`presence` is null when the employee has no work session running."""

    presence: Literal["active", "idle"] | None = None
    session_id: UUID | None = None
    agent_version: str = Field(max_length=20)
    sent_at: AwareDatetime
    #: Foreground application display name; omitted when application tracking is disabled.
    current_app: str | None = Field(default=None, max_length=120)


class HeartbeatResponse(APIModel):
    server_time: datetime
    device_status: DeviceStatus
    policy: AgentPolicy


# --------------------------------------------------------------------------- events


class _Event(StrictModel):
    id: UUID
    occurred_at: AwareDatetime


class SessionStartedEvent(_Event):
    type: Literal["session.started"]
    session_id: UUID


class SessionStoppedEvent(_Event):
    type: Literal["session.stopped"]
    session_id: UUID
    reason: Literal["user", "shutdown", "sign_out", "recovered"]
    active_seconds: int = Field(ge=0, le=7 * 86_400)
    idle_seconds: int = Field(ge=0, le=7 * 86_400)


class PresenceChangedEvent(_Event):
    type: Literal["presence.changed"]
    session_id: UUID
    status: Literal["active", "idle"]


class AgentStartedEvent(_Event):
    type: Literal["agent.started"]
    agent_version: str = Field(max_length=20)


class AgentStoppedEvent(_Event):
    type: Literal["agent.stopped"]
    reason: Literal["quit", "shutdown", "sign_out"]


MAX_SEGMENT_SECONDS = 4 * 3600


DOMAIN_PATTERN = (
    r"^([A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)*[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$"
)


class ActivitySegmentEvent(_Event):
    """Foreground application usage for a span of time. `occurred_at` equals `ended_at`."""

    type: Literal["activity.segment"]
    session_id: UUID
    app_id: str = Field(min_length=1, max_length=64, pattern=r"^[\w .+()\-]+$")
    app_name: str = Field(min_length=1, max_length=120)
    window_title: str | None = Field(default=None, max_length=300)
    #: Host name only (e.g. "github.com"), never a full address; sent only when websites are tracked.
    domain: str | None = Field(default=None, max_length=253, pattern=DOMAIN_PATTERN)
    started_at: AwareDatetime
    ended_at: AwareDatetime
    active_seconds: int = Field(ge=0, le=MAX_SEGMENT_SECONDS)
    activity_level: int = Field(ge=0, le=100)

    @model_validator(mode="after")
    def _consistent(self) -> ActivitySegmentEvent:
        span = (self.ended_at - self.started_at).total_seconds()
        if span < 0:
            raise ValueError("ended_at must not be before started_at")
        if span > MAX_SEGMENT_SECONDS + 60:
            raise ValueError("segment is longer than 4 hours")
        if self.active_seconds > span + 2:
            raise ValueError("active_seconds exceeds the segment duration")
        return self


AgentEventIn = Annotated[
    SessionStartedEvent
    | SessionStoppedEvent
    | PresenceChangedEvent
    | AgentStartedEvent
    | AgentStoppedEvent
    | ActivitySegmentEvent,
    Field(discriminator="type"),
]


class EventBatch(StrictModel):
    events: list[AgentEventIn] = Field(min_length=1, max_length=500)


class RejectedEvent(APIModel):
    id: str
    reason: str


class EventBatchResult(APIModel):
    accepted: int
    duplicates: int
    rejected: list[RejectedEvent]
