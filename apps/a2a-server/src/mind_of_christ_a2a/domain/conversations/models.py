"""Conversation-history DTOs the repository returns (never ORM rows). `content` is always
the user-facing turn text (user's message, or the agent's prose); `message_json` carries the
full AgentAnswer for agent turns and is None for user turns, so a reader can render a
conversation from `content` alone without deserializing the answer schema."""

from datetime import datetime
from enum import Enum
from typing import Any, Protocol

from pydantic import BaseModel, Field, field_validator


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


class ConversationSummary(BaseModel):
    """A conversation without its messages — the list-row shape (id + title + timestamps)
    the sidebar reads, so listing doesn't load every message body."""

    model_config = {"frozen": True}
    conversation_id: str
    summary: str | None
    created_at: datetime
    updated_at: datetime


class Conversation(BaseModel):
    model_config = {"frozen": True}
    conversation_id: str
    summary: str | None
    created_at: datetime
    updated_at: datetime
    messages: tuple[ConversationMessage, ...]


class ConversationRename(BaseModel):
    """PATCH body for renaming a conversation. `summary` must be non-blank after trimming —
    a blank title is rejected (422) rather than clearing the derived one."""

    model_config = {"frozen": True}
    summary: str = Field(min_length=1)

    @field_validator("summary")
    @classmethod
    def _strip_non_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("summary must not be blank")
        return stripped


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
