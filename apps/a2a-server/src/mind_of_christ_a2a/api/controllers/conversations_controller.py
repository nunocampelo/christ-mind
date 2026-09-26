"""Read-only conversation history. Its own REST surface (not A2A): `/a2a` runs the agent
turn, this returns stored history. A2A Tasks are executions, not history — see the
repository."""

from fastapi import APIRouter, Depends, HTTPException

from mind_of_christ_a2a.api.dependencies import get_conversations
from mind_of_christ_a2a.domain.conversations.models import (
    Conversation,
    ConversationSummary,
)
from mind_of_christ_a2a.infrastructure.db.repositories.conversations import (
    ConversationNotFoundError,
    ConversationRepository,
)

router = APIRouter(tags=["conversations"])


@router.get("/conversations")
async def list_conversations(
    conversations: ConversationRepository = Depends(get_conversations),
) -> list[ConversationSummary]:
    return list(await conversations.list_conversations())


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    conversations: ConversationRepository = Depends(get_conversations),
) -> Conversation:
    try:
        return await conversations.get(conversation_id)
    except ConversationNotFoundError:
        # Static detail: the id is not echoed back, matching the domain error's no-leak rule.
        raise HTTPException(status_code=404, detail="Conversation not found") from None
