"""The /conversations read surface through the real FastAPI app, with an in-memory repo
double on app.state (no DB). Covers newest-first listing, detail turn order + message_json,
and the 404 for an unknown id."""

from collections.abc import Iterator
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

import mind_of_christ_a2a.main as main_module
from mind_of_christ_a2a.domain.conversations.models import (
    Conversation,
    ConversationMessage,
    ConversationSummary,
    MessageRole,
)
from mind_of_christ_a2a.infrastructure.db.repositories.conversations import (
    ConversationNotFoundError,
)
from mind_of_christ_a2a.main import app

_ANSWER_JSON = {"text": "Forgiveness undoes it.", "cited_claims": [], "inferred_chains": []}

_OLDER = Conversation(
    conversation_id="ctx-old",
    summary="an older thread",
    created_at=datetime(2026, 1, 1),
    updated_at=datetime(2026, 1, 1),
    messages=(),
)
_NEWER = Conversation(
    conversation_id="ctx-new",
    summary="I cannot forgive",
    created_at=datetime(2026, 1, 2),
    updated_at=datetime(2026, 1, 3),
    messages=(
        ConversationMessage(
            conversation_id="ctx-new",
            role=MessageRole.user,
            content="I cannot forgive",
            message_json=None,
            timestamp=datetime(2026, 1, 2),
            sequence=1,
        ),
        ConversationMessage(
            conversation_id="ctx-new",
            role=MessageRole.agent,
            content="Forgiveness undoes it.",
            message_json=_ANSWER_JSON,
            timestamp=datetime(2026, 1, 3),
            sequence=2,
        ),
    ),
)


class _FakeConversations:
    def __init__(self, *conversations: Conversation) -> None:
        self._by_id = {c.conversation_id: c for c in conversations}

    async def list_conversations(self) -> tuple[ConversationSummary, ...]:
        summaries = [
            ConversationSummary(
                conversation_id=c.conversation_id,
                summary=c.summary,
                created_at=c.created_at,
                updated_at=c.updated_at,
            )
            for c in self._by_id.values()
        ]
        summaries.sort(key=lambda s: s.updated_at, reverse=True)
        return tuple(summaries)

    async def get(self, conversation_id: str) -> Conversation:
        conversation = self._by_id.get(conversation_id)
        if conversation is None:
            raise ConversationNotFoundError
        return conversation

    async def rename(self, conversation_id: str, summary: str) -> None:
        conversation = self._by_id.get(conversation_id)
        if conversation is None:
            raise ConversationNotFoundError
        self._by_id[conversation_id] = conversation.model_copy(
            update={"summary": summary}
        )

    async def delete(self, conversation_id: str) -> None:
        self._by_id.pop(conversation_id, None)


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("AGENT_PUBLIC_URL", "http://127.0.0.1:8000")

    async def in_memory_stores(app_: object) -> None:
        app_.state.conversations = _FakeConversations(_OLDER, _NEWER)  # type: ignore[attr-defined]
        return None

    monkeypatch.setattr(main_module, "build_stores", in_memory_stores)
    with TestClient(app) as c:
        yield c


def test_list_returns_summaries_newest_first(client: TestClient) -> None:
    body = client.get("/conversations").json()
    assert [c["conversation_id"] for c in body] == ["ctx-new", "ctx-old"]
    assert "messages" not in body[0]


def test_detail_returns_turns_in_order_with_message_json(client: TestClient) -> None:
    body = client.get("/conversations/ctx-new").json()
    assert [(m["role"], m["sequence"]) for m in body["messages"]] == [
        ("user", 1),
        ("agent", 2),
    ]
    assert body["messages"][0]["message_json"] is None
    assert body["messages"][1]["content"] == "Forgiveness undoes it."
    assert body["messages"][1]["message_json"] == _ANSWER_JSON


def test_unknown_conversation_is_404(client: TestClient) -> None:
    response = client.get("/conversations/nope")
    assert response.status_code == 404
    assert response.json()["detail"] == "Conversation not found"


def test_rename_updates_summary(client: TestClient) -> None:
    response = client.patch("/conversations/ctx-new", json={"summary": "Renamed"})
    assert response.status_code == 200
    assert response.json()["summary"] == "Renamed"
    # The change is reflected on a subsequent read.
    assert client.get("/conversations/ctx-new").json()["summary"] == "Renamed"


def test_rename_trims_and_rejects_blank(client: TestClient) -> None:
    assert (
        client.patch("/conversations/ctx-new", json={"summary": "  spaced  "}).json()[
            "summary"
        ]
        == "spaced"
    )
    assert (
        client.patch("/conversations/ctx-new", json={"summary": "   "}).status_code
        == 422
    )


def test_rename_unknown_is_404(client: TestClient) -> None:
    response = client.patch("/conversations/nope", json={"summary": "x"})
    assert response.status_code == 404


def test_delete_removes_and_is_idempotent(client: TestClient) -> None:
    assert client.delete("/conversations/ctx-old").status_code == 204
    assert client.get("/conversations/ctx-old").status_code == 404
    # Deleting an already-gone conversation is still a no-op 204.
    assert client.delete("/conversations/ctx-old").status_code == 204
