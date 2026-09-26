"""ConversationRepository against a live Postgres, gated on a reachable DB (same
connection-probe pattern as test_task_store_durability.py, since .env always sets
DATABASE_URL). Proves sequence ordering, the concurrent-append guard, CASCADE delete, and
restart survival."""

import asyncio
import uuid

import pytest
from sqlalchemy import text

from mind_of_christ_a2a.domain.conversations.models import MessageRole
from mind_of_christ_a2a.infrastructure.db.engine import create_db_engine
from mind_of_christ_a2a.infrastructure.db.repositories.conversations import (
    ConversationNotFoundError,
    ConversationRepository,
)

pytestmark = pytest.mark.anyio


@pytest.fixture
async def _require_db() -> None:
    engine = create_db_engine()
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    except Exception:
        pytest.skip("Postgres unreachable; needs the compose database up + migrated")
    finally:
        await engine.dispose()


def _conversation_id() -> str:
    return str(uuid.uuid4())


async def test_get_returns_messages_in_seq_order_and_derives_title(
    _require_db: None,
) -> None:
    engine = create_db_engine()
    repo = ConversationRepository(engine)
    cid = _conversation_id()
    try:
        await repo.append_message(cid, MessageRole.user, "I cannot forgive my brother")
        await repo.append_message(cid, MessageRole.agent, '{"text": "Forgiveness…"}')

        conversation = await repo.get(cid)
        assert [(m.role, m.sequence) for m in conversation.messages] == [
            (MessageRole.user, 1),
            (MessageRole.agent, 2),
        ]
        assert conversation.summary == "I cannot forgive my brother"
    finally:
        await repo.delete(cid)
        await engine.dispose()


async def test_concurrent_appends_get_contiguous_unique_seqs(_require_db: None) -> None:
    engine = create_db_engine()
    repo = ConversationRepository(engine)
    cid = _conversation_id()
    try:
        n = 12
        await asyncio.gather(
            *(
                repo.append_message(cid, MessageRole.user, f"message {i}")
                for i in range(n)
            )
        )
        conversation = await repo.get(cid)
        sequences = sorted(m.sequence for m in conversation.messages)
        assert sequences == list(range(1, n + 1))
        assert len(conversation.messages) == n
    finally:
        await repo.delete(cid)
        await engine.dispose()


async def test_delete_cascades_and_get_raises_after(_require_db: None) -> None:
    engine = create_db_engine()
    repo = ConversationRepository(engine)
    cid = _conversation_id()
    try:
        await repo.append_message(cid, MessageRole.user, "a situation")
        await repo.delete(cid)

        with pytest.raises(ConversationNotFoundError):
            await repo.get(cid)

        async with engine.connect() as connection:
            remaining = await connection.scalar(
                text(
                    "SELECT count(*) FROM conversation_messages "
                    "WHERE conversation_id = :cid"
                ),
                {"cid": cid},
            )
        assert remaining == 0
    finally:
        await engine.dispose()


async def test_get_raises_for_unknown_conversation(_require_db: None) -> None:
    engine = create_db_engine()
    repo = ConversationRepository(engine)
    try:
        with pytest.raises(ConversationNotFoundError):
            await repo.get(_conversation_id())
    finally:
        await engine.dispose()


async def test_messages_survive_a_fresh_engine(_require_db: None) -> None:
    cid = _conversation_id()
    writer_engine = create_db_engine()
    writer = ConversationRepository(writer_engine)
    try:
        await writer.append_message(cid, MessageRole.user, "persisted situation")
        await writer.append_message(cid, MessageRole.agent, '{"text": "answer"}')
    finally:
        await writer_engine.dispose()

    reader_engine = create_db_engine()
    reader = ConversationRepository(reader_engine)
    try:
        conversation = await reader.get(cid)
        assert [m.content for m in conversation.messages] == [
            "persisted situation",
            '{"text": "answer"}',
        ]
    finally:
        await reader.delete(cid)
        await reader_engine.dispose()
