"""Component tests for the orchestrator, mocking only the outermost boundaries: the
MCP client (a fake returning canned tool results), the mapper (a stub `Complete`), and
the streaming LLM (a scripted `chat_stream`). The application and domain layers run for
real, so the test covers the same path production does.
"""

from collections.abc import AsyncIterator

import pytest
from mcp.types import CallToolResult, TextContent, Tool

from mind_of_christ_agent.application.answer import AgentRequest
from mind_of_christ_agent.domain.events import (
    FinalEvent,
    StepStatusEvent,
    TokenEvent,
)
from mind_of_christ_agent.domain.orchestrator import Orchestrator


@pytest.fixture
def anyio_backend():
    return "asyncio"


class _StubMapper:
    def __init__(self, concepts: list[str]):
        self._concepts = concepts

    def map(self, free_text: str) -> list[str]:
        return list(self._concepts)


class _FakeMcpClient:
    """Stands in for the stdio MCP client at the transport boundary. Returns canned
    results keyed by tool name; records the calls it saw."""

    def __init__(self, results: dict[str, CallToolResult]):
        self._results = results
        self.calls: list[tuple[str, dict[str, object]]] = []

    async def list_tools(self) -> list[Tool]:
        return [
            Tool(name=name, description="", input_schema={"type": "object"})
            for name in self._results
        ]

    async def call_tool(self, name: str, arguments: dict[str, object]) -> CallToolResult:
        self.calls.append((name, arguments))
        return self._results[name]


def _scripted_stream(*replies: str):
    calls = {"n": 0}

    async def chat_stream(system: str, user: str) -> AsyncIterator[str]:
        reply = replies[min(calls["n"], len(replies) - 1)]
        calls["n"] += 1
        for ch in reply:
            yield ch

    return chat_stream


def _claim_result(**overrides: object) -> dict[str, object]:
    base = {
        "claim_id": "c1",
        "source_id": "matt-6-14-15",
        "subject": "forgiveness",
        "predicate": "creates",
        "object": "peace",
        "verb_phrase": "creates",
        "polarity": "affirmed",
        "mode": "descriptive",
        "attribution": "course",
        "evidence": "forgive and you will be forgiven",
        "evidence_start": 0,
        "evidence_end": 30,
    }
    base.update(overrides)
    return base


@pytest.mark.anyio
async def test_run_stream_maps_calls_a_cited_tool_then_answers():
    find_claims_result = CallToolResult(
        content=[TextContent(type="text", text="one claim")],
        structured_content={"result": [_claim_result()]},
    )
    mcp = _FakeMcpClient({"find_claims": find_claims_result})
    # Step 1: the LLM picks a tool. Step 2 (decision) + step 3 (answer prose).
    chat_stream = _scripted_stream(
        '{"tool_call": {"name": "find_claims", "arguments": {"query": "forgiveness"}}}',
        '{"final": "draft"}',
        "Forgiveness brings peace.",
    )
    orchestrator = Orchestrator(_StubMapper(["forgiveness"]), mcp, chat_stream)

    events = [
        event
        async for event in orchestrator.run_stream(
            AgentRequest(situation="I can't forgive my friend", max_steps=4)
        )
    ]

    assert mcp.calls == [("find_claims", {"query": "forgiveness"})]
    assert events[0] == StepStatusEvent(text="Mapped situation to 1 concept(s)")
    assert StepStatusEvent(text="Calling find_claims") in events
    assert StepStatusEvent(text="find_claims returned") in events
    token_text = "".join(e.delta for e in events if isinstance(e, TokenEvent))
    assert token_text == "Forgiveness brings peace."
    assert events[-1] == FinalEvent(text="Forgiveness brings peace.")


@pytest.mark.anyio
async def test_cited_claims_and_inferred_chains_stay_distinct():
    find_claims_result = CallToolResult(
        content=[TextContent(type="text", text="cited")],
        structured_content={"result": [_claim_result(claim_id="cited-1")]},
    )
    chain_result = CallToolResult(
        content=[TextContent(type="text", text="chain")],
        structured_content={
            "inferred": True,
            "subject_mention": "fear",
            "predicate": "causes",
            "chains": [
                {
                    "links": [
                        _claim_result(claim_id="link-1"),
                        _claim_result(claim_id="link-2"),
                    ]
                }
            ],
        },
    )
    mcp = _FakeMcpClient({"find_claims": find_claims_result, "chain_claims": chain_result})
    chat_stream = _scripted_stream(
        '{"tool_call": {"name": "find_claims", "arguments": {"query": "fear"}}}',
        '{"tool_call": {"name": "chain_claims", "arguments": {"subject_mention": "fear", "predicate": "causes"}}}',
        '{"final": "draft"}',
        "answer",
    )
    orchestrator = Orchestrator(_StubMapper(["fear"]), mcp, chat_stream)

    async for _ in orchestrator.run_stream(
        AgentRequest(situation="I am afraid", max_steps=5)
    ):
        pass

    answer = orchestrator.last_answer
    assert answer is not None
    # The find_claims result is cited; the chain_claims result is inferred. They never
    # merge into one flat list.
    assert [c.claim_id for c in answer.cited_claims] == ["cited-1"]
    assert len(answer.inferred_chains) == 1
    assert answer.inferred_chains[0].inferred is True
    assert [link.claim_id for link in answer.inferred_chains[0].links] == [
        "link-1",
        "link-2",
    ]


@pytest.mark.anyio
async def test_answers_immediately_when_no_tool_needed():
    mcp = _FakeMcpClient({"find_claims": CallToolResult(content=[], structured_content={"result": []})})
    chat_stream = _scripted_stream('{"final": "draft"}', "Peace is already yours.")
    orchestrator = Orchestrator(_StubMapper([]), mcp, chat_stream)

    events = [
        event
        async for event in orchestrator.run_stream(AgentRequest(situation="hi"))
    ]

    assert mcp.calls == []
    assert events[-1] == FinalEvent(text="Peace is already yours.")
