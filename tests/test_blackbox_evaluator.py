from evaluation.blackbox.evaluator import CriterionResult, combine


def _gating(status: str) -> CriterionResult:
    return CriterionResult(name="g", kind="gating", status=status)


def _advisory(status: str, score: float | None = None) -> CriterionResult:
    return CriterionResult(name="a", kind="advisory", status=status, score=score)


def test_one_gating_fail_fails_the_case():
    result = combine("c1", [_gating("pass"), _gating("fail"), _advisory("pass", 0.9)])
    assert result.status == "fail"


def test_advisory_fail_alone_still_passes():
    result = combine("c1", [_gating("pass"), _advisory("fail", 0.1)])
    assert result.status == "pass"


def test_not_evaluated_gating_does_not_fail():
    # A gating criterion that was not evaluated (e.g. no required sources named) is not a fail.
    result = combine("c1", [_gating("pass"), _gating("not_evaluated")])
    assert result.status == "pass"


def test_advisory_not_evaluated_does_not_flip():
    result = combine("c1", [_gating("pass"), _advisory("not_evaluated")])
    assert result.status == "pass"
