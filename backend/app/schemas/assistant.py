"""AI assistant API."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import Field

from app.schemas.common import APIModel


class AssistantStatus(APIModel):
    configured: bool
    model: str | None
    suggestions: list[str]


class ConversationSummary(APIModel):
    id: str
    title: str
    updated_at: datetime
    questions: int


class ConversationOut(APIModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    #: What the person saw: questions, answers, data cards, tools used.
    turns: list[dict[str, Any]]


class AskRequest(APIModel):
    message: str = Field(min_length=1, max_length=2000)
    #: Continue this conversation; omit to start a new one.
    conversation_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{24}$")
