"""Tests for `evaluation.blackbox.classify.FailureClassificationEvaluator`. Exercises
the four branches (nothing required, all retrieved and cited, retrieval miss classed
A vs. B, retrieved-but-uncited classed C) with real corpus ids so a change to the
ranker or the corpus surfaces here.
"""

from mind_of_christ_agent.application.answer import CitationDiagnostics, CitedClaim

from evaluation.blackbox.classify import FailureClassificationEvaluator
from evaluation.blackbox.evaluator import BlackBoxResponse
from evaluation.blackbox.gold import BlackBoxCase


def _claim(claim_id: str) -> CitedClaim:
    return CitedClaim(
        claim_id=claim_id,
        source_id="t1-0-1",
        subject="s",
        predicate="is",
        object=None,
        verb_phrase="is",
        polarity="affirmed",
        evidence="e",
    )


def _response(
    cited_ids: list[str],
    question: str = "q",
    unused: list[str] | None = None,
) -> BlackBoxResponse:
    return BlackBoxResponse(
        question=question,
        answer="a",
        cited_claims=[_claim(cid) for cid in cited_ids],
        inferred_chains=[],
        citation_diagnostics=CitationDiagnostics(
            unknown_ids=[], unused_claim_ids=unused or []
        ),
    )


def _case(
    question: str = "q",
    must_include_claim_ids: frozenset[str] = frozenset(),
    must_include_any_claim_ids: frozenset[str] = frozenset(),
) -> BlackBoxCase:
    return BlackBoxCase(
        id="t",
        question=question,
        intent="direct_description",
        corpus_reality="sufficient",
        expected_behavior=frozenset(),
        prohibited_behavior=frozenset(),
        must_include_source_ids=frozenset(),
        must_include_any_source_ids=frozenset(),
        may_include_source_ids=frozenset(),
        must_include_claim_ids=must_include_claim_ids,
        must_include_any_claim_ids=must_include_any_claim_ids,
        may_include_claim_ids=frozenset(),
    )


def test_case_with_no_required_claims_yields_not_evaluated():
    evaluator = FailureClassificationEvaluator()
    result = evaluator.evaluate(_case(), _response(cited_ids=[]))
    assert len(result) == 1
    assert result[0].status == "not_evaluated"
    assert result[0].kind == "advisory"


def test_all_required_retrieved_and_cited_yields_pass_with_clean_detail():
    # A `must_include` id that was retrieved AND marker-cited (not in unused): no
    # unsatisfied, no C. Detail is the "all clear" line with the reachability version.
    evaluator = FailureClassificationEvaluator()
    result = evaluator.evaluate(
        _case(must_include_claim_ids=frozenset({"x1"})),
        _response(cited_ids=["x1"], unused=[]),
    )
    assert result[0].status == "pass"
    assert "all required evidence retrieved and cited" in result[0].detail
    assert "v1" in result[0].detail


def test_missing_required_lexically_reachable_classifies_as_A():
    # course-about-006's required ids are lexically reachable from "What is the
    # Course all about?" (the ranker fix guarantees the top-12 batch surfaces them).
    # A run that failed to retrieve them is classified A -- ranking/query gen, not
    # a semantic gap.
    evaluator = FailureClassificationEvaluator()
    result = evaluator.evaluate(
        _case(
            question="What is the Course all about?",
            must_include_any_claim_ids=frozenset({"44e9f68768054c02", "934b7f695826e53c"}),
        ),
        _response(cited_ids=[]),  # nothing retrieved
    )
    detail = result[0].detail
    assert "A[" in detail
    assert "44e9f68768054c02" in detail and "934b7f695826e53c" in detail
    assert "B[" not in detail


def test_missing_required_lexically_unreachable_classifies_as_B():
    # mind-of-god-004b's required ids share no token with its question; the
    # plausible-query probe returns False. A run that missed them is a semantic
    # retrieval gap, not a ranking one.
    evaluator = FailureClassificationEvaluator()
    result = evaluator.evaluate(
        _case(
            question="How does God think? What is the Mind of God?",
            must_include_any_claim_ids=frozenset({
                "efdccd0ac72007aa", "f99fd11eb731987c",
            }),
        ),
        _response(cited_ids=[]),
    )
    detail = result[0].detail
    assert "B[" in detail
    assert "efdccd0ac72007aa" in detail and "f99fd11eb731987c" in detail
    assert "A[" not in detail


def test_retrieved_but_uncited_classifies_as_C():
    # The strict `must_include_claim_ids` id was retrieved (present in cited_claims,
    # i.e. gathered by a tool) but never marker-cited in the prose. The
    # citation_diagnostics.unused_claim_ids flags it. That's a synthesis failure,
    # not retrieval -- report it as C, distinct from A/B.
    evaluator = FailureClassificationEvaluator()
    result = evaluator.evaluate(
        _case(must_include_claim_ids=frozenset({"x1"})),
        _response(cited_ids=["x1"], unused=["x1"]),
    )
    detail = result[0].detail
    assert "C[x1]" in detail
    assert "A[" not in detail and "B[" not in detail


def test_must_include_any_group_satisfied_when_one_retrieved():
    # `must_include_any` is group-satisfied: retrieving one member means the group
    # counts as reached, so no A/B is reported even if the other members weren't
    # retrieved (they weren't required individually).
    evaluator = FailureClassificationEvaluator()
    result = evaluator.evaluate(
        _case(
            question="What is the Course all about?",
            must_include_any_claim_ids=frozenset({"44e9f68768054c02", "934b7f695826e53c"}),
        ),
        _response(cited_ids=["44e9f68768054c02"]),
    )
    detail = result[0].detail
    assert "A[" not in detail and "B[" not in detail
