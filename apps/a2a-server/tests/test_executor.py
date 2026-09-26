"""The executor maps orchestrator events onto A2A frames with the MCP subprocess and the
orchestrator build stubbed -- the outermost boundaries. Asserts the full frame sequence by
equality, and that the cited-vs-inferred distinction survives onto the evidence artifact.
"""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime

import pytest
from a2a.types import Task, TaskArtifactUpdateEvent, TaskState, TaskStatusUpdateEvent

from mind_of_christ_agent.application.answer import (
    AgentAnswer,
    CitedClaim,
    InferredChain,
)
from mind_of_christ_agent.domain.events import FinalEvent, StepStatusEvent, TokenEvent
from mind_of_christ_a2a.domain.a2a import executor as executor_module
from mind_of_christ_a2a.domain.a2a.executor import MindOfChristExecutor
from mind_of_christ_a2a.domain.conversations.models import (
    ConversationMessage,
    MessageRole,
)

_CLAIM = CitedClaim(
    claim_id="c1",
    source_id="s1",
    subject="the ego",
    predicate="teaches",
    object="attack",
    verb_phrase="teaches",
    polarity="affirmed",
    evidence="The ego teaches attack.",
)


class _RecordingQueue:
    def __init__(self) -> None:
        self.events: list[object] = []

    async def enqueue_event(self, event: object) -> None:
        self.events.append(event)


class _RecordingConversations:
    def __init__(self) -> None:
        self.appended: list[tuple[str, MessageRole, str]] = []

    async def append_message(
        self, conversation_id: str, role: MessageRole, content: str
    ) -> ConversationMessage:
        self.appended.append((conversation_id, role, content))
        return ConversationMessage(
            conversation_id=conversation_id,
            role=role,
            content=content,
            timestamp=datetime(2026, 1, 1),
            sequence=len(self.appended),
        )


class _FakeContext:
    def __init__(self, situation: str) -> None:
        self.task_id = "task-1"
        self.context_id = "ctx-1"
        self._situation = situation

    def get_user_input(self) -> str:
        return self._situation


class _StubOrchestrator:
    def __init__(self, answer: AgentAnswer) -> None:
        self.last_answer = answer

    async def run_stream(self, _request: object) -> AsyncIterator[object]:
        yield StepStatusEvent(text="Mapped situation to 1 concept(s)")
        yield StepStatusEvent(text="Calling find_claims")
        yield TokenEvent(delta="The Course ")
        yield TokenEvent(delta="says forgiveness.")
        yield FinalEvent(text="The Course says forgiveness.")


@pytest.fixture
def stubbed(monkeypatch: pytest.MonkeyPatch) -> AgentAnswer:
    answer = AgentAnswer(
        text="The Course says forgiveness.",
        concepts=["forgiveness"],
        cited_claims=[_CLAIM],
        inferred_chains=[InferredChain(links=[_CLAIM])],
    )

    @asynccontextmanager
    async def fake_connect() -> AsyncIterator[object]:
        yield object()

    monkeypatch.setattr(executor_module, "connect", fake_connect)
    monkeypatch.setattr(
        executor_module, "build_orchestrator", lambda _mcp: _StubOrchestrator(answer)
    )
    return answer


@pytest.mark.anyio
async def test_execute_maps_events_to_frames(stubbed: AgentAnswer) -> None:
    queue = _RecordingQueue()
    conversations = _RecordingConversations()
    await MindOfChristExecutor(conversations=conversations).execute(
        _FakeContext("I can't forgive"),  # type: ignore[arg-type]
        queue,  # type: ignore[arg-type]
    )

    kinds = [type(e).__name__ for e in queue.events]
    # Task first (SDK requires it before any status update), then start_work + two status
    # events, two answer artifact chunks + the artifact close, the evidence artifact, and
    # the terminal complete status.
    assert kinds[0] == "Task"
    assert isinstance(queue.events[0], Task)
    assert queue.events[0].status.state == TaskState.TASK_STATE_SUBMITTED

    statuses = [e for e in queue.events if isinstance(e, TaskStatusUpdateEvent)]
    artifacts = [e for e in queue.events if isinstance(e, TaskArtifactUpdateEvent)]

    working_texts = [
        p.text
        for e in statuses
        if e.status.state == TaskState.TASK_STATE_WORKING
        for p in e.status.message.parts
    ]
    assert "Mapped situation to 1 concept(s)" in working_texts
    assert "Calling find_claims" in working_texts

    answer_chunks = [a for a in artifacts if a.artifact.artifact_id == "answer"]
    streamed = "".join(p.text for a in answer_chunks for p in a.artifact.parts)
    assert streamed == "The Course says forgiveness."
    assert answer_chunks[0].append is False
    assert answer_chunks[-1].last_chunk is True

    terminal = statuses[-1]
    assert terminal.status.state == TaskState.TASK_STATE_COMPLETED
    assert "".join(p.text for p in terminal.status.message.parts) == (
        "The Course says forgiveness."
    )

    # A successful run persists the user turn then the assistant answer (the same JSON as
    # the evidence artifact), keyed by context_id.
    assert [(role, cid) for cid, role, _ in conversations.appended] == [
        (MessageRole.user, "ctx-1"),
        (MessageRole.agent, "ctx-1"),
    ]
    assert conversations.appended[0][2] == "I can't forgive"
    assert AgentAnswer.model_validate_json(conversations.appended[1][2]) == stubbed


@pytest.mark.anyio
async def test_evidence_artifact_keeps_cited_distinct_from_inferred(
    stubbed: AgentAnswer,
) -> None:
    queue = _RecordingQueue()
    await MindOfChristExecutor(conversations=_RecordingConversations()).execute(
        _FakeContext("I can't forgive"),  # type: ignore[arg-type]
        queue,  # type: ignore[arg-type]
    )

    evidence = [
        e
        for e in queue.events
        if isinstance(e, TaskArtifactUpdateEvent)
        and e.artifact.artifact_id == "evidence"
    ]
    assert len(evidence) == 1
    payload = json.loads(evidence[0].artifact.parts[0].text)
    # Round-trips to the same AgentAnswer: cited_claims and inferred_chains stay separate
    # lists, never a flattened one.
    assert AgentAnswer.model_validate(payload) == stubbed
    assert payload["cited_claims"] != []
    assert payload["inferred_chains"][0]["inferred"] is True


@pytest.mark.anyio
async def test_failure_emits_terminal_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    @asynccontextmanager
    async def fake_connect() -> AsyncIterator[object]:
        yield object()

    class _Boom:
        last_answer = None

        async def run_stream(self, _request: object) -> AsyncIterator[object]:
            raise RuntimeError("internal path /secret leaked here")
            yield  # pragma: no cover

    monkeypatch.setattr(executor_module, "connect", fake_connect)
    monkeypatch.setattr(executor_module, "build_orchestrator", lambda _mcp: _Boom())

    queue = _RecordingQueue()
    conversations = _RecordingConversations()
    await MindOfChristExecutor(conversations=conversations).execute(
        _FakeContext("x"),  # type: ignore[arg-type]
        queue,  # type: ignore[arg-type]
    )

    statuses = [e for e in queue.events if isinstance(e, TaskStatusUpdateEvent)]
    terminal = statuses[-1]
    assert terminal.status.state == TaskState.TASK_STATE_FAILED
    text = "".join(p.text for p in terminal.status.message.parts)
    assert text == "Agent request failed"
    assert "secret" not in text

    # A failed run keeps the user turn but persists no assistant answer.
    assert [role for _, role, _ in conversations.appended] == [MessageRole.user]
