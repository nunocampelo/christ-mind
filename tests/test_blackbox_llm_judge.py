import json

import pytest
from mind_of_christ_agent.application.answer import CitationDiagnostics, CitedClaim

from evaluation.blackbox.evaluator import BlackBoxResponse
from evaluation.blackbox.gold import BlackBoxCase
from evaluation.blackbox.llm_judge import LLMEvaluator
from infrastructure.llm.anthropic_proxy import AnthropicProxyError


def _case(corpus_reality: str = "sufficient") -> BlackBoxCase:
    return BlackBoxCase(
        id="t",
        question="q",
        intent="direct_description",
        corpus_reality=corpus_reality,
        expected_behavior=frozenset({"answer_directly"}),
        prohibited_behavior=frozenset(),
        must_include_source_ids=frozenset(),
        must_include_any_source_ids=frozenset(),
        may_include_source_ids=frozenset(),
        must_include_claim_ids=frozenset(),
        must_include_any_claim_ids=frozenset(),
        may_include_claim_ids=frozenset(),
    )


M1 = "a1a1a1a1a1a1a1a1"
M2 = "b2b2b2b2b2b2b2b2"
GHOST = "cccccccccccccccc"


def _response(answer: str = "a plain answer", *supplied: str) -> BlackBoxResponse:
    return BlackBoxResponse(
        question="q",
        answer=answer,
        cited_claims=[_claim(cid) for cid in supplied],
        inferred_chains=[],
        citation_diagnostics=CitationDiagnostics(),
    )


def _claim(claim_id: str) -> CitedClaim:
    return CitedClaim(
        claim_id=claim_id,
        source_id="s",
        subject="x",
        predicate="is",
        object="y",
        verb_phrase="is",
        polarity="affirm",
        evidence="x is y",
        evidence_context="x is y, as the paragraph says.",
    )


def _ground(answer: str, assertion: str, supported: bool, *, nth: int = 0) -> dict:
    # Locate the nth occurrence of `assertion` in `answer` and return an element with its real
    # offsets, mirroring what a correct judge would compute against the ANSWER block.
    start = -1
    for _ in range(nth + 1):
        start = answer.find(assertion, start + 1)
    return {
        "assertion": assertion,
        "char_start": start,
        "char_end": start + len(assertion),
        "supported_by_its_markers": supported,
        "quote": "x is y" if supported else "",
    }


def _reply(grounding: object, **scalars: float) -> str:
    body: dict[str, object] = {
        "answers_question": 0.9,
        "synthesis_fidelity": 0.7,
        "epistemic_boundary": 1.0,
        "interpretation_marked": 1.0,
    }
    body.update(scalars)
    body["semantic_grounding"] = grounding
    return json.dumps(body)


def _scripted(reply: str):
    def complete(system: str, user: str) -> str:
        return reply

    return complete


def _get(results, name: str):
    return next(c for c in results if c.name == name)


def test_parses_scored_reply_as_advisory():
    answer = f"God loves you [{M1}]."
    reply = _reply([_ground(answer, f"God loves you [{M1}].", True)])
    results = LLMEvaluator(_scripted(reply)).evaluate(_case(), _response(answer, M1))
    assert all(c.kind == "advisory" for c in results)
    answers = _get(results, "answers_question")
    assert answers.status == "pass"
    assert answers.score == 0.9


def test_one_unsupported_assertion_fails_grounding_with_fraction_score():
    answer = f"God loves you [{M1}]. God rules weather [{M2}]."
    reply = _reply(
        [
            _ground(answer, f"God loves you [{M1}].", True),
            _ground(answer, f"God rules weather [{M2}].", False),
        ]
    )
    results = LLMEvaluator(_scripted(reply)).evaluate(_case(), _response(answer, M1, M2))
    g = _get(results, "semantic_grounding")
    assert g.status == "fail"
    assert g.score == 0.5
    assert g.failure_reason is None


def test_all_supported_full_coverage_passes_grounding():
    answer = f"God loves you [{M1}]. The Father is greater [{M2}]."
    reply = _reply(
        [
            _ground(answer, f"God loves you [{M1}].", True),
            _ground(answer, f"The Father is greater [{M2}].", True),
        ]
    )
    results = LLMEvaluator(_scripted(reply)).evaluate(_case(), _response(answer, M1, M2))
    g = _get(results, "semantic_grounding")
    assert g.status == "pass"
    assert g.score == 1.0


def test_repeated_marker_mis_cited_use_cannot_hide():
    # Same id on two clauses: the first mis-cited (unsupported), the second sound. A set-based
    # coverage check could be satisfied by the sound one alone; per-occurrence coverage forces
    # BOTH to be examined, so the mis-cited use fails the answer.
    answer = f"God gives life [{M1}]. Later, God loves you [{M1}]."
    reply = _reply(
        [
            _ground(answer, f"God gives life [{M1}].", False, nth=0),
            _ground(answer, f"God loves you [{M1}].", True, nth=0),
        ]
    )
    results = LLMEvaluator(_scripted(reply)).evaluate(_case(), _response(answer, M1))
    g = _get(results, "semantic_grounding")
    assert g.status == "fail"
    assert g.score == 0.5


def test_malformed_grounding_element_invalidates_grounding_alone():
    # A grounding array with a bad element must not take down the valid scalar criteria.
    answer = f"God loves you [{M1}]."
    reply = _reply([{"assertion": f"God loves you [{M1}].", "char_start": 0}])  # no offsets/bool
    results = LLMEvaluator(_scripted(reply)).evaluate(_case(), _response(answer, M1))
    g = _get(results, "semantic_grounding")
    assert g.status == "not_evaluated"
    assert g.failure_reason == "parse_failure"
    assert _get(results, "answers_question").status == "pass"
    assert _get(results, "synthesis_fidelity").status == "pass"


def test_offsets_not_matching_answer_text_is_parse_failure():
    answer = f"God loves you [{M1}]."
    bad = {
        "assertion": "paraphrased claim",
        "char_start": 0,
        "char_end": 5,
        "supported_by_its_markers": True,
        "quote": "",
    }
    results = LLMEvaluator(_scripted(_reply([bad]))).evaluate(
        _case(), _response(answer, M1)
    )
    g = _get(results, "semantic_grounding")
    assert g.status == "not_evaluated"
    assert g.failure_reason == "parse_failure"


def test_empty_grounding_with_cited_markers_is_incomplete_coverage():
    answer = f"God loves you [{M1}]."
    results = LLMEvaluator(_scripted(_reply([]))).evaluate(_case(), _response(answer, M1))
    g = _get(results, "semantic_grounding")
    assert g.status == "not_evaluated"
    assert g.failure_reason == "incomplete_coverage"


def test_uncovered_marker_occurrence_is_incomplete_coverage():
    # The answer carries two markers; the array accounts for only one occurrence.
    answer = f"God loves you [{M1}]. The Father is greater [{M2}]."
    reply = _reply([_ground(answer, f"God loves you [{M1}].", True)])
    results = LLMEvaluator(_scripted(reply)).evaluate(_case(), _response(answer, M1, M2))
    g = _get(results, "semantic_grounding")
    assert g.status == "not_evaluated"
    assert g.failure_reason == "incomplete_coverage"


def test_answer_marker_not_in_supplied_evidence_fails_grounding():
    # A marker the ANSWER cites that resolves to no supplied claim is a grounding DEFECT (the
    # answer mis-cited an id), so grounding FAILS -- it is not an unverifiable not_evaluated.
    answer = f"God loves you [{GHOST}]."
    reply = _reply([_ground(answer, f"God loves you [{GHOST}].", True)])
    results = LLMEvaluator(_scripted(reply)).evaluate(_case(), _response(answer, M1))
    g = _get(results, "semantic_grounding")
    assert g.status == "fail"
    assert g.failure_reason is None


def test_span_clipping_a_marker_is_parse_failure():
    # A span that ends right after '[', excluding the id and ']', must NOT count the marker as
    # covered -- it is a malformed anchor, rejected, never a silent pass.
    answer = f"God loves you [{M1}]."
    open_bracket = answer.index("[")
    clipped = {
        "assertion": answer[: open_bracket + 1],
        "char_start": 0,
        "char_end": open_bracket + 1,  # includes '[' but not the id/']'
        "supported_by_its_markers": True,
        "quote": "",
    }
    results = LLMEvaluator(_scripted(_reply([clipped]))).evaluate(
        _case(), _response(answer, M1)
    )
    g = _get(results, "semantic_grounding")
    assert g.status == "not_evaluated"
    assert g.failure_reason == "parse_failure"


def test_overlapping_spans_with_distinct_markers_is_parse_failure():
    # Two spans whose text ranges overlap, each carrying a different marker occurrence. The
    # per-occurrence check alone wouldn't catch this (distinct markers); the interval check must.
    answer = f"God loves you [{M1}] and is greater [{M2}] still."
    whole = {
        "assertion": answer,
        "char_start": 0,
        "char_end": len(answer),
        "supported_by_its_markers": True,
        "quote": "x is y",
    }
    second = _ground(answer, f"is greater [{M2}]", True)  # a sub-range of `whole`
    results = LLMEvaluator(_scripted(_reply([whole, second]))).evaluate(
        _case(), _response(answer, M1, M2)
    )
    g = _get(results, "semantic_grounding")
    assert g.status == "not_evaluated"
    assert g.failure_reason == "parse_failure"


def test_out_of_range_offsets_is_parse_failure():
    answer = f"God loves you [{M1}]."
    bad = {
        "assertion": answer,
        "char_start": 0,
        "char_end": len(answer) + 10,
        "supported_by_its_markers": True,
        "quote": "",
    }
    results = LLMEvaluator(_scripted(_reply([bad]))).evaluate(
        _case(), _response(answer, M1)
    )
    g = _get(results, "semantic_grounding")
    assert g.status == "not_evaluated"
    assert g.failure_reason == "parse_failure"


def test_uncited_substantive_assertion_marked_true_still_fails_grounding():
    # No marker in the span: ungrounded in code regardless of the returned boolean.
    answer = "God is love."
    reply = _reply([_ground(answer, "God is love.", True)])
    results = LLMEvaluator(_scripted(reply)).evaluate(_case(), _response(answer))
    g = _get(results, "semantic_grounding")
    assert g.status == "fail"


def test_no_markers_no_assertions_grounding_not_evaluated_without_reason():
    answer = "I can't answer that from the material."
    results = LLMEvaluator(_scripted(_reply([]))).evaluate(_case(), _response(answer))
    g = _get(results, "semantic_grounding")
    assert g.status == "not_evaluated"
    assert g.failure_reason is None


def test_low_score_is_advisory_fail_not_gating():
    reply = '{"answers_question": 0.1}'
    results = LLMEvaluator(_scripted(reply)).evaluate(_case(), _response())
    answers = next(c for c in results if c.name == "answers_question")
    assert answers.status == "fail"
    assert answers.kind == "advisory"


def test_malformed_reply_is_parse_failure():
    results = LLMEvaluator(_scripted("not json at all")).evaluate(_case(), _response())
    assert all(c.status == "not_evaluated" for c in results)
    assert all(c.failure_reason == "parse_failure" for c in results)


def test_missing_criterion_is_not_evaluated():
    results = LLMEvaluator(_scripted("{}")).evaluate(_case(), _response())
    assert all(c.status == "not_evaluated" for c in results)


def test_provider_failure_marks_all_not_evaluated_with_reason():
    def boom(system: str, user: str) -> str:
        raise AnthropicProxyError("Anthropic proxy request failed")

    results = LLMEvaluator(boom).evaluate(_case(), _response())
    assert all(c.status == "not_evaluated" for c in results)
    assert all(c.failure_reason == "provider_failure" for c in results)


def test_non_proxy_error_propagates():
    # A programming bug (not a provider or parse failure) must surface, not degrade silently.
    def boom(system: str, user: str) -> str:
        raise RuntimeError("bug")

    with pytest.raises(RuntimeError):
        LLMEvaluator(boom).evaluate(_case(), _response())


# --- premature_abstention: the corpus_reality x abstained truth table ---

def _abstention(results, corpus_reality: str):
    return next(c for c in results if c.name == "premature_abstention")


def _run(reply: str, corpus_reality: str):
    results = LLMEvaluator(_scripted(reply)).evaluate(_case(corpus_reality), _response())
    return _abstention(results, corpus_reality)


def test_sufficient_and_abstained_is_advisory_fail():
    c = _run('{"abstained": 1.0}', "sufficient")
    assert c.kind == "advisory" and c.status == "fail" and c.score == 1.0


def test_sufficient_and_not_abstained_is_advisory_pass():
    c = _run('{"abstained": 0.0}', "sufficient")
    assert c.kind == "advisory" and c.status == "pass"


def test_absent_and_abstained_is_not_evaluated():
    # Correct abstention is out of this criterion's scope -- not penalized, not judged.
    c = _run('{"abstained": 1.0}', "absent")
    assert c.status == "not_evaluated"


def test_insufficient_and_abstained_is_not_evaluated():
    c = _run('{"abstained": 1.0}', "insufficient")
    assert c.status == "not_evaluated"


def test_missing_abstained_on_sufficient_degrades_not_evaluated():
    # The load-bearing case: judge failure => "we don't know", never "the agent abstained".
    c = _run('{"answers_question": 0.9}', "sufficient")
    assert c.status == "not_evaluated"


def test_malformed_reply_abstention_is_not_evaluated_not_fail():
    results = LLMEvaluator(_scripted("not json")).evaluate(_case("sufficient"), _response())
    assert _abstention(results, "sufficient").status == "not_evaluated"
