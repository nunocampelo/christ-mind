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
from mind_of_christ_agent.domain.orchestrator import Orchestrator, _parse_decision


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
    # Step 1: the LLM picks a tool. Step 2: it answers; the `final` value streams as
    # tokens via the extractor (no separate answer call).
    chat_stream = _scripted_stream(
        '{"tool_call": {"name": "find_claims", "arguments": {"query": "forgiveness"}}}',
        '{"final": "Forgiveness brings peace."}',
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
        '{"final": "answer"}',
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
    chat_stream = _scripted_stream('{"final": "Peace is already yours."}')
    orchestrator = Orchestrator(_StubMapper([]), mcp, chat_stream)

    events = [
        event
        async for event in orchestrator.run_stream(AgentRequest(situation="hi"))
    ]

    assert mcp.calls == []
    assert events[-1] == FinalEvent(text="Peace is already yours.")


@pytest.mark.anyio
async def test_polarity_survives_from_the_tool_result_into_the_cited_claim():
    negated = CallToolResult(
        content=[TextContent(type="text", text="one claim")],
        structured_content={
            "result": [
                _claim_result(
                    claim_id="neg-1",
                    subject="God",
                    object="partial",
                    polarity="negated",
                    evidence="God is NOT partial.",
                )
            ]
        },
    )
    mcp = _FakeMcpClient({"find_claims": negated})
    chat_stream = _scripted_stream(
        '{"tool_call": {"name": "find_claims", "arguments": {"query": "God"}}}',
        '{"final": "The Course says God is not partial."}',
    )
    orchestrator = Orchestrator(_StubMapper(["God"]), mcp, chat_stream)

    async for _ in orchestrator.run_stream(AgentRequest(situation="describe God")):
        pass

    answer = orchestrator.last_answer
    assert answer is not None
    assert [(c.claim_id, c.polarity) for c in answer.cited_claims] == [("neg-1", "negated")]


@pytest.mark.anyio
async def test_final_with_no_retrieved_claims_still_answers_with_empty_evidence():
    # The insufficient-evidence case: the model answers without any cited claims. The
    # prose contract (say so plainly, don't invent advice) is prompt-enforced; here we
    # lock that the structured answer carries an empty evidence set rather than failing.
    mcp = _FakeMcpClient(
        {"find_claims": CallToolResult(content=[], structured_content={"result": []})}
    )
    chat_stream = _scripted_stream(
        '{"final": "I could not find cited claims that address this."}'
    )
    orchestrator = Orchestrator(_StubMapper([]), mcp, chat_stream)

    events = [
        event
        async for event in orchestrator.run_stream(AgentRequest(situation="help"))
    ]

    assert events[-1] == FinalEvent(
        text="I could not find cited claims that address this."
    )
    assert orchestrator.last_answer is not None
    assert orchestrator.last_answer.cited_claims == []
    assert orchestrator.last_answer.inferred_chains == []


@pytest.mark.anyio
async def test_summarizes_when_the_model_never_answers():
    find_claims_result = CallToolResult(
        content=[TextContent(type="text", text="claim")],
        structured_content={"result": [_claim_result()]},
    )
    mcp = _FakeMcpClient({"find_claims": find_claims_result})
    # The model only ever searches; the loop exhausts max_steps. The scripted stream's
    # last reply is the forced answer-only call, which must become the answer.
    chat_stream = _scripted_stream(
        '{"tool_call": {"name": "find_claims", "arguments": {"query": "a"}}}',
        '{"tool_call": {"name": "find_claims", "arguments": {"query": "b"}}}',
        "Here is what the Course offers.",
    )
    orchestrator = Orchestrator(_StubMapper(["forgiveness"]), mcp, chat_stream)

    events = [
        event
        async for event in orchestrator.run_stream(
            AgentRequest(situation="help", max_steps=2)
        )
    ]

    # max_steps=2 tool calls, then the summarize call yields prose.
    assert len(mcp.calls) == 2
    token_text = "".join(e.delta for e in events if isinstance(e, TokenEvent))
    assert token_text == "Here is what the Course offers."
    assert events[-1] == FinalEvent(text="Here is what the Course offers.")
    assert orchestrator.last_answer is not None
    assert orchestrator.last_answer.text == "Here is what the Course offers."
    # The claims gathered during the loop still ride on the structured answer.
    assert [c.claim_id for c in orchestrator.last_answer.cited_claims] == ["c1", "c1"]


@pytest.mark.anyio
async def test_citation_diagnostics_clean_when_prose_cites_a_gathered_claim():
    find_claims_result = CallToolResult(
        content=[TextContent(type="text", text="one claim")],
        structured_content={"result": [_claim_result(claim_id="c1")]},
    )
    mcp = _FakeMcpClient({"find_claims": find_claims_result})
    chat_stream = _scripted_stream(
        '{"tool_call": {"name": "find_claims", "arguments": {"query": "peace"}}}',
        '{"final": "Forgiveness brings peace. [c1]"}',
    )
    orchestrator = Orchestrator(_StubMapper(["forgiveness"]), mcp, chat_stream)

    async for _ in orchestrator.run_stream(AgentRequest(situation="peace", max_steps=4)):
        pass

    answer = orchestrator.last_answer
    assert answer is not None
    assert answer.citation_diagnostics.unknown_ids == []
    assert answer.citation_diagnostics.unused_claim_ids == []


@pytest.mark.anyio
async def test_citation_diagnostics_record_unknown_and_unused_but_still_answer():
    find_claims_result = CallToolResult(
        content=[TextContent(type="text", text="one claim")],
        structured_content={"result": [_claim_result(claim_id="c1")]},
    )
    mcp = _FakeMcpClient({"find_claims": find_claims_result})
    # The prose cites a claim_id that was never gathered (unknown) and never cites the one
    # that was (unused). The turn must still complete -- validation is soft.
    chat_stream = _scripted_stream(
        '{"tool_call": {"name": "find_claims", "arguments": {"query": "peace"}}}',
        '{"final": "Forgiveness brings peace. [made-up]"}',
    )
    orchestrator = Orchestrator(_StubMapper(["forgiveness"]), mcp, chat_stream)

    events = [
        event
        async for event in orchestrator.run_stream(
            AgentRequest(situation="peace", max_steps=4)
        )
    ]

    assert events[-1] == FinalEvent(text="Forgiveness brings peace. [made-up]")
    answer = orchestrator.last_answer
    assert answer is not None
    assert answer.citation_diagnostics.unknown_ids == ["made-up"]
    assert answer.citation_diagnostics.unused_claim_ids == ["c1"]


def test_parse_decision_pulls_tool_call_out_of_reasoning_prose():
    raw = (
        "I have some claims about freedom. Let me explore.\n\n"
        '{"tool_call": {"name": "find_claims", "arguments": {"query": "bondage"}}}'
    )
    decision = _parse_decision(raw)
    assert "tool_call" in decision
    assert "final" not in decision


def test_parse_decision_strips_a_code_fence():
    raw = '```json\n{"final": "Peace."}\n```'
    assert _parse_decision(raw) == {"final": "Peace."}


def test_parse_decision_does_not_leak_raw_prose_as_final():
    # No JSON object at all: an empty decision, never the raw protocol text as an answer.
    assert _parse_decision("Let me think about this out loud.") == {}


@pytest.mark.anyio
async def test_reasoning_wrapped_tool_call_routes_to_the_tool_without_leaking():
    find_claims_result = CallToolResult(
        content=[TextContent(type="text", text="one claim")],
        structured_content={"result": [_claim_result()]},
    )
    mcp = _FakeMcpClient({"find_claims": find_claims_result})
    # Step 1: reasoning prose wrapped around the tool_call. Step 2: a clean final.
    chat_stream = _scripted_stream(
        'Let me look into freedom.\n{"tool_call": {"name": "find_claims", "arguments": {"query": "freedom"}}}',
        '{"final": "Freedom is yours."}',
    )
    orchestrator = Orchestrator(_StubMapper(["freedom"]), mcp, chat_stream)

    events = [
        event
        async for event in orchestrator.run_stream(
            AgentRequest(situation="she doesn't believe she is free", max_steps=4)
        )
    ]

    assert mcp.calls == [("find_claims", {"query": "freedom"})]
    token_text = "".join(e.delta for e in events if isinstance(e, TokenEvent))
    # The reasoning prose and the tool_call JSON never leak into the answer stream.
    assert token_text == "Freedom is yours."
    assert "tool_call" not in token_text
    assert events[-1] == FinalEvent(text="Freedom is yours.")
