"""Server-owned conversation history, returned as DTOs (never ORM rows). Deliberately not
reconstructed from A2A Tasks — Tasks are executions, messages are history, and coupling the
two would tie history to the task lifecycle.

The repository is a pure session-consumer: it holds an `AsyncSession` and never opens one or
commits. The caller owns the transaction via `SessionProvider.unit_of_work` (a request-scoped
one for the controllers, a short per-append one the executor opens itself)."""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mind_of_christ_a2a.domain.conversations.models import (
    Conversation,
    ConversationMessage,
    ConversationSummary,
    MessageRole,
)
from mind_of_christ_a2a.infrastructure.db.models.conversation import (
    ConversationMessageRow,
    ConversationRow,
)

_SUMMARY_MAX_CHARS = 80


class ConversationNotFoundError(Exception):
    """No conversation with the given id. Static message: the id is not interpolated, so a
    caught instance can't leak it into a log or an upstream response."""

    def __init__(self) -> None:
        super().__init__("Conversation not found")


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _summary_from(content: str) -> str:
    single_line = " ".join(content.split())
    if len(single_line) <= _SUMMARY_MAX_CHARS:
        return single_line
    return single_line[: _SUMMARY_MAX_CHARS - 1].rstrip() + "…"


class ConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_conversations(self) -> tuple[ConversationSummary, ...]:
        result = await self._session.execute(
            select(ConversationRow).order_by(ConversationRow.updated_at.desc())
        )
        return tuple(
            ConversationSummary(
                conversation_id=c.conversation_id,
                summary=c.summary,
                created_at=c.created_at,
                updated_at=c.updated_at,
            )
            for c in result.scalars()
        )

    async def get(self, conversation_id: str) -> Conversation:
        row = await self._session.get(ConversationRow, conversation_id)
        if row is None:
            raise ConversationNotFoundError
        result = await self._session.execute(
            select(ConversationMessageRow)
            .where(ConversationMessageRow.conversation_id == conversation_id)
            .order_by(ConversationMessageRow.sequence)
        )
        messages = tuple(
            ConversationMessage(
                conversation_id=m.conversation_id,
                role=MessageRole(m.role),
                content=m.content,
                message_json=m.message_json,
                timestamp=m.timestamp,
                sequence=m.sequence,
            )
            for m in result.scalars()
        )
        return Conversation(
            conversation_id=row.conversation_id,
            summary=row.summary,
            created_at=row.created_at,
            updated_at=row.updated_at,
            messages=messages,
        )

    async def append_message(
        self,
        conversation_id: str,
        role: MessageRole,
        content: str,
        message_json: dict[str, Any] | None = None,
    ) -> ConversationMessage:
        """Single attempt against the bound session. The retry that guards concurrent
        appends must re-enter the unit of work (a rolled-back session can't be reused), so
        it lives in the caller that owns the unit of work, not here."""
        now = _now()
        conversation = await self._session.get(ConversationRow, conversation_id)
        if conversation is None:
            self._session.add(
                ConversationRow(
                    conversation_id=conversation_id,
                    summary=(
                        _summary_from(content) if role is MessageRole.user else None
                    ),
                    created_at=now,
                    updated_at=now,
                )
            )
        else:
            conversation.updated_at = now

        max_sequence = await self._session.scalar(
            select(func.max(ConversationMessageRow.sequence)).where(
                ConversationMessageRow.conversation_id == conversation_id
            )
        )
        sequence = (max_sequence or 0) + 1
        self._session.add(
            ConversationMessageRow(
                conversation_id=conversation_id,
                role=role.value,
                content=content,
                message_json=message_json,
                timestamp=now,
                sequence=sequence,
            )
        )
        return ConversationMessage(
            conversation_id=conversation_id,
            role=role,
            content=content,
            message_json=message_json,
            timestamp=now,
            sequence=sequence,
        )

    async def rename(self, conversation_id: str, summary: str) -> None:
        conversation = await self._session.get(ConversationRow, conversation_id)
        if conversation is None:
            raise ConversationNotFoundError
        conversation.summary = summary
        conversation.updated_at = _now()

    async def delete(self, conversation_id: str) -> None:
        conversation = await self._session.get(ConversationRow, conversation_id)
        if conversation is not None:
            await self._session.delete(conversation)
