"""Conversation-history DTOs the repository returns (never ORM rows). Agent `content` is
the `AgentAnswer` JSON stored verbatim, so history matches the A2A `evidence` artifact."""

from datetime import datetime
from enum import Enum
from typing import Protocol

from pydantic import BaseModel


class MessageRole(str, Enum):
    user = "user"
    agent = "agent"


class ConversationMessage(BaseModel):
    model_config = {"frozen": True}
    conversation_id: str
    role: MessageRole
    content: str
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
        self, conversation_id: str, role: MessageRole, content: str
    ) -> ConversationMessage: ...
