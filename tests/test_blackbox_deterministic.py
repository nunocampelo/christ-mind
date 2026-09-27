from mind_of_christ_agent.application.answer import (
    CitationDiagnostics,
    CitedClaim,
)

from evaluation.blackbox.deterministic import DeterministicEvaluator
from evaluation.blackbox.evaluator import BlackBoxResponse
from evaluation.blackbox.gold import BlackBoxCase

# A real corpus source_id / claim_id (t2-0-16, the "no order of difficulty" principle).
_REAL_SOURCE = "t2-0-16"
_REAL_CLAIM = "632a5b31428b0a68"


def _claim(claim_id: str = _REAL_CLAIM, source_id: str = _REAL_SOURCE) -> CitedClaim:
    return CitedClaim(
        claim_id=claim_id,
        source_id=source_id,
        subject="miracles",
        predicate="other",
        object="order of difficulty",
        verb_phrase="have no",
        polarity="negated",
        evidence="there is NO order of difficulty in miracles",
    )


def _response(
    answer: str = "There is no order of difficulty. [632a5b31428b0a68]",
    cited: list[CitedClaim] | None = None,
    diagnostics: CitationDiagnostics | None = None,
) -> BlackBoxResponse:
    return BlackBoxResponse(
        question="q",
        answer=answer,
        cited_claims=[_claim()] if cited is None else cited,
        inferred_chains=[],
        citation_diagnostics=diagnostics or CitationDiagnostics(),
    )


def _case(**overrides: object) -> BlackBoxCase:
    base = {
        "id": "t",
        "question": "q",
        "intent": "direct_description",
        "corpus_reality": "adequate",
        "expected_behavior": frozenset(),
        "prohibited_behavior": frozenset(),
        "must_include_source_ids": frozenset(),
        "may_include_source_ids": frozenset(),
        "must_include_claim_ids": frozenset(),
        "may_include_claim_ids": frozenset(),
    }
    base.update(overrides)
    return BlackBoxCase(**base)  # type: ignore[arg-type]


def _crit(results, name):
    return next(c for c in results if c.name == name)


def test_clean_response_passes_gating():
    results = DeterministicEvaluator().evaluate(_case(), _response())
    assert all(c.status != "fail" for c in results)


def test_fabricated_citation_fails():
    diag = CitationDiagnostics(unknown_ids=["deadbeef"])
    results = DeterministicEvaluator().evaluate(_case(), _response(diagnostics=diag))
    assert _crit(results, "citation_integrity").status == "fail"


def test_unknown_source_id_fails():
    bad = [_claim(source_id="not-a-real-source")]
    results = DeterministicEvaluator().evaluate(_case(), _response(cited=bad))
    assert _crit(results, "citation_integrity").status == "fail"


def test_duplicate_cited_claim_fails():
    dup = [_claim(), _claim()]
    results = DeterministicEvaluator().evaluate(_case(), _response(cited=dup))
    assert _crit(results, "citation_integrity").status == "fail"


def test_empty_answer_fails():
    results = DeterministicEvaluator().evaluate(_case(), _response(answer="   "))
    assert _crit(results, "non_empty").status == "fail"


def test_required_source_present_passes_when_hit():
    case = _case(must_include_source_ids=frozenset({_REAL_SOURCE}))
    results = DeterministicEvaluator().evaluate(case, _response())
    assert _crit(results, "required_source_present").status == "pass"


def test_required_source_missing_fails():
    case = _case(must_include_source_ids=frozenset({"t1-1-1"}))
    results = DeterministicEvaluator().evaluate(case, _response())
    assert _crit(results, "required_source_present").status == "fail"


def test_no_required_source_is_not_evaluated():
    results = DeterministicEvaluator().evaluate(_case(), _response())
    assert _crit(results, "required_source_present").status == "not_evaluated"
