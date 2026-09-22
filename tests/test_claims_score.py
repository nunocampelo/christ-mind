from dataclasses import replace

from domain.claims.models import Attribution, Claim, Mode, Polarity, Predicate
from evaluation.claims.score import ClaimScore, score_claims

NATURAL = Claim(
    source_id="t1-1-6",
    subject="miracles",
    predicate=Predicate.IS,
    object="natural",
    verb_phrase="are",
    polarity=Polarity.AFFIRMED,
    mode=Mode.ASSERTION,
    attribution=Attribution.COURSE,
    evidence_start=3,
    evidence_end=23,
)
PURIFICATION = replace(
    NATURAL,
    source_id="t1-1-7",
    predicate=Predicate.REQUIRES,
    object="purification",
    verb_phrase="is necessary first",
)


def test_identical_claims_score_perfectly():
    report = score_claims([NATURAL, PURIFICATION], [NATURAL, PURIFICATION])

    assert report.strict == ClaimScore(2, 0, 0)
    assert report.strict.precision == report.strict.recall == 1.0


def test_matching_ignores_case_whitespace_and_evidence_span():
    predicted = replace(
        NATURAL, subject="  Miracles ", object="NATURAL", evidence_start=0
    )

    report = score_claims([predicted], [NATURAL])

    assert report.strict == ClaimScore(1, 0, 0)


def test_dropped_negation_is_a_loose_match_but_strict_miss():
    predicted = replace(NATURAL, polarity=Polarity.NEGATED)

    report = score_claims([predicted], [NATURAL])

    assert report.loose == ClaimScore(1, 0, 0)
    assert report.strict == ClaimScore(0, 1, 1)
    assert report.polarity_mismatches == 1
    assert report.mode_mismatches == report.attribution_mismatches == 0


def test_extra_and_missing_claims_count_as_false_positive_and_negative():
    extra = replace(NATURAL, object="habits")

    report = score_claims([NATURAL, extra], [NATURAL, PURIFICATION])

    assert report.loose == ClaimScore(1, 1, 1)
    assert report.loose.precision == report.loose.recall == 0.5


def test_predictions_for_unlabelled_sources_are_ignored():
    unlabelled = replace(NATURAL, source_id="t1-1-99")

    report = score_claims([NATURAL, unlabelled], [NATURAL])

    assert report.strict == ClaimScore(1, 0, 0)


def test_duplicate_triples_pair_strict_matches_first():
    ego_voiced = replace(NATURAL, attribution=Attribution.EGO)

    report = score_claims([ego_voiced, NATURAL], [NATURAL, ego_voiced])

    assert report.strict == ClaimScore(2, 0, 0)
    assert report.attribution_mismatches == 0


def test_no_predictions_scores_zero_without_dividing_by_zero():
    report = score_claims([], [NATURAL])

    assert report.loose == ClaimScore(0, 0, 1)
    assert report.loose.precision == report.loose.recall == 0.0
