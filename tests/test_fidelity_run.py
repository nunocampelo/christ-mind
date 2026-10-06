"""Independent literal/derived layer reporting and the complete literal tier.

F5 proves the structured + readable literal report distinguishes the loose and strict tiers
(a dropped negation is loose-correct but strict-wrong) -- a divergence the always-perfect
oracle cannot show. F6 proves the three layer states (unauthored / not_run / scored) stay
distinct and that an unauthored layer is never scored as an all-missing model result,
observed by spying on the scorer and the gold loader, not only by reading report text.
"""

from dataclasses import replace

import pytest

from application.extraction.extract_claims import CandidateClaim, anchor_claim
from domain.claims.models import Attribution, Claim, Mode, Polarity, Predicate
from domain.derivation.models import AuthoringStatus, DerivedGold
from domain.sources.models import Source
from evaluation.claims.fidelity import run
from evaluation.claims.fidelity.report import (
    LayerState,
    LiteralReport,
    RunRecord,
    SourceRun,
    literal_lines,
)
from evaluation.claims.fidelity.run import Split, _coverage, _source_run, run_split
from evaluation.claims.score import score_claims

SOURCE = Source(
    id="p",
    book="ACIM",
    chapter=1,
    text="Forgiveness is an empty gesture unless it entails correction.",
)


def _claim(
    *,
    polarity: Polarity = Polarity.AFFIRMED,
    mode: Mode = Mode.ASSERTION,
    attribution: Attribution = Attribution.COURSE,
) -> Claim:
    return anchor_claim(
        SOURCE,
        CandidateClaim(
            subject="Forgiveness",
            verb_phrase="is",
            object="an empty gesture",
            predicate=Predicate.IS,
            polarity=polarity,
            mode=mode,
            attribution=attribution,
            evidence="Forgiveness is an empty gesture",
        ),
    )


# Each axis flips one qualifier away from the gold's, naming the mismatch counter it must
# increment -- so a future refactor can't drop mode/attribution from the attribution while
# polarity still passes (0038 line 125: mode and attribution are equally observable).
_QUALIFIER_FLIPS = [
    (_claim(polarity=Polarity.NEGATED), "polarity_mismatches"),
    (_claim(mode=Mode.NORMATIVE), "mode_mismatches"),
    (_claim(attribution=Attribution.EGO), "attribution_mismatches"),
]


@pytest.mark.parametrize("predicted,counter", _QUALIFIER_FLIPS)
def test_qualifier_flip_diverges_loose_from_strict(predicted, counter):
    # F5: same triple, one qualifier flipped. Loose (triple only) still matches; strict (which
    # also checks polarity/mode/attribution) does not, and the gap is attributed to the right
    # mismatch counter -- the other two stay zero.
    report = LiteralReport.of(score_claims([predicted], [_claim()]))
    assert (report.loose.true_positives, report.loose.false_positives) == (1, 0)
    assert (
        report.strict.true_positives,
        report.strict.false_positives,
        report.strict.false_negatives,
    ) == (0, 1, 1)
    counters = {"polarity_mismatches", "mode_mismatches", "attribution_mismatches"}
    assert getattr(report, counter) == 1
    assert all(getattr(report, other) == 0 for other in counters - {counter})


def test_polarity_flip_visible_in_readable_and_structured_output():
    # F5: the divergence must be observable in BOTH the readable summary and the typed JSON
    # record, so neither view can quietly report loose success as proof of fidelity.
    report = LiteralReport.of(
        score_claims([_claim(polarity=Polarity.NEGATED)], [_claim()])
    )
    text = "\n".join(literal_lines(report))
    assert "strict (primary)" in text
    assert "polarity 1" in text

    restored = LiteralReport.model_validate_json(report.model_dump_json())
    assert restored.strict.true_positives == 0
    assert restored.polarity_mismatches == 1


def _other_claim() -> Claim:
    return anchor_claim(
        SOURCE,
        CandidateClaim(
            subject="correction",
            verb_phrase="entails",
            object="forgiveness",
            predicate=Predicate.IS,
            polarity=Polarity.AFFIRMED,
            mode=Mode.ASSERTION,
            attribution=Attribution.COURSE,
            evidence="unless it entails correction",
        ),
    )


def test_na_distinct_from_real_zero():
    # F5: no items at all is n/a (null precision), not a misleading 0.0; a real false
    # positive stays visible as precision < 1, never collapsed into n/a. (An invented
    # prediction needs an in-scope gold source to count as an FP -- score_claims scopes to
    # the gold's own sources and is intentionally left unchanged.)
    empty = LiteralReport.of(score_claims([], []))
    assert empty.strict.precision is None
    assert empty.strict.recall is None

    gold = [_claim()]
    invented = LiteralReport.of(score_claims([_claim(), _other_claim()], gold))
    assert invented.strict.precision == 0.5
    assert invented.strict.false_positives == 1


@pytest.mark.parametrize(
    "literal_status,derived_status,expected_literal,expected_derived",
    [
        (AuthoringStatus.UNAUTHORED, AuthoringStatus.UNAUTHORED, LayerState.UNAUTHORED, LayerState.UNAUTHORED),
        (AuthoringStatus.AUTHORED, AuthoringStatus.UNAUTHORED, LayerState.NOT_RUN, LayerState.UNAUTHORED),
        (AuthoringStatus.UNAUTHORED, AuthoringStatus.AUTHORED, LayerState.UNAUTHORED, LayerState.NOT_RUN),
        (AuthoringStatus.AUTHORED, AuthoringStatus.AUTHORED, LayerState.NOT_RUN, LayerState.NOT_RUN),
    ],
)
def test_layer_states_are_independent(
    literal_status, derived_status, expected_literal, expected_derived
):
    # F6: each layer's state is driven by its OWN authoring status, independently. With no
    # prediction wired in this scaffold, an authored layer is NOT_RUN (absent input), never a
    # fabricated all-missing score -- and never conflated with UNAUTHORED.
    gold = DerivedGold(
        source_id="p", literal_status=literal_status, derived_status=derived_status
    )
    run_record = _source_run("p", gold)
    assert run_record.literal_state is expected_literal
    assert run_record.derived_state is expected_derived
    assert run_record.literal is None  # NOT_RUN carries no numbers
    assert run_record.derived is None


def test_authored_empty_gold_is_a_real_negative_target():
    # F6: authored-but-empty gold is a legitimate target, distinct from unauthored. Scoring
    # an invented prediction against it would yield a false positive -- but that is SCORED
    # behavior; here, with no prediction, the authored layer is still NOT_RUN, not UNAUTHORED.
    gold = DerivedGold(
        source_id="p",
        literal_status=AuthoringStatus.AUTHORED,
        derived_status=AuthoringStatus.AUTHORED,
    )
    run_record = _source_run("p", gold)
    assert run_record.literal_state is LayerState.NOT_RUN
    assert run_record.derived_state is LayerState.NOT_RUN


def test_dev_split_reports_coverage_only_without_scoring(monkeypatch):
    # F6: a normal Stage 1 dev run never scores -- the scorer and the literal-claim loader are
    # never invoked for the unauthored layers, so no empty prediction is manufactured into a
    # benchmark result. Observed by spying on the loaders, not just the report text.
    def forbidden(*args, **kwargs):
        raise AssertionError("unauthored layer must not be scored")

    monkeypatch.setattr(run, "score_fidelity", forbidden)
    monkeypatch.setattr(
        "evaluation.claims.gold.load_gold_claims",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("literal gold must not be read")),
    )

    record = run_split(Split.DEV)
    assert record.literal_coverage.authored == 0
    assert record.derived_coverage.authored == 0
    assert record.literal_coverage.total == 5
    assert all(s.literal_state is LayerState.UNAUTHORED for s in record.sources)
    assert all(s.derived_state is LayerState.UNAUTHORED for s in record.sources)


def test_coverage_counts_authored_per_layer():
    # F6: coverage is per layer, so a split with a mix reports each independently.
    assert _coverage(
        [AuthoringStatus.AUTHORED, AuthoringStatus.UNAUTHORED, AuthoringStatus.AUTHORED]
    ).authored == 2


def test_run_record_round_trips():
    record = RunRecord(
        schema_version=2,
        split="dev",
        literal_coverage=_coverage([AuthoringStatus.UNAUTHORED]),
        derived_coverage=_coverage([AuthoringStatus.UNAUTHORED]),
        sources=[SourceRun(source_id="p", literal_state=LayerState.UNAUTHORED, derived_state=LayerState.UNAUTHORED)],
    )
    assert RunRecord.model_validate_json(record.model_dump_json()) == record
