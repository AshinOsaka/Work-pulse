"""AI assistant conversations.

Two parallel records per conversation, both append-only:

* `transcript` - the exact Claude API message list (user turns, assistant content blocks including thinking and tool
  calls, tool results). It is replayed unchanged on the next question: thinking blocks are bound to the conversation
  that produced them, so the history is never edited, only appended to.
* `turns` - what the person saw: their questions, the assistant's text, the data cards and which tools ran.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from app.models.base import PyObjectId, TenantModel


class Conversation(TenantModel):
    user_id: PyObjectId
    title: str
    transcript: list[dict[str, Any]] = Field(default_factory=list)
    turns: list[dict[str, Any]] = Field(default_factory=list)
