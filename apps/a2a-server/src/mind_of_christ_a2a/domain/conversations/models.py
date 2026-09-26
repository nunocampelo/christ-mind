"""Conversation-history DTOs the repository returns (never ORM rows). `content` is always
the user-facing turn text (user's message, or the agent's prose); `message_json` carries the
full AgentAnswer for agent turns and is None for user turns, so a reader can render a
conversation from `content` alone without deserializing the answer schema."""

from datetime import datetime
from enum import Enum
from typing import Any, Protocol

from pydantic import BaseModel


class MessageRole(str, Enum):
    user = "user"
    agent = "agent"


class ConversationMessage(BaseModel):
    model_config = {"frozen": True}
    conversation_id: str
    role: MessageRole
    content: str
    message_json: dict[str, Any] | None
    timestamp: datetime
    sequence: int


class Conversation(BaseModel):
    model_config = {"frozen": True}
    conversation_id: str
    summary: str | None
    created_at: datetime
    updated_at: datetime
    messages: tuple[ConversationMessage, ...]


class ConversationWriter(Protocol):
    """What the executor needs to persist a turn — narrower than the full repository, so a
    test double satisfies it structurally."""

    async def append_message(
        self,
        conversation_id: str,
        role: MessageRole,
        content: str,
        message_json: dict[str, Any] | None = None,
    ) -> ConversationMessage: ...
