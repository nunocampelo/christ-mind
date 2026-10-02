"""The executor maps orchestrator events onto A2A frames with the MCP subprocess and the
orchestrator build stubbed -- the outermost boundaries. Asserts the full frame sequence by
equality, and that the cited-vs-inferred distinction survives onto the evidence artifact.
"""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

import pytest
from a2a.types import Task, TaskArtifactUpdateEvent, TaskState, TaskStatusUpdateEvent

from application.mapping.map_situation import ConversationTurn

from mind_of_christ_agent.application.answer import (
    AgentAnswer,
    AgentRequest,
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
    """Records appends and hands back the executor a SessionProvider double whose unit of
    work yields a repository bound to this recorder. Substitutes for the real
    SessionProvider + ConversationRepository so the executor's persistence is observed
    without a DB."""

    def __init__(
        self, history: tuple[ConversationMessage, ...] = ()
    ) -> None:
        self.appended: list[tuple[str, MessageRole, str, dict[str, Any] | None]] = []
        self._history = history
        self.history_before_sequence: int | None = None

    async def history_before(
        self,
        conversation_id: str,
        before_sequence: int,
        max_turns: int,
        max_chars: int,
    ) -> tuple[ConversationMessage, ...]:
        self.history_before_sequence = before_sequence
        return tuple(m for m in self._history if m.sequence < before_sequence)

    async def append_message(
        self,
        conversation_id: str,
        role: MessageRole,
        content: str,
        message_json: dict[str, Any] | None = None,
    ) -> ConversationMessage:
        self.appended.append((conversation_id, role, content, message_json))
        # Continue past any seeded history, as a real append would (max existing seq + 1).
        base = max((m.sequence for m in self._history), default=0)
        return ConversationMessage(
            conversation_id=conversation_id,
            role=role,
            content=content,
            message_json=message_json,
            timestamp=datetime(2026, 1, 1),
            sequence=base + len(self.appended),
        )

    def as_session_provider(self) -> "_FakeSessionProvider":
        return _FakeSessionProvider(self)


class _FakeSessionProvider:
    def __init__(self, conversations: _RecordingConversations) -> None:
        self._conversations = conversations

    @asynccontextmanager
    async def unit_of_work(self) -> AsyncIterator[_RecordingConversations]:
        yield self._conversations


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
    # The fake unit of work yields the recorder as the "session"; passing it straight
    # through stands in for ConversationRepository(session), so appends land on the recorder.
    monkeypatch.setattr(executor_module, "ConversationRepository", lambda session: session)
    return answer


@pytest.mark.anyio
async def test_execute_maps_events_to_frames(stubbed: AgentAnswer) -> None:
    queue = _RecordingQueue()
    conversations = _RecordingConversations()
    await MindOfChristExecutor(
        sessions=conversations.as_session_provider()  # type: ignore[arg-type]
    ).execute(
        _FakeContext("I can't forgive"),  # type: ignore[arg-type]
        queue,  # type: ignore[arg-type]
    )

    kinds = [type(e).__name__ for e in queue.events]
    # Task first (SDK requires it before any status update), then start_work + two status
    # events, two streamed answer deltas, the final answer chunk that replaces them with the
    # sanitized full text, the evidence artifact, and the terminal complete status.
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
    # Interior chunks stream deltas (first creates the artifact, append=False); the final
    # chunk replaces them (append=False, last_chunk) with FinalEvent.text, so a GetTask /
    # recovery read sees the authoritative sanitized answer, not the raw delta stream.
    interior = "".join(p.text for a in answer_chunks[:-1] for p in a.artifact.parts)
    assert interior == "The Course says forgiveness."
    assert answer_chunks[0].append is False
    final_chunk = answer_chunks[-1]
    assert final_chunk.append is False
    assert final_chunk.last_chunk is True
    assert "".join(p.text for p in final_chunk.artifact.parts) == (
        "The Course says forgiveness."
    )

    terminal = statuses[-1]
    assert terminal.status.state == TaskState.TASK_STATE_COMPLETED
    assert "".join(p.text for p in terminal.status.message.parts) == (
        "The Course says forgiveness."
    )

    # A successful run persists the user turn then the assistant turn, keyed by context_id.
    assert [(role, cid) for cid, role, _, _ in conversations.appended] == [
        (MessageRole.user, "ctx-1"),
        (MessageRole.agent, "ctx-1"),
    ]
    # The user turn stores the raw text and no structured payload.
    user_cid, _, user_content, user_json = conversations.appended[0]
    assert user_content == "I can't forgive"
    assert user_json is None
    # The agent turn stores the prose in content and the full AgentAnswer in message_json.
    _, _, agent_content, agent_json = conversations.appended[1]
    assert agent_content == "The Course says forgiveness."
    assert agent_json is not None
    assert AgentAnswer.model_validate(agent_json) == stubbed


@pytest.mark.anyio
async def test_final_answer_supersedes_the_raw_streamed_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The raw deltas carry a fabricated citation marker; FinalEvent.text is the sanitized
    # prose. The final answer chunk and the terminal message must both be the sanitized text
    # (what a GetTask / recovery read sees), never the raw stream with the bogus marker.
    sanitized = "Forgiveness brings peace."
    answer = AgentAnswer(
        text=sanitized,
        concepts=["forgiveness"],
        cited_claims=[_CLAIM],
        inferred_chains=[],
    )

    class _FabricatingOrchestrator:
        last_answer = answer

        async def run_stream(self, _request: object) -> AsyncIterator[object]:
            yield TokenEvent(delta="Forgiveness brings peace. [made-up]")
            yield FinalEvent(text=sanitized)

    @asynccontextmanager
    async def fake_connect() -> AsyncIterator[object]:
        yield object()

    monkeypatch.setattr(executor_module, "connect", fake_connect)
    monkeypatch.setattr(
        executor_module,
        "build_orchestrator",
        lambda _mcp: _FabricatingOrchestrator(),
    )
    monkeypatch.setattr(executor_module, "ConversationRepository", lambda session: session)

    queue = _RecordingQueue()
    conversations = _RecordingConversations()
    await MindOfChristExecutor(
        sessions=conversations.as_session_provider()  # type: ignore[arg-type]
    ).execute(
        _FakeContext("peace"),  # type: ignore[arg-type]
        queue,  # type: ignore[arg-type]
    )

    answer_chunks = [
        e
        for e in queue.events
        if isinstance(e, TaskArtifactUpdateEvent)
        and e.artifact.artifact_id == "answer"
    ]
    final_chunk = answer_chunks[-1]
    assert final_chunk.append is False
    assert final_chunk.last_chunk is True
    assert "".join(p.text for p in final_chunk.artifact.parts) == sanitized

    statuses = [e for e in queue.events if isinstance(e, TaskStatusUpdateEvent)]
    terminal = statuses[-1]
    assert terminal.status.state == TaskState.TASK_STATE_COMPLETED
    assert "".join(p.text for p in terminal.status.message.parts) == sanitized

    # The persisted assistant turn is the sanitized prose, too.
    _, _, agent_content, _ = conversations.appended[1]
    assert agent_content == sanitized


@pytest.mark.anyio
async def test_evidence_artifact_keeps_cited_distinct_from_inferred(
    stubbed: AgentAnswer,
) -> None:
    queue = _RecordingQueue()
    await MindOfChristExecutor(
        sessions=_RecordingConversations().as_session_provider()  # type: ignore[arg-type]
    ).execute(
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
    monkeypatch.setattr(executor_module, "ConversationRepository", lambda session: session)

    queue = _RecordingQueue()
    conversations = _RecordingConversations()
    await MindOfChristExecutor(
        sessions=conversations.as_session_provider()  # type: ignore[arg-type]
    ).execute(
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
    assert [role for _, role, _, _ in conversations.appended] == [MessageRole.user]


@pytest.mark.anyio
async def test_execute_loads_history_and_passes_it_excluding_the_current_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, AgentRequest] = {}

    class _RequestCapturingOrchestrator:
        last_answer = None

        async def run_stream(self, request: AgentRequest) -> AsyncIterator[object]:
            captured["request"] = request
            yield FinalEvent(text="ok")

    @asynccontextmanager
    async def fake_connect() -> AsyncIterator[object]:
        yield object()

    monkeypatch.setattr(executor_module, "connect", fake_connect)
    monkeypatch.setattr(
        executor_module, "build_orchestrator", lambda _mcp: _RequestCapturingOrchestrator()
    )
    monkeypatch.setattr(executor_module, "ConversationRepository", lambda session: session)

    prior = (
        ConversationMessage(
            conversation_id="ctx-1",
            role=MessageRole.user,
            content="What does the Course say about salvation?",
            message_json=None,
            timestamp=datetime(2026, 1, 1),
            sequence=1,
        ),
        ConversationMessage(
            conversation_id="ctx-1",
            role=MessageRole.agent,
            content="Salvation undoes the belief in separation.",
            message_json=None,
            timestamp=datetime(2026, 1, 1),
            sequence=2,
        ),
    )
    conversations = _RecordingConversations(history=prior)
    await MindOfChristExecutor(
        sessions=conversations.as_session_provider()  # type: ignore[arg-type]
    ).execute(
        _FakeContext("how does that relate to forgiveness?"),  # type: ignore[arg-type]
        _RecordingQueue(),  # type: ignore[arg-type]
    )

    # The user turn is appended first (sequence 3), and history is loaded strictly before
    # that sequence -- so the request carries the two prior turns, not the in-flight one.
    assert conversations.history_before_sequence == 3
    request = captured["request"]
    assert request.history == (
        ConversationTurn("user", "What does the Course say about salvation?"),
        ConversationTurn("agent", "Salvation undoes the belief in separation."),
    )
    assert request.situation == "how does that relate to forgiveness?"


@pytest.mark.anyio
@pytest.mark.parametrize("suppress_cancellation", [False, True])
async def test_cancel_stops_tools_and_prevents_completion(
    monkeypatch: pytest.MonkeyPatch, suppress_cancellation: bool
) -> None:
    import asyncio

    tool_started = asyncio.Event()
    disconnected = False
    tool_calls: list[str] = []

    class _Client:
        async def call_tool(self, name: str) -> None:
            tool_calls.append(name)
            tool_started.set()
            await asyncio.Future()

    client = _Client()

    class _Orchestrator:
        last_answer = None

        async def run_stream(self, _request: object) -> AsyncIterator[object]:
            await client.call_tool("find_claims")
            await client.call_tool("infer_chain")
            yield FinalEvent(text="should never complete")

    @asynccontextmanager
    async def fake_connect() -> AsyncIterator[object]:
        nonlocal disconnected
        try:
            yield client
        except asyncio.CancelledError:
            if not suppress_cancellation:
                raise
        finally:
            disconnected = True

    monkeypatch.setattr(executor_module, "connect", fake_connect)
    monkeypatch.setattr(executor_module, "build_orchestrator", lambda _mcp: _Orchestrator())
    monkeypatch.setattr(executor_module, "ConversationRepository", lambda session: session)
    conversations = _RecordingConversations()
    executor = MindOfChristExecutor(
        sessions=conversations.as_session_provider()  # type: ignore[arg-type]
    )
    context = _FakeContext("peace")
    queue = _RecordingQueue()
    execution = asyncio.create_task(
        executor.execute(context, queue)  # type: ignore[arg-type]
    )
    try:
        await asyncio.wait_for(tool_started.wait(), timeout=1)
        # Match the SDK workflow: cancel the producer, then invoke the cancel hook.
        execution.cancel()
        await executor.cancel(context, queue)  # type: ignore[arg-type]
        if suppress_cancellation:
            await execution
        else:
            with pytest.raises(asyncio.CancelledError):
                await execution
    finally:
        if not execution.done():
            execution.cancel()
        await asyncio.gather(execution, return_exceptions=True)

    assert disconnected
    assert tool_calls == ["find_claims"]
    terminal_states = [
        e.status.state
        for e in queue.events
        if isinstance(e, TaskStatusUpdateEvent)
        and e.status.state != TaskState.TASK_STATE_WORKING
    ]
    assert terminal_states == [TaskState.TASK_STATE_CANCELED]
    assert [role for _, role, _, _ in conversations.appended] == [MessageRole.user]


@pytest.mark.anyio
async def test_run_without_cancel_completes_and_is_recoverable(
    stubbed: AgentAnswer,
) -> None:
    # A plain client disconnect does NOT cancel the producer: the SDK's request handler keeps
    # consuming in the background (default_request_handler.py), so only an explicit tasks/cancel
    # propagates CancelledError into execute() (see test_cancel_stops_tools_and_prevents_completion
    # for that pole). This pins the opposite contract -- a run that is never cancelled completes
    # normally and leaves the artifacts a later GetTask / recoverAssistant read needs: the
    # authoritative answer chunk (last_chunk), the evidence artifact, and a persisted agent turn.
    queue = _RecordingQueue()
    conversations = _RecordingConversations()
    await MindOfChristExecutor(
        sessions=conversations.as_session_provider()  # type: ignore[arg-type]
    ).execute(
        _FakeContext("I can't forgive"),  # type: ignore[arg-type]
        queue,  # type: ignore[arg-type]
    )

    statuses = [e for e in queue.events if isinstance(e, TaskStatusUpdateEvent)]
    assert statuses[-1].status.state == TaskState.TASK_STATE_COMPLETED

    artifacts = [e for e in queue.events if isinstance(e, TaskArtifactUpdateEvent)]
    answer_chunks = [a for a in artifacts if a.artifact.artifact_id == "answer"]
    assert answer_chunks[-1].last_chunk is True
    assert "".join(p.text for p in answer_chunks[-1].artifact.parts) == stubbed.text
    assert any(a.artifact.artifact_id == "evidence" for a in artifacts)

    assert [role for _, role, _, _ in conversations.appended] == [
        MessageRole.user,
        MessageRole.agent,
    ]
