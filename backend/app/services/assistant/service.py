"""The WorkPulse assistant: Claude answering from WorkPulse data only, through read-only tools.

Grounding:
* The model has no database access; it can only call the tools in `tools.py`, which run as the requester (same
  permissions and scope as the web app). The system prompt requires every figure to come from a tool result, with its
  period, metrics and source, and forbids judgements about people.
* Numbers shown in data cards come straight from the tools, not from model text.

Conversation integrity (Claude Opus 5.5 binds thinking blocks to the conversation that produced them):
* The system prompt and the tool list are fixed; the current date/time travels in each user turn instead.
* Assistant content (thinking, text, tool calls, fallback blocks) is stored exactly as returned and replayed unchanged;
  the transcript is append-only. "Clear conversation" starts a new one rather than editing history.

Requests use adaptive thinking (the only mode on this model), explicit effort, streaming, prompt caching, and
server-side refusal fallbacks (`fallbacks: "default"`).
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections import defaultdict, deque
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import anthropic

from app.auth.permissions import Permission
from app.auth.principal import Principal
from app.core.config import Settings
from app.core.exceptions import (
    ForbiddenError,
    NotFoundError,
    ServiceUnavailableError,
    TooManyRequestsError,
)
from app.models.assistant import Conversation
from app.repositories.assistant import ConversationRepository
from app.services.assistant.tools import (
    TOOL_DEFINITIONS,
    TOOL_LABELS,
    AssistantServices,
    AssistantTools,
    ToolError,
)
from app.services.audit_service import AuditService
from app.services.helpers import parse_id
from app.utils.time import utcnow

logger = logging.getLogger(__name__)

FALLBACK_BETA = "server-side-fallback-2026-07-01"
MAX_TOOL_ROUNDS = 8
MAX_JSON_RETRIES = 2
RATE_WINDOW_SECONDS = 3600

SYSTEM_PROMPT = """You are the WorkPulse assistant. You help managers understand recorded work signals in their WorkPulse \
workspace: presence, work sessions, application activity, projects, tasks, attendance and alerts.

Grounding rules - these matter more than anything else:
- You can only know what the tools return. Never state a number, name, date, status or event that is not in a tool \
result from this conversation. If the tools can't answer, say so plainly and suggest where in WorkPulse to look.
- Call tools for every factual question, even if you answered something similar earlier, so figures are current.
- Every answer states the time period it covers, the metrics it is based on, and the data source (each tool result \
includes a `source`). Times are in the workspace time zone given with each question.
- Link to the relevant page using the `link` values from tool results, as Markdown links such as \
[Open Live Tracking](/live). Only use links that appear in tool results.
- The person sees each tool's data card (tables, numbers, charts) next to your answer. Summarise and point out what \
stands out; don't repeat whole tables.

People:
- Describe recorded work signals, not people. Never make claims or guesses about anyone's character, intent, \
honesty, effort, motivation, mental or physical health, intelligence, or personal circumstances, and don't rank \
people against each other. Activity data misses meetings, calls, thinking and offline work; when it matters, say so.
- If asked for a judgement of a person ("is X lazy", "who is the worst"), explain that WorkPulse data can't answer \
that, and offer the factual signals instead.
- Follow the caveats in tool results (for example, attendance has no leave or shift records).

Style: concise and clear. Lead with the answer, then a few supporting points. Use Markdown lists and bold sparingly. \
No tables in your text (the cards have them)."""

SUGGESTIONS = [
    "What happened today?",
    "How many employees are currently active?",
    "Summarize today's team activity.",
    "How much time was spent on Website relaunch this month?",
    "Which tasks are overdue?",
    "Show this week's attendance summary.",
]


@dataclass
class AssistantClient:
    """The Claude client (None when no API key is configured)."""

    client: Any
    model: str


def build_client(settings: Settings) -> AssistantClient:
    key = settings.anthropic_api_key.get_secret_value() if settings.anthropic_api_key else ""
    client = anthropic.AsyncAnthropic(api_key=key, max_retries=2, timeout=120.0) if key else None
    return AssistantClient(client=client, model=settings.assistant_model)


class RateLimiter:
    """Per-user questions per hour, in process (the API runs as one instance; see the scaling note in docs)."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str, limit: int) -> bool:
        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] > RATE_WINDOW_SECONDS:
            hits.popleft()
        if len(hits) >= limit:
            return False
        hits.append(now)
        return True


def sse(event: dict[str, Any]) -> bytes:
    return f"data: {json.dumps(event, default=str)}\n\n".encode()


def _block_dict(block: Any) -> dict[str, Any]:
    """Assistant content as plain JSON, exactly as returned (replayed unchanged on the next request)."""
    data: dict[str, Any] = block.to_dict() if hasattr(block, "to_dict") else dict(block)
    return data


class AssistantService:
    def __init__(
        self,
        *,
        settings: Settings,
        conversations: ConversationRepository,
        services: AssistantServices,
        audit: AuditService,
        claude: AssistantClient,
        limiter: RateLimiter,
    ) -> None:
        self._settings = settings
        self._conversations = conversations
        self._services = services
        self._audit = audit
        self._claude = claude
        self._limiter = limiter

    @staticmethod
    def require(principal: Principal) -> None:
        if not principal.has(Permission.REPORT_VIEW):
            raise ForbiddenError(
                "The assistant is available to people who can view reports.", code="insufficient_permissions"
            )

    @property
    def configured(self) -> bool:
        return self._claude.client is not None

    # ------------------------------------------------------------------ conversations
    async def list(self, principal: Principal) -> list[Conversation]:
        self.require(principal)
        return await self._conversations.for_user(principal.company_id, principal.user_id)

    async def get(self, principal: Principal, conversation_id: str) -> Conversation:
        self.require(principal)
        oid = parse_id(conversation_id, not_found="Conversation not found.", code="conversation_not_found")
        found = await self._conversations.own(principal.company_id, principal.user_id, oid)
        if found is None:
            raise NotFoundError("Conversation not found.", code="conversation_not_found")
        return found

    async def delete(self, principal: Principal, conversation_id: str | None) -> int:
        self.require(principal)
        if conversation_id is None:
            return await self._conversations.delete_all(principal.company_id, principal.user_id)
        conversation = await self.get(principal, conversation_id)
        await self._conversations.delete_by_id(principal.company_id, conversation.id)
        return 1

    # ------------------------------------------------------------------ asking
    async def prepare(self, principal: Principal, conversation_id: str | None, question: str) -> Conversation:
        """Checks that run before the response starts streaming (so they can still be HTTP errors)."""
        self.require(principal)
        if not self.configured:
            raise ServiceUnavailableError(
                "The assistant isn't configured: an administrator needs to set ANTHROPIC_API_KEY.",
                code="assistant_not_configured",
            )
        if not self._limiter.allow(str(principal.user_id), self._settings.assistant_questions_per_hour):
            raise TooManyRequestsError(
                "You've reached the hourly question limit. Try again a little later.", retry_after=600
            )
        if conversation_id:
            return await self.get(principal, conversation_id)
        conversation = Conversation(
            company_id=principal.company_id, user_id=principal.user_id, title=question.strip()[:80]
        )
        await self._conversations.create(principal.company_id, conversation)
        return conversation

    async def _context_line(self, tools: AssistantTools) -> str:
        tz = await tools.tz()
        now = utcnow().astimezone(tz)
        return (
            f"[Context: it is {now.strftime('%A %d %B %Y, %H:%M')} in the workspace time zone ({tz.key}). "
            f"The person asking is {tools.p.user.full_name} ({tools.p.user.role.value.replace('_', ' ').lower()}).]"
        )

    async def stream(
        self, principal: Principal, conversation: Conversation, question: str
    ) -> AsyncIterator[bytes]:
        tools = AssistantTools(self._services, principal)
        turn_id = uuid.uuid4().hex
        user_message = {
            "role": "user",
            "content": [
                {"type": "text", "text": await self._context_line(tools)},
                {"type": "text", "text": question.strip()},
            ],
        }
        user_turn = {
            "id": uuid.uuid4().hex,
            "role": "user",
            "text": question.strip(),
            "created_at": utcnow().isoformat(),
        }
        history = [*conversation.transcript, user_message]
        new_transcript: list[dict[str, Any]] = [user_message]
        text_parts: list[str] = []
        cards: list[dict[str, Any]] = []
        used: list[dict[str, Any]] = []
        error: str | None = None
        yield sse(
            {
                "type": "start",
                "conversation_id": str(conversation.id),
                "turn_id": turn_id,
                "title": conversation.title,
            }
        )
        try:
            json_retries = 0
            for _round in range(MAX_TOOL_ROUNDS):
                try:
                    message = None
                    async with self._claude.client.beta.messages.stream(
                        model=self._claude.model,
                        max_tokens=32000,
                        system=SYSTEM_PROMPT,
                        tools=TOOL_DEFINITIONS,
                        messages=history,
                        thinking={"type": "adaptive"},
                        output_config={"effort": self._settings.assistant_effort},
                        cache_control={"type": "ephemeral"},
                        betas=[FALLBACK_BETA],
                        fallbacks="default",
                    ) as stream:
                        async for event in stream:
                            if event.type == "text":
                                text_parts.append(event.text)
                                yield sse({"type": "text", "delta": event.text})
                        message = await stream.get_final_message()
                    json_retries = 0
                except ValueError:
                    # A tool input the SDK could not parse at all: re-issue the turn (bounded).
                    json_retries += 1
                    if json_retries > MAX_JSON_RETRIES:
                        raise
                    continue
                content = [_block_dict(b) for b in message.content]
                assistant_message = {"role": "assistant", "content": content}
                history.append(assistant_message)
                new_transcript.append(assistant_message)
                if message.stop_reason == "refusal":
                    error = "The assistant can't help with that request."
                    break
                tool_uses = [b for b in message.content if b.type == "tool_use"]
                if message.stop_reason == "pause_turn":
                    continue
                if not tool_uses:
                    break
                if message.stop_reason == "max_tokens":
                    error = "The answer was cut short. Try a narrower question."
                    break
                results = []
                for block in tool_uses:
                    label = TOOL_LABELS.get(block.name, block.name)
                    yield sse(
                        {
                            "type": "tool",
                            "id": block.id,
                            "name": block.name,
                            "label": label,
                            "status": "running",
                        }
                    )
                    try:
                        result = await tools.run(block.name, block.input)
                        results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": json.dumps(result.facts, default=str),
                            }
                        )
                        for card in result.cards:
                            card = {"id": uuid.uuid4().hex, **card}
                            cards.append(card)
                            yield sse({"type": "card", "card": card})
                        used.append({"name": block.name, "label": label, "status": "done"})
                        yield sse(
                            {
                                "type": "tool",
                                "id": block.id,
                                "name": block.name,
                                "label": label,
                                "status": "done",
                            }
                        )
                    except ToolError as exc:
                        results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": str(exc),
                                "is_error": True,
                            }
                        )
                        used.append(
                            {"name": block.name, "label": label, "status": "error", "message": str(exc)}
                        )
                        yield sse(
                            {
                                "type": "tool",
                                "id": block.id,
                                "name": block.name,
                                "label": label,
                                "status": "error",
                                "message": str(exc),
                            }
                        )
                tool_message = {"role": "user", "content": results}
                history.append(tool_message)
                new_transcript.append(tool_message)
            else:
                error = "This question needed too many steps. Try asking something more specific."
        except anthropic.RateLimitError:
            error = "The AI service is busy. Please try again in a minute."
        except anthropic.APIStatusError as exc:
            logger.warning("Assistant request failed: %s %s", exc.status_code, getattr(exc, "message", ""))
            error = "The AI service returned an error. Please try again."
        except anthropic.APIConnectionError:
            error = "Couldn't reach the AI service. Please try again."
        except Exception:
            logger.exception("Assistant turn failed")
            error = "Something went wrong while answering. Please try again."

        assistant_turn = {
            "id": turn_id,
            "role": "assistant",
            "text": "".join(text_parts),
            "cards": cards,
            "tools": used,
            "error": error,
            "created_at": utcnow().isoformat(),
        }
        # Only a cleanly finished turn joins the transcript that is replayed to the model; a refused, cut-short or
        # failed turn is still shown to the person (in `turns`) but never half-written into the model's history.
        complete = error is None and len(new_transcript) > 1 and new_transcript[-1]["role"] == "assistant"
        await self._conversations.append(
            principal.company_id,
            conversation.id,
            new_transcript if complete else [],
            [user_turn, assistant_turn],
        )
        await self._audit.record(
            "assistant.question_answered",
            company_id=principal.company_id,
            actor_user_id=principal.user_id,
            target_type="assistant_conversation",
            target_id=str(conversation.id),
            metadata={"tools": [u["name"] for u in used], "error": bool(error)},
        )
        if error:
            yield sse({"type": "error", "message": error})
        yield sse({"type": "done", "turn": assistant_turn})


__all__ = ["SUGGESTIONS", "AssistantClient", "AssistantService", "RateLimiter", "build_client", "sse"]
