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


def test_article_and_quote_differences_match_under_loose_and_strict():
    gold = replace(NATURAL, subject="the miracles", object="natural, always")
    predicted = replace(NATURAL, subject="Miracles.", object="natural always?")

    report = score_claims([predicted], [gold])

    assert report.loose == ClaimScore(1, 0, 0)
    assert report.strict == ClaimScore(1, 0, 0)


def test_curly_quotes_fold_to_straight_before_punctuation_is_stripped():
    gold = replace(NATURAL, object="“bigger” than another")
    predicted = replace(NATURAL, object='"bigger" than another')

    assert score_claims([predicted], [gold]).strict == ClaimScore(1, 0, 0)


def test_relaxed_containment_matches_only_when_evidence_overlaps():
    gold = replace(NATURAL, subject="miracles", object="natural state of mind")
    overlapping = replace(
        NATURAL, subject="all miracles", object="natural", evidence_start=10
    )
    disjoint = replace(
        NATURAL,
        subject="all miracles",
        object="natural",
        evidence_start=100,
        evidence_end=140,
    )

    assert score_claims([overlapping], [gold]).relaxed == ClaimScore(1, 0, 0)
    assert score_claims([disjoint], [gold]).relaxed == ClaimScore(0, 1, 1)


def test_relaxed_one_prediction_cannot_satisfy_two_gold_claims():
    broad = replace(NATURAL, subject="love", object="expressions of love")
    gold_a = replace(NATURAL, subject="love", object="expressions")
    gold_b = replace(NATURAL, subject="love", object="expressions", evidence_start=4)

    report = score_claims([broad], [gold_a, gold_b])

    assert report.relaxed == ClaimScore(1, 0, 1)


def test_relaxed_does_not_recount_a_gold_claim_already_matched_strictly():
    gold_exact = NATURAL
    gold_broad = replace(NATURAL, object="natural state", evidence_start=1)
    exact = NATURAL
    broad = replace(NATURAL, object="a natural state of things", evidence_start=1)

    report = score_claims([exact, broad], [gold_exact, gold_broad])

    assert report.strict == ClaimScore(1, 1, 1)
    assert report.relaxed == ClaimScore(2, 0, 0)


def test_relaxed_does_not_match_a_reversed_causes():
    gold = replace(
        NATURAL,
        predicate=Predicate.CAUSES,
        subject="misprojection",
        object="interpretation",
        verb_phrase="causes",
    )
    reversed_claim = replace(gold, subject="interpretation", object="misprojection")

    assert score_claims([reversed_claim], [gold]).relaxed == ClaimScore(0, 1, 1)
