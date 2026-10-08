"""AI assistant: status, conversations, and asking (answers stream as server-sent events)."""

from __future__ import annotations

from fastapi import APIRouter, Response, status
from fastapi.responses import StreamingResponse

from app.api.deps import AssistantServiceDep
from app.auth.dependencies import CurrentPrincipal
from app.schemas.assistant import AskRequest, AssistantStatus, ConversationOut, ConversationSummary
from app.services.assistant.service import SUGGESTIONS

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.get("/status", response_model=AssistantStatus)
async def assistant_status(principal: CurrentPrincipal, service: AssistantServiceDep) -> AssistantStatus:
    service.require(principal)
    return AssistantStatus(
        configured=service.configured,
        model=service._claude.model if service.configured else None,
        suggestions=SUGGESTIONS,
    )


@router.get("/conversations", response_model=list[ConversationSummary])
async def conversations(
    principal: CurrentPrincipal, service: AssistantServiceDep
) -> list[ConversationSummary]:
    return [
        ConversationSummary(
            id=str(c.id),
            title=c.title,
            updated_at=c.updated_at,
            questions=sum(1 for t in c.turns if t.get("role") == "user"),
        )
        for c in await service.list(principal)
    ]


@router.get("/conversations/{conversation_id}", response_model=ConversationOut)
async def conversation(
    conversation_id: str, principal: CurrentPrincipal, service: AssistantServiceDep
) -> ConversationOut:
    c = await service.get(principal, conversation_id)
    return ConversationOut(
        id=str(c.id), title=c.title, created_at=c.created_at, updated_at=c.updated_at, turns=c.turns
    )


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: str, principal: CurrentPrincipal, service: AssistantServiceDep
) -> Response:
    await service.delete(principal, conversation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/conversations", status_code=status.HTTP_204_NO_CONTENT)
async def clear_history(principal: CurrentPrincipal, service: AssistantServiceDep) -> Response:
    await service.delete(principal, None)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/ask", summary="Ask a question; the answer streams as server-sent events")
async def ask(
    payload: AskRequest, principal: CurrentPrincipal, service: AssistantServiceDep
) -> StreamingResponse:
    """Events: start, text (deltas), tool (running/done/error), card (data cards), error, done."""
    conversation = await service.prepare(principal, payload.conversation_id, payload.message)
    return StreamingResponse(
        service.stream(principal, conversation, payload.message),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
