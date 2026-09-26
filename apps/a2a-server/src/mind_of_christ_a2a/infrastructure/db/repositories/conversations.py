"""Server-owned conversation history, returned as DTOs (never ORM rows). Deliberately not
reconstructed from A2A Tasks — Tasks are executions, messages are history, and coupling the
two would tie history to the task lifecycle."""

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from mind_of_christ_a2a.domain.conversations.models import (
    Conversation,
    ConversationMessage,
    MessageRole,
)
from mind_of_christ_a2a.infrastructure.db.models.conversation import (
    ConversationMessageRow,
    ConversationRow,
)

_SUMMARY_MAX_CHARS = 80
_MAX_SEQUENCE_RETRIES = 8


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
    def __init__(self, engine: AsyncEngine) -> None:
        self._session = async_sessionmaker(engine, expire_on_commit=False)

    async def get(self, conversation_id: str) -> Conversation:
        async with self._session() as session:
            row = await session.get(ConversationRow, conversation_id)
            if row is None:
                raise ConversationNotFoundError
            result = await session.execute(
                select(ConversationMessageRow)
                .where(ConversationMessageRow.conversation_id == conversation_id)
                .order_by(ConversationMessageRow.sequence)
            )
            messages = tuple(
                ConversationMessage(
                    conversation_id=m.conversation_id,
                    role=MessageRole(m.role),
                    content=m.content,
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
        self, conversation_id: str, role: MessageRole, content: str
    ) -> ConversationMessage:
        for _ in range(_MAX_SEQUENCE_RETRIES):
            try:
                return await self._append_once(conversation_id, role, content)
            except IntegrityError:
                # A concurrent append won this sequence. Retry the allocate-and-insert
                # against the now-higher max; the UNIQUE constraint, not a read lock, guards.
                continue
        raise RuntimeError("append_message could not allocate a unique sequence")

    async def _append_once(
        self, conversation_id: str, role: MessageRole, content: str
    ) -> ConversationMessage:
        now = _now()
        async with self._session() as session:
            async with session.begin():
                conversation = await session.get(ConversationRow, conversation_id)
                if conversation is None:
                    session.add(
                        ConversationRow(
                            conversation_id=conversation_id,
                            summary=(
                                _summary_from(content)
                                if role is MessageRole.user
                                else None
                            ),
                            created_at=now,
                            updated_at=now,
                        )
                    )
                else:
                    conversation.updated_at = now

                max_sequence = await session.scalar(
                    select(func.max(ConversationMessageRow.sequence)).where(
                        ConversationMessageRow.conversation_id == conversation_id
                    )
                )
                sequence = (max_sequence or 0) + 1
                session.add(
                    ConversationMessageRow(
                        conversation_id=conversation_id,
                        role=role.value,
                        content=content,
                        timestamp=now,
                        sequence=sequence,
                    )
                )
        return ConversationMessage(
            conversation_id=conversation_id,
            role=role,
            content=content,
            timestamp=now,
            sequence=sequence,
        )

    async def delete(self, conversation_id: str) -> None:
        async with self._session() as session:
            async with session.begin():
                conversation = await session.get(ConversationRow, conversation_id)
                if conversation is not None:
                    await session.delete(conversation)
