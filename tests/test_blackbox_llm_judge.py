from mind_of_christ_agent.application.answer import CitationDiagnostics

from evaluation.blackbox.evaluator import BlackBoxResponse
from evaluation.blackbox.gold import BlackBoxCase
from evaluation.blackbox.llm_judge import LLMEvaluator


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


def _response() -> BlackBoxResponse:
    return BlackBoxResponse(
        question="q",
        answer="an answer",
        cited_claims=[],
        inferred_chains=[],
        citation_diagnostics=CitationDiagnostics(),
    )


def _scripted(reply: str):
    def complete(system: str, user: str) -> str:
        return reply

    return complete


def test_parses_scored_reply_as_advisory():
    reply = (
        '{"answers_question": 0.9, "semantic_grounding": 0.8, '
        '"synthesis_fidelity": 0.7, "epistemic_boundary": 1.0, '
        '"interpretation_marked": 1.0}'
    )
    results = LLMEvaluator(_scripted(reply)).evaluate(_case(), _response())
    assert all(c.kind == "advisory" for c in results)
    answers = next(c for c in results if c.name == "answers_question")
    assert answers.status == "pass"
    assert answers.score == 0.9


def test_low_score_is_advisory_fail_not_gating():
    reply = '{"answers_question": 0.1}'
    results = LLMEvaluator(_scripted(reply)).evaluate(_case(), _response())
    answers = next(c for c in results if c.name == "answers_question")
    assert answers.status == "fail"
    assert answers.kind == "advisory"


def test_malformed_reply_is_not_evaluated():
    results = LLMEvaluator(_scripted("not json at all")).evaluate(_case(), _response())
    assert all(c.status == "not_evaluated" for c in results)


def test_missing_criterion_is_not_evaluated():
    results = LLMEvaluator(_scripted("{}")).evaluate(_case(), _response())
    assert all(c.status == "not_evaluated" for c in results)


def test_raising_complete_degrades_to_not_evaluated():
    def boom(system: str, user: str) -> str:
        raise RuntimeError("proxy down")

    results = LLMEvaluator(boom).evaluate(_case(), _response())
    assert all(c.status == "not_evaluated" for c in results)


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
