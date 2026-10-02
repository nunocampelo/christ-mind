import time

import pytest

from evaluation.blackbox.calibration.fixtures import (
    CriterionVerdict,
    Derivation,
    Fixture,
    FrozenCase,
)
from evaluation.blackbox.calibration.run import (
    _evaluate,
    _reject_split_leakage,
    _reject_unapproved,
)
from evaluation.blackbox.evaluator import BlackBoxResponse, CriterionResult
from mind_of_christ_agent.application.answer import CitationDiagnostics


def _case(fid: str) -> FrozenCase:
    return FrozenCase(
        id=fid,
        question="q",
        intent="definition",
        corpus_reality="sufficient",
        expected_behavior=[],
        prohibited_behavior=[],
    )


def _response() -> BlackBoxResponse:
    return BlackBoxResponse(
        question="q",
        answer="a",
        cited_claims=[],
        inferred_chains=[],
        citation_diagnostics=CitationDiagnostics(),
    )


def _fixture(
    fid: str,
    verdicts: dict[str, str],
    *,
    split: str = "tune",
    approved: bool = True,
    derived_from: str | None = None,
) -> Fixture:
    return Fixture(
        id=fid,
        role="negative_control" if derived_from else "real",
        split=split,  # type: ignore[arg-type]
        case=_case(fid),
        response=_response(),
        verdicts={
            name: CriterionVerdict(verdict=v, reason="r")  # type: ignore[arg-type]
            for name, v in verdicts.items()
        },
        approved_by="reviewer" if approved else "",
        derivation=(
            Derivation(derived_from=derived_from, edit="swap marker")
            if derived_from
            else None
        ),
    )


class _FakeJudge:
    """Returns a scripted score per fixture-question. Deterministic across repeats unless the
    script lists multiple values, which it cycles -- so a test can force a verdict flip."""

    name = "fake"

    def __init__(self, scores_by_answer: dict[str, list[float]]):
        self._scores = scores_by_answer
        self._calls: dict[str, int] = {}

    def evaluate(self, case, response) -> list[CriterionResult]:  # noqa: ANN001
        key = case.id
        seq = self._scores[key]
        i = self._calls.get(key, 0)
        self._calls[key] = i + 1
        score = seq[i % len(seq)]
        status = "pass" if score >= 0.6 else "fail"
        return [
            CriterionResult(
                name="semantic_grounding", kind="advisory", status=status, score=score
            )
        ]


def test_within_fixture_stability_is_zero_for_a_deterministic_judge():
    # The reproduced bug: two fixtures legitimately scored 0.1 and 0.9 pooled to stdev 0.5
    # even though the judge was perfectly deterministic. Within-fixture stdev must be 0.
    fixtures = [
        _fixture("lo", {"semantic_grounding": "fail"}),
        _fixture("hi", {"semantic_grounding": "pass"}),
    ]
    judge = _FakeJudge({"lo": [0.1], "hi": [0.9]})
    criteria, trials = _evaluate(judge, fixtures, repeats=3)
    stats = criteria["semantic_grounding"]
    assert stats.mean_within_fixture_stdev == 0.0
    assert stats.verdict_flips == 0
    assert stats.agree == 6  # both fixtures agree, 3 repeats each
    assert stats.false_positive == 0 and stats.false_negative == 0
    assert len(trials) == 6


def test_verdict_flip_is_counted_per_fixture():
    fixtures = [_fixture("f", {"semantic_grounding": "pass"})]
    judge = _FakeJudge({"f": [0.9, 0.2]})  # alternates pass/fail across repeats
    criteria, _ = _evaluate(judge, fixtures, repeats=4)
    stats = criteria["semantic_grounding"]
    assert stats.verdict_flips == 1
    assert stats.mean_within_fixture_stdev and stats.mean_within_fixture_stdev > 0


def test_false_positive_and_false_negative_counts():
    fp = _fixture("fp", {"semantic_grounding": "fail"})  # human fail, judge will pass
    fn = _fixture("fn", {"semantic_grounding": "pass"})  # human pass, judge will fail
    judge = _FakeJudge({"fp": [0.9], "fn": [0.1]})
    criteria, _ = _evaluate(judge, [fp, fn], repeats=2)
    stats = criteria["semantic_grounding"]
    assert stats.false_positive == 2
    assert stats.false_negative == 2
    assert stats.agree == 0


def test_not_applicable_verdicts_are_skipped():
    fixtures = [_fixture("f", {"semantic_grounding": "not_applicable"})]
    judge = _FakeJudge({"f": [0.9]})
    criteria, trials = _evaluate(judge, fixtures, repeats=3)
    assert criteria == {}
    assert trials == []


def test_reject_unapproved_fixtures():
    fixtures = [
        _fixture("ok", {"semantic_grounding": "pass"}),
        _fixture("draft", {"semantic_grounding": "pass"}, approved=False),
    ]
    with pytest.raises(SystemExit, match="approved_by"):
        _reject_unapproved(fixtures)


def test_approved_fixtures_pass_the_gate():
    _reject_unapproved([_fixture("ok", {"semantic_grounding": "pass"})])


def test_reject_split_leakage_when_control_and_baseline_differ():
    base = _fixture("real-x", {"semantic_grounding": "pass"}, split="tune")
    control = _fixture(
        "wrong-marker-x",
        {"semantic_grounding": "fail"},
        split="holdout",
        derived_from="real-x",
    )
    with pytest.raises(SystemExit, match="leakage"):
        _reject_split_leakage([base, control])


def test_control_sharing_baseline_split_is_allowed():
    base = _fixture("real-x", {"semantic_grounding": "pass"}, split="tune")
    control = _fixture(
        "wrong-marker-x",
        {"semantic_grounding": "fail"},
        split="tune",
        derived_from="real-x",
    )
    _reject_split_leakage([base, control])


class _UnavailableJudge:
    """Emits a single not_evaluated semantic_grounding result with a fixed failure_reason, so
    a test can assert each unavailable cause lands in the right bucket and never as FP/FN."""

    name = "unavailable"

    def __init__(self, reason: str | None):
        self._reason = reason

    def evaluate(self, case, response) -> list[CriterionResult]:  # noqa: ANN001
        return [
            CriterionResult(
                name="semantic_grounding",
                kind="advisory",
                status="not_evaluated",
                failure_reason=self._reason,  # type: ignore[arg-type]
            )
        ]


@pytest.mark.parametrize(
    "reason,field",
    [
        ("provider_failure", "provider_failure"),
        ("parse_failure", "parse_failure"),
        ("incomplete_coverage", "incomplete_coverage"),
    ],
)
def test_unavailable_judgment_lands_in_its_bucket_not_fp_fn(reason: str, field: str):
    # A human "fail" with a judge not_evaluated must NOT be read as a false negative, and a
    # human "pass" with not_evaluated must NOT be a false positive -- an unavailable judgment
    # is no judgment. Each cause is counted in its own bucket.
    fail_fx = _fixture("f-fail", {"semantic_grounding": "fail"})
    pass_fx = _fixture("f-pass", {"semantic_grounding": "pass"})
    criteria, _ = _evaluate(_UnavailableJudge(reason), [fail_fx, pass_fx], repeats=2)
    stats = criteria["semantic_grounding"]
    assert stats.false_positive == 0
    assert stats.false_negative == 0
    assert stats.agree == 0
    assert getattr(stats, field) == 4  # 2 fixtures x 2 repeats
    buckets = {"provider_failure", "parse_failure", "incomplete_coverage", "unscored"}
    assert all(getattr(stats, b) == 0 for b in buckets - {field})


def test_reasonless_not_evaluated_is_unscored_not_parse_failure():
    # A deliberate out-of-scope not_evaluated (failure_reason None) must NOT inflate
    # parse_failure -- it lands in its own `unscored` bucket.
    fx = _fixture("f", {"semantic_grounding": "fail"})
    criteria, _ = _evaluate(_UnavailableJudge(None), [fx], repeats=2)
    stats = criteria["semantic_grounding"]
    assert stats.unscored == 2
    assert stats.parse_failure == 0
    assert stats.false_positive == 0 and stats.false_negative == 0


def test_failure_reason_survives_into_trials():
    fx = _fixture("f", {"semantic_grounding": "fail"})
    _, trials = _evaluate(_UnavailableJudge("provider_failure"), [fx], repeats=2)
    assert len(trials) == 2
    assert all(t.failure_reason == "provider_failure" for t in trials)
    assert all(t.judge_status == "not_evaluated" for t in trials)


class _StaticJudge:
    """Thread-safe: returns a fixed per-fixture score with no shared mutable state, so trial
    results are identical regardless of thread timing. Sleeps a per-fixture-varying amount so
    workers finish out of submission order -- the equivalence test then proves the fold is
    independent of completion order."""

    name = "static"

    def __init__(self, score_by_id: dict[str, float], delay_by_id: dict[str, float]):
        self._scores = score_by_id
        self._delays = delay_by_id

    def evaluate(self, case, response) -> list[CriterionResult]:  # noqa: ANN001
        time.sleep(self._delays.get(case.id, 0.0))
        score = self._scores[case.id]
        status = "pass" if score >= 0.6 else "fail"
        return [
            CriterionResult(
                name="semantic_grounding", kind="advisory", status=status, score=score
            )
        ]


def test_parallel_matches_serial_under_out_of_order_completion():
    # The core guarantee: with identical trial results, the parallel fold produces a report
    # byte-equal to the serial one, even when workers complete in reverse submission order.
    fixtures = [
        _fixture("a", {"semantic_grounding": "pass"}),
        _fixture("b", {"semantic_grounding": "fail"}),
        _fixture("c", {"semantic_grounding": "pass"}),
    ]
    scores = {"a": 0.9, "b": 0.2, "c": 0.7}
    # Earlier-submitted fixtures sleep longer, forcing out-of-order completion.
    delays = {"a": 0.15, "b": 0.1, "c": 0.0}
    serial = _evaluate(_StaticJudge(scores, {}), fixtures, repeats=3, concurrency=1)
    parallel = _evaluate(_StaticJudge(scores, delays), fixtures, repeats=3, concurrency=4)
    assert serial[0] == parallel[0]  # criteria stats
    assert serial[1] == parallel[1]  # ordered trials


class _RaisingJudge:
    name = "raising"

    def evaluate(self, case, response) -> list[CriterionResult]:  # noqa: ANN001
        raise RuntimeError("unexpected bug in the judge")


@pytest.mark.parametrize("concurrency", [1, 4])
def test_unexpected_exception_propagates(concurrency: int):
    fx = _fixture("f", {"semantic_grounding": "pass"})
    with pytest.raises(RuntimeError, match="unexpected bug"):
        _evaluate(_RaisingJudge(), [fx], repeats=3, concurrency=concurrency)
