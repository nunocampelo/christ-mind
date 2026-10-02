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


def _ground(assertion: str, supported: bool) -> dict:
    # A grounding element carries only the VERBATIM assertion and the supported bool -- no
    # offsets. Python recovers the span by locating the assertion as a substring of the answer.
    return {
        "assertion": assertion,
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
    reply = _reply([_ground(f"God loves you [{M1}].", True)])
    results = LLMEvaluator(_scripted(reply)).evaluate(_case(), _response(answer, M1))
    assert all(c.kind == "advisory" for c in results)
    answers = _get(results, "answers_question")
    assert answers.status == "pass"
    assert answers.score == 0.9


def test_one_unsupported_assertion_fails_grounding_with_fraction_score():
    answer = f"God loves you [{M1}]. God rules weather [{M2}]."
    reply = _reply(
        [
            _ground(f"God loves you [{M1}].", True),
            _ground(f"God rules weather [{M2}].", False),
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
            _ground(f"God loves you [{M1}].", True),
            _ground(f"The Father is greater [{M2}].", True),
        ]
    )
    results = LLMEvaluator(_scripted(reply)).evaluate(_case(), _response(answer, M1, M2))
    g = _get(results, "semantic_grounding")
    assert g.status == "pass"
    assert g.score == 1.0


def test_repeated_marker_mis_cited_use_cannot_hide():
    # Same id on two DIFFERENT clauses: the first mis-cited (unsupported), the second sound. A
    # set-based coverage check could be satisfied by the sound one alone; per-occurrence coverage
    # forces BOTH to be examined, so the mis-cited use fails the answer.
    answer = f"God gives life [{M1}]. Later, God loves you [{M1}]."
    reply = _reply(
        [
            _ground(f"God gives life [{M1}].", False),
            _ground(f"God loves you [{M1}].", True),
        ]
    )
    results = LLMEvaluator(_scripted(reply)).evaluate(_case(), _response(answer, M1))
    g = _get(results, "semantic_grounding")
    assert g.status == "fail"
    assert g.score == 0.5


def test_malformed_grounding_element_invalidates_grounding_alone():
    # A grounding array with a bad element must not take down the valid scalar criteria.
    answer = f"God loves you [{M1}]."
    reply = _reply([{"assertion": f"God loves you [{M1}]."}])  # no supported_by_its_markers
    results = LLMEvaluator(_scripted(reply)).evaluate(_case(), _response(answer, M1))
    g = _get(results, "semantic_grounding")
    assert g.status == "not_evaluated"
    assert g.failure_reason == "parse_failure"
    assert _get(results, "answers_question").status == "pass"
    assert _get(results, "synthesis_fidelity").status == "pass"


def test_non_verbatim_assertion_is_parse_failure():
    # An assertion the judge paraphrased (not a literal substring of the answer) cannot be
    # located, so the span can't be recovered -- rejected, never a guessed pass/fail.
    answer = f"God loves you [{M1}]."
    bad = {
        "assertion": "paraphrased claim not in the answer",
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
    reply = _reply([_ground(f"God loves you [{M1}].", True)])
    results = LLMEvaluator(_scripted(reply)).evaluate(_case(), _response(answer, M1, M2))
    g = _get(results, "semantic_grounding")
    assert g.status == "not_evaluated"
    assert g.failure_reason == "incomplete_coverage"


def test_answer_marker_not_in_supplied_evidence_fails_grounding():
    # A marker the ANSWER cites that resolves to no supplied claim is a grounding DEFECT (the
    # answer mis-cited an id), so grounding FAILS -- it is not an unverifiable not_evaluated.
    answer = f"God loves you [{GHOST}]."
    reply = _reply([_ground(f"God loves you [{GHOST}].", True)])
    results = LLMEvaluator(_scripted(reply)).evaluate(_case(), _response(answer, M1))
    g = _get(results, "semantic_grounding")
    assert g.status == "fail"
    assert g.failure_reason is None


def test_span_clipping_a_marker_leaves_it_uncovered():
    # A verbatim assertion ending right after '[', excluding the id and ']', is a malformed
    # anchor: the partition skips any span that clips a marker, so the [M1] occurrence is covered
    # by nothing and the whole array fails coverage -- never a silent pass.
    answer = f"God loves you [{M1}]."
    open_bracket = answer.index("[")
    clipped = {
        "assertion": answer[: open_bracket + 1],  # "God loves you [" -- clips the marker
        "supported_by_its_markers": True,
        "quote": "",
    }
    results = LLMEvaluator(_scripted(_reply([clipped]))).evaluate(
        _case(), _response(answer, M1)
    )
    g = _get(results, "semantic_grounding")
    assert g.status == "not_evaluated"
    assert g.failure_reason == "incomplete_coverage"


def test_overlapping_spans_with_distinct_markers_fail_coverage():
    # Two verbatim spans whose text ranges overlap: `whole` spans the entire answer (both
    # markers), `second` is a sub-range of it. No non-overlapping assignment covers each marker
    # occurrence exactly once, so the partition yields nothing -- never a silent pass.
    answer = f"God loves you [{M1}] and is greater [{M2}] still."
    whole = _ground(answer, True)
    second = _ground(f"is greater [{M2}]", True)  # a sub-range of `whole`
    results = LLMEvaluator(_scripted(_reply([whole, second]))).evaluate(
        _case(), _response(answer, M1, M2)
    )
    g = _get(results, "semantic_grounding")
    assert g.status == "not_evaluated"
    assert g.failure_reason == "incomplete_coverage"


def test_identical_assertions_resolving_to_multiple_mappings_is_incomplete_coverage():
    # The SAME verbatim clause appears twice (same id both times); two elements copy that
    # identical text, so each could map to either occurrence. More than one assignment satisfies
    # the partition, so per the strict rule the mapping is ambiguous -- reject to
    # incomplete_coverage, never silently pick one, even when the verdicts happen to agree.
    clause = f"God loves you [{M1}]"
    answer = f"{clause}. Again, {clause}."
    reply = _reply([_ground(clause, True), _ground(clause, False)])
    results = LLMEvaluator(_scripted(reply)).evaluate(_case(), _response(answer, M1))
    g = _get(results, "semantic_grounding")
    assert g.status == "not_evaluated"
    assert g.failure_reason == "incomplete_coverage"


def test_ambiguous_repeated_span_assignment_is_incomplete_coverage():
    # Three identical occurrences but only two elements: more than one assignment of elements to
    # occurrences satisfies the partition, so the mapping is genuinely ambiguous. Don't guess --
    # reject to incomplete_coverage rather than silently pick one.
    clause = f"God loves you [{M1}]"
    answer = f"{clause}. {clause}. {clause}."
    reply = _reply([_ground(clause, True), _ground(clause, True)])
    results = LLMEvaluator(_scripted(reply)).evaluate(_case(), _response(answer, M1))
    g = _get(results, "semantic_grounding")
    assert g.status == "not_evaluated"
    assert g.failure_reason == "incomplete_coverage"


def test_uncited_substantive_assertion_marked_true_still_fails_grounding():
    # No marker in the span: ungrounded in code regardless of the returned boolean.
    answer = "God is love."
    reply = _reply([_ground("God is love.", True)])
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
