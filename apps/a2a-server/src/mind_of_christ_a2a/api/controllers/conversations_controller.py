"""Read-only conversation history. Its own REST surface (not A2A): `/a2a` runs the agent
turn, this returns stored history. A2A Tasks are executions, not history — see the
repository."""

from fastapi import APIRouter, Depends, HTTPException, Response, status

from mind_of_christ_a2a.api.dependencies import get_conversations
from mind_of_christ_a2a.domain.conversations.models import (
    Conversation,
    ConversationRename,
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


@router.patch("/conversations/{conversation_id}")
async def rename_conversation(
    conversation_id: str,
    body: ConversationRename,
    conversations: ConversationRepository = Depends(get_conversations),
) -> ConversationSummary:
    try:
        await conversations.rename(conversation_id, body.summary)
        conversation = await conversations.get(conversation_id)
    except ConversationNotFoundError:
        raise HTTPException(status_code=404, detail="Conversation not found") from None
    return ConversationSummary(
        conversation_id=conversation.conversation_id,
        summary=conversation.summary,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: str,
    conversations: ConversationRepository = Depends(get_conversations),
) -> Response:
    # Idempotent: deleting an unknown id is a no-op 204 (repo.delete no-ops), so a stale row
    # or double-click can't error.
    await conversations.delete(conversation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
