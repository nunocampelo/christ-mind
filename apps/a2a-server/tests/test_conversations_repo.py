"""ConversationRepository against a live Postgres, gated on a reachable DB (same
connection-probe pattern as test_task_store_durability.py). conftest's session-wide
load_env() sets DATABASE_URL from .env, so `_require_db` gates on a live connection rather
than erroring on import order. Proves sequence ordering, the concurrent-append guard,
CASCADE delete, and restart survival.

The repository is now a session-consumer, so these tests drive it through the same seams
production does: a unit of work per operation via SessionProvider. `_append` mirrors the
executor's per-append retry (a rolled-back session can't be reused, so IntegrityError
re-enters a fresh unit of work); `_read` and `_mutate` wrap a single read/write."""

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from mind_of_christ_a2a.domain.conversations.models import (
    Conversation,
    ConversationMessage,
    ConversationSummary,
    MessageRole,
)
from mind_of_christ_a2a.infrastructure.db.engine import create_db_engine
from mind_of_christ_a2a.infrastructure.db.repositories.conversations import (
    ConversationNotFoundError,
    ConversationRepository,
)
from mind_of_christ_a2a.infrastructure.db.session import SessionProvider

pytestmark = pytest.mark.anyio

_T = TypeVar("_T")
_MAX_SEQUENCE_RETRIES = 8


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


async def _append(
    provider: SessionProvider,
    conversation_id: str,
    role: MessageRole,
    content: str,
    message_json: dict[str, Any] | None = None,
) -> ConversationMessage:
    for _ in range(_MAX_SEQUENCE_RETRIES):
        try:
            async with provider.unit_of_work() as session:
                return await ConversationRepository(session).append_message(
                    conversation_id, role, content, message_json
                )
        except IntegrityError:
            continue
    raise RuntimeError("append_message could not allocate a unique sequence")


async def _read(
    provider: SessionProvider,
    read: Callable[[ConversationRepository], Awaitable[_T]],
) -> _T:
    async with provider.unit_of_work() as session:
        return await read(ConversationRepository(session))


async def test_get_returns_messages_in_seq_order_and_derives_title(
    _require_db: None,
) -> None:
    provider = SessionProvider(create_db_engine())
    cid = _conversation_id()
    answer = {"text": "Forgiveness undoes it.", "cited_claims": []}
    try:
        await _append(provider, cid, MessageRole.user, "I cannot forgive my brother")
        await _append(
            provider, cid, MessageRole.agent, "Forgiveness undoes it.", answer
        )

        conversation = await _read(provider, lambda r: r.get(cid))
        assert [(m.role, m.sequence) for m in conversation.messages] == [
            (MessageRole.user, 1),
            (MessageRole.agent, 2),
        ]
        assert conversation.summary == "I cannot forgive my brother"

        user_msg, agent_msg = conversation.messages
        # content is the user-facing text for both; message_json only rides on the agent.
        assert (user_msg.content, user_msg.message_json) == (
            "I cannot forgive my brother",
            None,
        )
        assert agent_msg.content == "Forgiveness undoes it."
        assert agent_msg.message_json == answer
    finally:
        await _read(provider, lambda r: r.delete(cid))


async def test_concurrent_appends_get_contiguous_unique_seqs(_require_db: None) -> None:
    provider = SessionProvider(create_db_engine())
    cid = _conversation_id()
    try:
        n = 12
        await asyncio.gather(
            *(_append(provider, cid, MessageRole.user, f"message {i}") for i in range(n))
        )
        conversation = await _read(provider, lambda r: r.get(cid))
        sequences = sorted(m.sequence for m in conversation.messages)
        assert sequences == list(range(1, n + 1))
        assert len(conversation.messages) == n
    finally:
        await _read(provider, lambda r: r.delete(cid))


async def test_delete_cascades_and_get_raises_after(_require_db: None) -> None:
    engine = create_db_engine()
    provider = SessionProvider(engine)
    cid = _conversation_id()
    await _append(provider, cid, MessageRole.user, "a situation")
    await _read(provider, lambda r: r.delete(cid))

    with pytest.raises(ConversationNotFoundError):
        await _read(provider, lambda r: r.get(cid))

    async with engine.connect() as connection:
        remaining = await connection.scalar(
            text(
                "SELECT count(*) FROM conversation_messages "
                "WHERE conversation_id = :cid"
            ),
            {"cid": cid},
        )
    assert remaining == 0


async def test_get_raises_for_unknown_conversation(_require_db: None) -> None:
    provider = SessionProvider(create_db_engine())
    with pytest.raises(ConversationNotFoundError):
        await _read(provider, lambda r: r.get(_conversation_id()))


async def test_messages_survive_a_fresh_engine(_require_db: None) -> None:
    cid = _conversation_id()
    writer = SessionProvider(create_db_engine())
    await _append(writer, cid, MessageRole.user, "persisted situation")
    await _append(writer, cid, MessageRole.agent, '{"text": "answer"}')

    reader = SessionProvider(create_db_engine())
    try:
        conversation = await _read(reader, lambda r: r.get(cid))
        assert [m.content for m in conversation.messages] == [
            "persisted situation",
            '{"text": "answer"}',
        ]
    finally:
        await _read(reader, lambda r: r.delete(cid))


async def test_list_conversations_orders_by_most_recently_updated(
    _require_db: None,
) -> None:
    provider = SessionProvider(create_db_engine())
    first, second = _conversation_id(), _conversation_id()
    try:
        await _append(provider, first, MessageRole.user, "started first")
        await _append(provider, second, MessageRole.user, "started second")
        # A later append to `first` bumps its updated_at above `second`.
        await _append(provider, first, MessageRole.agent, '{"text": "reply"}')

        listed: tuple[ConversationSummary, ...] = await _read(
            provider, lambda r: r.list_conversations()
        )
        by_id = {c.conversation_id: c for c in listed}
        assert first in by_id and second in by_id
        # `first` was updated most recently, so it sorts ahead of `second`.
        order = [c.conversation_id for c in listed if c.conversation_id in {first, second}]
        assert order == [first, second]
        assert by_id[first].summary == "started first"
    finally:
        await _read(provider, lambda r: r.delete(first))
        await _read(provider, lambda r: r.delete(second))


async def test_rename_updates_summary(_require_db: None) -> None:
    provider = SessionProvider(create_db_engine())
    cid = _conversation_id()
    try:
        await _append(provider, cid, MessageRole.user, "auto-derived title")
        await _read(provider, lambda r: r.rename(cid, "My renamed thread"))

        conversation: Conversation = await _read(provider, lambda r: r.get(cid))
        assert conversation.summary == "My renamed thread"
    finally:
        await _read(provider, lambda r: r.delete(cid))


async def test_rename_unknown_conversation_raises(_require_db: None) -> None:
    provider = SessionProvider(create_db_engine())
    with pytest.raises(ConversationNotFoundError):
        await _read(provider, lambda r: r.rename(_conversation_id(), "no such thread"))


async def test_history_before_excludes_current_seq_and_bounds_by_turns(
    _require_db: None,
) -> None:
    provider = SessionProvider(create_db_engine())
    cid = _conversation_id()
    try:
        for i in range(1, 6):
            await _append(provider, cid, MessageRole.user, f"turn {i}")
        current = await _append(provider, cid, MessageRole.user, "turn 6 (in flight)")

        history = await _read(
            provider,
            lambda r: r.history_before(cid, current.sequence, max_turns=3, max_chars=10_000),
        )
        # Bounded to the 3 newest turns strictly before the current one (seqs 3,4,5),
        # re-ordered oldest-first for prompting; the in-flight turn 6 is excluded.
        assert [m.sequence for m in history] == [3, 4, 5]
        assert all(m.sequence < current.sequence for m in history)
    finally:
        await _read(provider, lambda r: r.delete(cid))


async def test_history_before_drops_oldest_past_char_budget(_require_db: None) -> None:
    provider = SessionProvider(create_db_engine())
    cid = _conversation_id()
    try:
        await _append(provider, cid, MessageRole.user, "A" * 100)
        await _append(provider, cid, MessageRole.agent, "B" * 100)
        await _append(provider, cid, MessageRole.user, "C" * 100)
        current = await _append(provider, cid, MessageRole.user, "current")

        history = await _read(
            provider,
            lambda r: r.history_before(cid, current.sequence, max_turns=6, max_chars=200),
        )
        # Newest-first fills the budget exactly: "C" (100) + "B" (100) = 200; "A" would
        # overshoot, so the oldest is dropped. Returned oldest-first.
        assert [m.content for m in history] == ["B" * 100, "C" * 100]
    finally:
        await _read(provider, lambda r: r.delete(cid))


async def test_history_before_truncates_the_boundary_message_to_fit_budget(
    _require_db: None,
) -> None:
    provider = SessionProvider(create_db_engine())
    cid = _conversation_id()
    try:
        await _append(provider, cid, MessageRole.user, "B" * 100)
        await _append(provider, cid, MessageRole.user, "C" * 100)
        current = await _append(provider, cid, MessageRole.user, "current")

        history = await _read(
            provider,
            lambda r: r.history_before(cid, current.sequence, max_turns=6, max_chars=150),
        )
        # "C" (100) fits; "B" overshoots, so it is truncated to its newest 50-char tail
        # rather than dropped or admitted whole. Total == budget, never over.
        assert [m.content for m in history] == ["B" * 50, "C" * 100]
        assert sum(len(m.content) for m in history) == 150
    finally:
        await _read(provider, lambda r: r.delete(cid))


async def test_history_before_truncates_a_single_oversized_turn(_require_db: None) -> None:
    provider = SessionProvider(create_db_engine())
    cid = _conversation_id()
    try:
        await _append(provider, cid, MessageRole.user, "X" * 10_000)
        current = await _append(provider, cid, MessageRole.user, "current")

        history = await _read(
            provider,
            lambda r: r.history_before(cid, current.sequence, max_turns=6, max_chars=4_000),
        )
        # The single prior turn is larger than the whole budget: it must be truncated to
        # the budget, not admitted whole (the P1 regression).
        assert len(history) == 1
        assert history[0].content == "X" * 4_000
        assert sum(len(m.content) for m in history) == 4_000
    finally:
        await _read(provider, lambda r: r.delete(cid))
