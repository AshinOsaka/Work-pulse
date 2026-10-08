"""Desktop agent API.

Public endpoints exchange employee credentials or an enrolment code for a
device secret, and the device secret for short-lived device tokens. All other
endpoints require a device token (separate audience from user tokens).
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import AgentServiceDep, RequestMetaDep
from app.auth.device_auth import CurrentDevice
from app.schemas.agent import (
    AgentCredentials,
    AgentEnrollRequest,
    AgentIdentity,
    AgentRegisterRequest,
    AgentTokenRequest,
    AgentTokenResponse,
    EventBatch,
    EventBatchResult,
    HeartbeatRequest,
    HeartbeatResponse,
)

router = APIRouter(prefix="/agent", tags=["agent"])


@router.post(
    "/register", response_model=AgentCredentials, summary="Register this device by signing in as the employee"
)
async def register(
    payload: AgentRegisterRequest, service: AgentServiceDep, meta: RequestMetaDep
) -> AgentCredentials:
    """Returns a device secret (shown once). Re-registering the same machine rotates its secret."""
    return await service.register(payload, meta)


@router.post(
    "/enroll", response_model=AgentCredentials, summary="Register this device with an enrolment code"
)
async def enroll(
    payload: AgentEnrollRequest, service: AgentServiceDep, meta: RequestMetaDep
) -> AgentCredentials:
    return await service.enroll(payload, meta)


@router.post(
    "/token", response_model=AgentTokenResponse, summary="Exchange device credentials for an access token"
)
async def token(payload: AgentTokenRequest, service: AgentServiceDep) -> AgentTokenResponse:
    return await service.issue_token(payload)


@router.get("/me", response_model=AgentIdentity)
async def me(device: CurrentDevice, service: AgentServiceDep) -> AgentIdentity:
    return await service.identity(device)


@router.post("/heartbeat", response_model=HeartbeatResponse)
async def heartbeat(
    payload: HeartbeatRequest, device: CurrentDevice, service: AgentServiceDep, meta: RequestMetaDep
) -> HeartbeatResponse:
    """Marks the device online and reports its current presence."""
    return await service.heartbeat(device, payload, meta)


@router.post("/events", response_model=EventBatchResult)
async def events(payload: EventBatch, device: CurrentDevice, service: AgentServiceDep) -> EventBatchResult:
    """Ingest a batch of queued events. Idempotent per event id, so retries are always safe."""
    return await service.ingest(device, payload)
