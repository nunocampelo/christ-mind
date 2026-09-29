"""Component tests for the orchestrator, mocking only the outermost boundaries: the
MCP client (a fake returning canned tool results), the mapper (a stub `Complete`), and
the streaming LLM (a scripted `chat_stream`). The application and domain layers run for
real, so the test covers the same path production does.
"""

from collections.abc import AsyncIterator

import pytest
from mcp.types import CallToolResult, TextContent, Tool

from mind_of_christ_agent.application.answer import AgentRequest, CitedClaim
from mind_of_christ_agent.domain.events import (
    FinalEvent,
    StepStatusEvent,
    TokenEvent,
)
from mind_of_christ_agent.domain.orchestrator import (
    CitationRehydrationError,
    Orchestrator,
    _call_terms,
    _normalize_term,
    _parse_decision,
    _rehydrate,
)


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

    @property
    def retrieval_calls(self) -> list[tuple[str, dict[str, object]]]:
        # The searches the model drove, excluding the orchestrator's own get_sources
        # rehydration follow-up -- what the retrieval-sequence assertions care about.
        return [call for call in self.calls if call[0] != "get_sources"]

    async def call_tool(self, name: str, arguments: dict[str, object]) -> CallToolResult:
        self.calls.append((name, arguments))
        if name not in self._results:
            # A tool the test didn't script (e.g. the rehydration get_sources call) returns
            # empty rather than raising, so claims fall back to no context -- the benign
            # missing-source path -- and tests opt into rehydration only by scripting it.
            return CallToolResult(content=[], structured_content={"result": []})
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
async def test_run_stream_seeds_mapped_concepts_then_answers():
    find_claims_result = CallToolResult(
        content=[TextContent(type="text", text="one claim")],
        structured_content={"result": [_claim_result()]},
    )
    mcp = _FakeMcpClient({"find_claims": find_claims_result})
    # The mapped concepts are searched in one deterministic seeded batch before any LLM
    # decision, so the model's first decision already has the evidence and answers -- the
    # common path is a single LLM call, not one per concept.
    chat_stream = _scripted_stream('{"final": "Forgiveness brings peace."}')
    orchestrator = Orchestrator(_StubMapper(["forgiveness"]), mcp, chat_stream)

    events = [
        event
        async for event in orchestrator.run_stream(
            AgentRequest(situation="I can't forgive my friend", max_steps=4)
        )
    ]

    assert mcp.retrieval_calls == [("find_claims", {"queries": ["forgiveness"]})]
    assert events[0] == StepStatusEvent(text="Mapped situation to 1 concept(s)")
    assert StepStatusEvent(text="Calling find_claims for 1 mapped concept(s)") in events
    assert StepStatusEvent(text="find_claims returned 1 claim(s)") in events
    token_text = "".join(e.delta for e in events if isinstance(e, TokenEvent))
    assert token_text == "Forgiveness brings peace."
    assert events[-1] == FinalEvent(text="Forgiveness brings peace.")
    answer = orchestrator.last_answer
    assert answer is not None
    assert [c.claim_id for c in answer.cited_claims] == ["c1"]


@pytest.mark.anyio
async def test_run_stream_seeds_all_mapped_concepts_in_one_batch():
    mcp = _FakeMcpClient(
        {
            "find_claims": CallToolResult(
                content=[TextContent(type="text", text="claims")],
                structured_content={"result": [_claim_result()]},
            )
        }
    )
    chat_stream = _scripted_stream('{"final": "answer"}')
    orchestrator = Orchestrator(
        _StubMapper(["forgiveness", "fear", "peace"]), mcp, chat_stream
    )

    async for _ in orchestrator.run_stream(
        AgentRequest(situation="I can't forgive my friend", max_steps=4)
    ):
        pass

    # One seeded batch carrying every mapped concept -- not one call per concept.
    assert mcp.retrieval_calls == [("find_claims", {"queries": ["forgiveness", "fear", "peace"]})]


@pytest.mark.anyio
async def test_meta_question_appends_course_to_seed_batch():
    mcp = _FakeMcpClient(
        {
            "find_claims": CallToolResult(
                content=[TextContent(type="text", text="claims")],
                structured_content={"result": [_claim_result()]},
            )
        }
    )
    chat_stream = _scripted_stream('{"final": "answer"}')
    orchestrator = Orchestrator(_StubMapper(["forgiveness", "atonement"]), mcp, chat_stream)

    async for _ in orchestrator.run_stream(
        AgentRequest(situation="What is the Course all about?", max_steps=4)
    ):
        pass

    # A question about the Course itself supplements the mapped concepts with "course".
    assert mcp.retrieval_calls == [
        ("find_claims", {"queries": ["course", "forgiveness", "atonement"]})
    ]


@pytest.mark.anyio
async def test_meta_supplement_is_not_searched_twice():
    mcp = _FakeMcpClient(
        {
            "find_claims": CallToolResult(
                content=[TextContent(type="text", text="claims")],
                structured_content={"result": [_claim_result()]},
            )
        }
    )
    chat_stream = _scripted_stream('{"final": "answer"}')
    # A mapped concept already folds to "course"; the supplement must not duplicate it.
    orchestrator = Orchestrator(_StubMapper(["the course", "love"]), mcp, chat_stream)

    async for _ in orchestrator.run_stream(
        AgentRequest(situation="What is the Course?", max_steps=4)
    ):
        pass

    # Supplements are seeded first, so the supplement's "course" wins the dedup over the
    # mapped "the course" (same normalized term); searched once, not twice.
    assert mcp.retrieval_calls == [("find_claims", {"queries": ["course", "love"]})]


@pytest.mark.anyio
async def test_non_meta_question_seed_batch_unchanged():
    mcp = _FakeMcpClient(
        {
            "find_claims": CallToolResult(
                content=[TextContent(type="text", text="claims")],
                structured_content={"result": [_claim_result()]},
            )
        }
    )
    chat_stream = _scripted_stream('{"final": "answer"}')
    orchestrator = Orchestrator(_StubMapper(["forgiveness"]), mcp, chat_stream)

    async for _ in orchestrator.run_stream(
        AgentRequest(situation="What does the Course say about forgiveness?", max_steps=4)
    ):
        pass

    # A content question naming the Course must NOT get the supplemental "course" query.
    assert mcp.retrieval_calls == [("find_claims", {"queries": ["forgiveness"]})]


@pytest.mark.anyio
async def test_concept_question_appends_subject_to_seed_batch():
    mcp = _FakeMcpClient(
        {
            "find_claims": CallToolResult(
                content=[TextContent(type="text", text="claims")],
                structured_content={"result": [_claim_result()]},
            )
        }
    )
    chat_stream = _scripted_stream('{"final": "answer"}')
    orchestrator = Orchestrator(_StubMapper(["separation", "fear"]), mcp, chat_stream)

    async for _ in orchestrator.run_stream(
        AgentRequest(situation="What is the ego?", max_steps=4)
    ):
        pass

    # A bare-subject definitional question supplements the mapped concepts with its subject.
    assert mcp.retrieval_calls == [
        ("find_claims", {"queries": ["ego", "separation", "fear"]})
    ]


@pytest.mark.anyio
async def test_concept_subject_matching_a_mapped_concept_is_not_searched_twice():
    mcp = _FakeMcpClient(
        {
            "find_claims": CallToolResult(
                content=[TextContent(type="text", text="claims")],
                structured_content={"result": [_claim_result()]},
            )
        }
    )
    chat_stream = _scripted_stream('{"final": "answer"}')
    # The mapper already emitted "ego"; the concept supplement must dedupe against it.
    orchestrator = Orchestrator(_StubMapper(["ego", "fear"]), mcp, chat_stream)

    async for _ in orchestrator.run_stream(
        AgentRequest(situation="What is the ego?", max_steps=4)
    ):
        pass

    assert mcp.retrieval_calls == [("find_claims", {"queries": ["ego", "fear"]})]


@pytest.mark.anyio
async def test_repeat_tool_call_is_not_re_run():
    empty = CallToolResult(
        content=[TextContent(type="text", text="")],
        structured_content={"result": []},
    )
    mcp = _FakeMcpClient({"find_claims_for_entity": empty})
    # No seed; the model calls the same entity twice (the zero-result retry loop), then
    # answers. The second identical call must be skipped, not sent to the transport.
    chat_stream = _scripted_stream(
        '{"tool_call": {"name": "find_claims_for_entity", "arguments": {"mention": "the Mind of God"}}}',
        '{"tool_call": {"name": "find_claims_for_entity", "arguments": {"mention": "the Mind of God"}}}',
        '{"final": "answer"}',
    )
    orchestrator = Orchestrator(_StubMapper([]), mcp, chat_stream)

    events = [
        event
        # A situation that doesn't seed (no mapped concepts, not a bare-subject/meta
        # question) so this test exercises only the repeat-guard on the model's own calls.
        async for event in orchestrator.run_stream(
            AgentRequest(situation="my friend keeps doubting himself", max_steps=5)
        )
    ]

    # The transport saw the call once, though the model asked twice.
    assert mcp.retrieval_calls == [("find_claims_for_entity", {"mention": "the Mind of God"})]
    status_texts = [e.text for e in events if isinstance(e, StepStatusEvent)]
    assert "Skipped repeat search via find_claims_for_entity" in status_texts
    assert events[-1] == FinalEvent(text="answer")


@pytest.mark.anyio
async def test_article_and_tool_variance_of_a_searched_term_is_skipped():
    empty = CallToolResult(
        content=[TextContent(type="text", text="")],
        structured_content={"result": []},
    )
    mcp = _FakeMcpClient(
        {"find_claims": empty, "find_claims_for_entity": empty, "find_sources": empty}
    )
    # The seed searches "the Mind of God" (normalizes to "mind of god"). A retry that only
    # varies the article ("Mind of God") or switches tool for the same normalized target is
    # a subset of what was already searched, so both are skipped. Article/case/possessive
    # and ordering variance is what normalization catches; genuine rephrasing is not (that
    # is the decision prompt's job), so this test deliberately only varies those.
    chat_stream = _scripted_stream(
        '{"tool_call": {"name": "find_claims_for_entity", "arguments": {"mention": "Mind of God"}}}',
        '{"tool_call": {"name": "find_sources", "arguments": {"query": "the Mind of God"}}}',
        '{"final": "answer"}',
    )
    orchestrator = Orchestrator(_StubMapper(["the Mind of God"]), mcp, chat_stream)

    events = [
        event
        async for event in orchestrator.run_stream(
            AgentRequest(situation="the mind of God", max_steps=6)
        )
    ]

    # Only the seeded find_claims reached the transport; both variance retries were skipped.
    assert mcp.retrieval_calls == [("find_claims", {"queries": ["the Mind of God"]})]
    status_texts = [e.text for e in events if isinstance(e, StepStatusEvent)]
    assert sum(t.startswith("Skipped repeat search") for t in status_texts) == 2
    assert events[-1] == FinalEvent(text="answer")


@pytest.mark.anyio
async def test_status_events_carry_the_call_arguments_and_result_counts():
    find_claims_result = CallToolResult(
        content=[TextContent(type="text", text="claims")],
        structured_content={"result": [_claim_result(claim_id="c1"), _claim_result(claim_id="c2")]},
    )
    entity_result = CallToolResult(
        content=[TextContent(type="text", text="entity")],
        structured_content={"result": [_claim_result(claim_id="e1")]},
    )
    mcp = _FakeMcpClient(
        {"find_claims": find_claims_result, "find_claims_for_entity": entity_result}
    )
    # No seed (empty concepts) so the reactive call's status text is asserted in isolation.
    chat_stream = _scripted_stream(
        '{"tool_call": {"name": "find_claims_for_entity", "arguments": {"mention": "the ego", "limit": 8}}}',
        '{"final": "answer"}',
    )
    orchestrator = Orchestrator(_StubMapper([]), mcp, chat_stream)

    events = [
        event
        async for event in orchestrator.run_stream(
            AgentRequest(situation="tell me about the ego", max_steps=4)
        )
    ]
    status_texts = [e.text for e in events if isinstance(e, StepStatusEvent)]

    # The mention rides in the "Calling" label; the limit does not (noise). The result
    # count rides in the "returned" label.
    assert 'Calling find_claims_for_entity for "the ego"' in status_texts
    assert "find_claims_for_entity returned 1 claim(s)" in status_texts


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
    # The seeded batch retrieves the cited claim; the model only needs the reactive
    # chain_claims follow-up before answering.
    chat_stream = _scripted_stream(
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
    # The seeded batch retrieves the negated claim; the model answers from it directly.
    chat_stream = _scripted_stream('{"final": "The Course says God is not partial."}')
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
        '{"tool_call": {"name": "find_claims", "arguments": {"queries": ["a"]}}}',
        '{"tool_call": {"name": "find_claims", "arguments": {"queries": ["b"]}}}',
        "Here is what the Course offers.",
    )
    # No mapped concepts, so no seeded batch -- the loop is driven purely by the model,
    # exercising the max_steps-exhaustion path in isolation.
    orchestrator = Orchestrator(_StubMapper([]), mcp, chat_stream)

    events = [
        event
        async for event in orchestrator.run_stream(
            AgentRequest(situation="help", max_steps=2)
        )
    ]

    # max_steps=2 tool calls, then the summarize call yields prose.
    assert len(mcp.retrieval_calls) == 2
    token_text = "".join(e.delta for e in events if isinstance(e, TokenEvent))
    assert token_text == "Here is what the Course offers."
    assert events[-1] == FinalEvent(text="Here is what the Course offers.")
    assert orchestrator.last_answer is not None
    assert orchestrator.last_answer.text == "Here is what the Course offers."
    # The claims gathered during the loop still ride on the structured answer -- once,
    # even though two overlapping find_claims calls each returned c1. See
    # test_absorb_dedupes_cited_claims_across_tool_calls for the invariant in isolation.
    assert [c.claim_id for c in orchestrator.last_answer.cited_claims] == ["c1"]


@pytest.mark.anyio
async def test_absorb_dedupes_cited_claims_across_tool_calls():
    # Two different retrieval tools legitimately surface the same claim_id (a batch
    # find_claims followed by a targeted find_claims_for_entity for the same subject).
    # cited_claims must be set-by-id, first-appearance wins, so the eval's
    # citation_integrity duplicate-check stays green and _diagnose_citations counts a
    # single gathered claim.
    first = _claim_result(subject="forgiveness")
    second = _claim_result(subject="mercy")  # same claim_id "c1", different surface form
    find_claims_result = CallToolResult(
        content=[TextContent(type="text", text="claim")],
        structured_content={"result": [first]},
    )
    for_entity_result = CallToolResult(
        content=[TextContent(type="text", text="claim")],
        structured_content={"result": [second]},
    )
    mcp = _FakeMcpClient(
        {"find_claims": find_claims_result, "find_claims_for_entity": for_entity_result}
    )
    chat_stream = _scripted_stream(
        # After the seeded batch already ran find_claims, the model reaches for the same
        # claim via a different tool + a term the seeded batch didn't cover -- so the
        # repeat-search guard doesn't fire and _absorb is what has to hold the invariant.
        '{"tool_call": {"name": "find_claims_for_entity", "arguments": {"mention": "atonement"}}}',
        '{"final": "Forgiveness is the way. [c1]"}',
    )
    orchestrator = Orchestrator(_StubMapper(["forgiveness"]), mcp, chat_stream)

    events = [
        event
        async for event in orchestrator.run_stream(
            AgentRequest(situation="help me forgive", max_steps=4)
        )
    ]

    assert isinstance(events[-1], FinalEvent)
    answer = orchestrator.last_answer
    assert answer is not None
    # Set-by-id, first appearance retained: the seeded find_claims subject wins over the
    # later find_claims_for_entity's differing surface form.
    assert [c.claim_id for c in answer.cited_claims] == ["c1"]
    assert answer.cited_claims[0].subject == "forgiveness"
    # A single marker for c1 resolves; the deterministic evaluator's duplicate check has
    # nothing to flag either (that check runs on cited_claims, which now holds one entry).
    assert answer.citation_diagnostics.unknown_ids == []


@pytest.mark.anyio
async def test_citation_diagnostics_clean_when_prose_cites_a_gathered_claim():
    find_claims_result = CallToolResult(
        content=[TextContent(type="text", text="one claim")],
        structured_content={"result": [_claim_result(claim_id="c1")]},
    )
    mcp = _FakeMcpClient({"find_claims": find_claims_result})
    # Seeded batch gathers c1; the prose then cites it. Diagnostics stay clean.
    chat_stream = _scripted_stream('{"final": "Forgiveness brings peace. [c1]"}')
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
    # the seeded batch did gather (unused). The turn must still complete -- validation is soft.
    chat_stream = _scripted_stream('{"final": "Forgiveness brings peace. [made-up]"}')
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


def test_normalize_term_folds_case_article_and_possessive():
    assert _normalize_term("the Mind of God") == _normalize_term("Mind of God")
    assert _normalize_term("  MIND  of  God ") == "mind of god"
    # A genuine rephrase does NOT collapse -- that is left to the decision prompt.
    assert _normalize_term("Christ's mind") != _normalize_term("the mind of Christ")


def test_call_terms_is_order_independent_and_ignores_limits():
    a = _call_terms({"queries": ["fear", "peace"], "global_limit": 12})
    b = _call_terms({"queries": ["peace", "the fear"], "limit_per_query": 3})
    assert a == b == frozenset({"fear", "peace"})


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
    # No mapped concepts, so the only call is the model's own reactive tool_call.
    chat_stream = _scripted_stream(
        'Let me look into freedom.\n{"tool_call": {"name": "find_claims", "arguments": {"queries": ["freedom"]}}}',
        '{"final": "Freedom is yours."}',
    )
    orchestrator = Orchestrator(_StubMapper([]), mcp, chat_stream)

    events = [
        event
        async for event in orchestrator.run_stream(
            AgentRequest(situation="she doesn't believe she is free", max_steps=4)
        )
    ]

    assert mcp.retrieval_calls == [("find_claims", {"queries": ["freedom"]})]
    token_text = "".join(e.delta for e in events if isinstance(e, TokenEvent))
    # The reasoning prose and the tool_call JSON never leak into the answer stream.
    assert token_text == "Freedom is yours."
    assert "tool_call" not in token_text
    assert events[-1] == FinalEvent(text="Freedom is yours.")


# --- rehydration: claims carry their source paragraph before the answer layer sees them ---

# The real t2-1-7 paragraph and the offsets that anchor "my kind of denial and projection"
# within it. The paragraph defines "my kind" two sentences earlier ("MY use of projection...
# is NOT based on faulty denial. It DOES involve... the very powerful use of the denial of
# errors"), which the bare claim can't carry -- the failure this whole increment fixes.
_T2_1_7 = (
    "False projection arises out of false denial, NOT out of its proper use. My own role "
    "in the Atonement is one of TRUE projection; I can project to YOU the affirmation of "
    "truth. If you project error to me, or to yourself, you are interfering with the "
    "process. MY use of projection, which can also be yours, is NOT based on faulty "
    "denial. It DOES involve, however, the very powerful use of the denial of errors. The "
    "miracle worker is one who accepts my kind of denial and projection, unites his own "
    "inherent abilities to deny and project with mine, and imposes them back on himself "
    "and others. This establishes the total LACK of threat anywhere. Together we can then "
    "work for the real time of peace, which is eternal."
)
_MIRACLE_WORKER_EVIDENCE = (
    "The miracle worker is one who accepts my kind of denial and projection"
)


def _cited_claim(**overrides: object) -> CitedClaim:
    base: dict[str, object] = {
        "claim_id": "c1",
        "source_id": "t2-1-7",
        "subject": "miracle worker",
        "predicate": "is",
        "object": "one who accepts my kind of denial and projection",
        "verb_phrase": "is",
        "polarity": "affirmed",
        "evidence": _MIRACLE_WORKER_EVIDENCE,
        "evidence_start": 408,
        "evidence_end": 478,
    }
    base.update(overrides)
    return CitedClaim(**base)  # type: ignore[arg-type]


def _sources_result(*pairs: tuple[str, str]) -> CallToolResult:
    return CallToolResult(
        content=[TextContent(type="text", text="sources")],
        structured_content={
            "result": [{"id": source_id, "text": text} for source_id, text in pairs]
        },
    )


@pytest.mark.anyio
async def test_rehydrate_attaches_the_source_paragraph_and_the_offsets_anchor_it():
    mcp = _FakeMcpClient({"get_sources": _sources_result(("t2-1-7", _T2_1_7))})

    [claim] = await _rehydrate([_cited_claim()], mcp)

    assert claim.evidence_context == _T2_1_7
    # The load-bearing coordinate-system invariant: offsets index the paragraph, not the clause.
    assert (
        claim.evidence_context[claim.evidence_start : claim.evidence_end]
        == claim.evidence
    )


@pytest.mark.anyio
async def test_rehydrate_batches_and_dedupes_shared_sources_into_one_call():
    mcp = _FakeMcpClient({"get_sources": _sources_result(("t2-1-7", _T2_1_7))})

    await _rehydrate(
        [_cited_claim(claim_id="c1"), _cited_claim(claim_id="c2")], mcp
    )

    assert mcp.calls == [("get_sources", {"source_ids": ["t2-1-7"]})]


@pytest.mark.anyio
async def test_rehydrate_leaves_context_empty_when_the_source_is_missing():
    mcp = _FakeMcpClient({"get_sources": _sources_result()})

    [claim] = await _rehydrate([_cited_claim()], mcp)

    assert claim.evidence_context == ""


@pytest.mark.anyio
async def test_rehydrate_fails_loud_when_a_present_source_no_longer_anchors_the_offsets():
    # The source came back but its text has drifted so the offsets no longer slice the
    # evidence -- a version mismatch or extraction bug. Raise rather than ship a citation
    # whose highlight points at the wrong words.
    drifted = "Some earlier words. " + _T2_1_7
    mcp = _FakeMcpClient({"get_sources": _sources_result(("t2-1-7", drifted))})

    with pytest.raises(CitationRehydrationError):
        await _rehydrate([_cited_claim()], mcp)


@pytest.mark.anyio
async def test_rehydrate_is_idempotent_on_already_hydrated_claims():
    mcp = _FakeMcpClient({"get_sources": _sources_result(("t2-1-7", _T2_1_7))})
    hydrated = _cited_claim(evidence_context=_T2_1_7)

    result = await _rehydrate([hydrated], mcp)

    assert result == [hydrated]
    assert mcp.calls == []


@pytest.mark.anyio
async def test_answer_prompt_carries_the_context_that_resolves_my_kind():
    # End-to-end regression for 95eaa50303ea9c1b: after a real turn, the answer prompt must
    # contain the surrounding text that defines "my kind", so the model never has to infer
    # the antecedent from the bare claim.
    find_claims_result = CallToolResult(
        content=[TextContent(type="text", text="claim")],
        structured_content={
            "result": [
                _claim_result(
                    claim_id="95eaa50303ea9c1b",
                    source_id="t2-1-7",
                    subject="miracle worker",
                    object="one who accepts my kind of denial and projection",
                    evidence=_MIRACLE_WORKER_EVIDENCE,
                    evidence_start=408,
                    evidence_end=478,
                )
            ]
        },
    )
    mcp = _FakeMcpClient(
        {
            "find_claims": find_claims_result,
            "get_sources": _sources_result(("t2-1-7", _T2_1_7)),
        }
    )
    captured: dict[str, str] = {}

    async def capturing_stream(system: str, user: str) -> AsyncIterator[str]:
        captured["user"] = user
        for ch in '{"final": "The miracle worker accepts a corrective denial."}':
            yield ch

    orchestrator = Orchestrator(_StubMapper(["miracles"]), mcp, capturing_stream)

    [
        event
        async for event in orchestrator.run_stream(
            AgentRequest(situation="what is a miracle worker", max_steps=4)
        )
    ]

    answer_prompt = captured["user"]
    assert "MY use of projection" in answer_prompt
    assert "the very powerful use of the denial of errors" in answer_prompt
