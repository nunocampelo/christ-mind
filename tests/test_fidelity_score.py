"""The real proof of scorer correctness: each test provokes one failure mode and asserts it
scores as intended, independent of the others."""

import itertools
from dataclasses import replace

import pytest

from domain.claims.models import Attribution, Mode, Polarity, Predicate
from domain.derivation.models import (
    AuthoringStatus,
    DerivedGold,
    DerivedKind,
    PropositionSig,
    ResolutionStatus,
    Support,
    Variant,
)
from domain.sources.models import Source
from evaluation.claims.fidelity.fixtures import entry
from evaluation.claims.fidelity.score_fidelity import (
    GoldAnchorError,
    _maximum_weight_matching,
    Prediction,
    score_fidelity,
)

# One passage long enough that every quote below is a real, unique substring.
SOURCE = Source(
    id="p",
    book="ACIM",
    chapter=1,
    text=(
        "Forgiveness is an empty gesture unless it entails correction. "
        "Without this, it is essentially judgemental rather than healing. "
        "Truth is always abundant and the questioning mind looks for future answers."
    ),
)

FORGIVENESS = PropositionSig(
    "forgiveness",
    Predicate.IS,
    "an empty gesture",
    Polarity.AFFIRMED,
    Mode.ASSERTION,
    Attribution.COURSE,
)


def _authored(
    *, shared=(), variants=(Variant("v1"),), exhaustive=False
) -> DerivedGold:
    return DerivedGold(
        source_id="p",
        literal_status=AuthoringStatus.AUTHORED,
        derived_status=AuthoringStatus.AUTHORED,
        shared=tuple(shared),
        variants=tuple(variants),
        exhaustive=exhaustive,
    )


def _score(prediction: Prediction, gold: DerivedGold):
    return score_fidelity(prediction, (), gold, (), SOURCE)


def _condition(text="unless it entails correction", scope="when correction is absent", **kw):
    return entry(
        "p",
        DerivedKind.CONDITION,
        "unless it entails correction",
        condition_text=text,
        scope=scope,
        attaches_to=kw.get("attaches_to", FORGIVENESS),
    )


def test_missing_condition_is_a_false_negative_not_hidden_by_mode():
    gold = _authored(shared=(_condition(),))
    report = _score(Prediction("p"), gold)
    # No mode metric can mask this: the condition is simply absent from the prediction.
    assert report.condition.presence.false_negatives == 1
    assert report.condition.presence.true_positives == 0


def test_wrong_antecedent_fails_reference_only_condition_unaffected():
    reference_gold = entry(
        "p", DerivedKind.RESOLVED_REFERENCE, "Without this", mention="this", referent="correction"
    )
    gold = _authored(shared=(_condition(), reference_gold))
    predicted_reference = entry(
        "p", DerivedKind.RESOLVED_REFERENCE, "Without this", mention="this", referent="healing"
    )
    report = _score(Prediction("p", (_condition(), predicted_reference)), gold)

    # Reference aligned but the referent is wrong.
    assert report.reference.aligned == 1
    assert report.reference.referent_matches == 0
    # Condition is untouched -- the two failures are independent.
    assert report.condition.presence.true_positives == 1
    assert report.condition.content_matches == 1
    assert report.condition.scope_matches == 1


def test_invented_qualification_on_plain_passage_is_a_precision_hit():
    gold = _authored()  # no occurrence items at all
    invented = entry(
        "p",
        DerivedKind.OCCURRENCE,
        "Truth is always abundant",
        base_concept="truth",
        scope="invented",
    )
    report = _score(Prediction("p", (invented,)), gold)
    q = report.qualification
    assert (q.true_positives, q.false_positives, q.false_negatives) == (0, 1, 0)
    assert q.precision == 0.0  # the false positive is NOT suppressed
    assert q.recall is None  # no gold items -> recall n/a


def test_contradictory_alternative_mix_is_not_credited():
    occ_v1 = entry(
        "p", DerivedKind.OCCURRENCE, "unless it entails correction", base_concept="forgiveness"
    )
    occ_v2 = entry(
        "p", DerivedKind.OCCURRENCE, "rather than healing", base_concept="judgement"
    )
    gold = _authored(variants=(Variant("v1", (occ_v1,)), Variant("v2", (occ_v2,))))
    # Prediction takes one entry from each incompatible variant.
    report = _score(Prediction("p", (occ_v1, occ_v2)), gold)
    # Only one variant is chosen; its single occurrence is a TP, the cross-variant one an FP.
    assert report.qualification.true_positives == 1
    assert report.qualification.false_positives == 1


def test_duplicate_prediction_counts_once():
    occ = entry(
        "p", DerivedKind.OCCURRENCE, "unless it entails correction", base_concept="forgiveness"
    )
    gold = _authored(shared=(occ,))
    report = _score(Prediction("p", (occ, occ)), gold)
    assert report.qualification.true_positives == 1
    assert report.qualification.false_positives == 1  # the duplicate is excess


def test_unsupported_resolution_vs_abstention():
    unresolved_gold = entry(
        "p",
        DerivedKind.RESOLVED_REFERENCE,
        "Without this",
        mention="this",
        resolution=ResolutionStatus.UNRESOLVED,
    )
    gold = _authored(shared=(unresolved_gold,))

    # Prediction resolves what gold withheld -> unsupported resolution, penalized as such.
    resolved = entry(
        "p", DerivedKind.RESOLVED_REFERENCE, "Without this", mention="this", referent="correction"
    )
    bad = _score(Prediction("p", (resolved,)), gold)
    assert bad.reference.unsupported_resolution == 1
    assert bad.reference.abstention == 0

    # Prediction also abstains -> abstention, neither rewarded nor penalized.
    abstains = entry(
        "p",
        DerivedKind.RESOLVED_REFERENCE,
        "Without this",
        mention="this",
        resolution=ResolutionStatus.UNRESOLVED,
    )
    good = _score(Prediction("p", (abstains,)), gold)
    assert good.reference.abstention == 1
    assert good.reference.unsupported_resolution == 0
    assert good.reference.referent_matches == 0  # abstention is not a referent match


def test_invalid_gold_evidence_raises_not_silently_misses():
    # A gold quote absent from the source invalidates the benchmark; it must raise loudly,
    # unlike a prediction's un-anchorable span (a mere scoring miss).
    bad_gold = entry(
        "p", DerivedKind.OCCURRENCE, "a quote not in the passage", base_concept="x"
    )
    gold = _authored(shared=(bad_gold,))
    with pytest.raises(GoldAnchorError):
        _score(Prediction("p"), gold)


def test_unsupported_inference_only_counted_when_gold_is_exhaustive():
    gold_open = _authored(exhaustive=False)
    gold_closed = _authored(exhaustive=True)
    stray = entry(
        "p", DerivedKind.OCCURRENCE, "Truth is always abundant", base_concept="truth"
    )
    assert _score(Prediction("p", (stray,)), gold_open).unsupported == 0
    assert _score(Prediction("p", (stray,)), gold_closed).unsupported == 1


def test_matching_is_order_independent_for_identical_content():
    # Two gold occurrences, identical content, different spans; both predicted. Whichever
    # order the predictions arrive in, maximum matching credits both.
    g1 = entry("p", DerivedKind.OCCURRENCE, "Truth is always abundant", base_concept="c")
    g2 = entry("p", DerivedKind.OCCURRENCE, "the questioning mind", base_concept="c")
    gold = _authored(shared=(g1, g2))
    p1 = entry("p", DerivedKind.OCCURRENCE, "Truth is always abundant", base_concept="c")
    p2 = entry("p", DerivedKind.OCCURRENCE, "the questioning mind", base_concept="c")
    for order in ((p1, p2), (p2, p1)):
        assert _score(Prediction("p", order), gold).qualification.true_positives == 2


def test_matching_is_maximum_not_greedy():
    # A broad prediction overlaps BOTH gold spans; a narrow one overlaps only the first. A
    # greedy pass could pair the broad one with the first gold and strand the narrow one at
    # 1 TP; maximum matching must find 2 regardless of order.
    g1 = entry("p", DerivedKind.OCCURRENCE, "Forgiveness is an empty gesture", base_concept="c")
    g2 = entry("p", DerivedKind.OCCURRENCE, "healing", base_concept="c")
    gold = _authored(shared=(g1, g2))
    broad = entry("p", DerivedKind.OCCURRENCE, SOURCE.text, base_concept="c")  # overlaps both
    narrow = entry("p", DerivedKind.OCCURRENCE, "Forgiveness", base_concept="c")  # g1 only
    for order in ((broad, narrow), (narrow, broad)):
        assert _score(Prediction("p", order), gold).qualification.true_positives == 2


def test_description_attachment_matched_through_alignment_not_fingerprint():
    # The predicted requirement quote differs (trailing period) so its fingerprint differs,
    # but it aligns to the gold requirement by span; the description that correctly attaches
    # to it must still score a true positive.
    req_g = entry(
        "p",
        DerivedKind.REQUIREMENT,
        "unless it entails correction",
        reframed_proposition=FORGIVENESS,
        reframed_mode="assertion",
    )
    desc_g = entry(
        "p",
        DerivedKind.DESCRIPTION,
        "essentially judgemental",
        description_text="judgemental",
        describes=req_g.annotation_id,
    )
    gold = _authored(shared=(req_g, desc_g))

    req_p = entry(
        "p",
        DerivedKind.REQUIREMENT,
        "unless it entails correction.",  # different quote -> different fingerprint
        reframed_proposition=FORGIVENESS,
        reframed_mode="assertion",
    )
    desc_p = entry(
        "p",
        DerivedKind.DESCRIPTION,
        "essentially judgemental",
        description_text="judgemental",
        describes=req_p.annotation_id,
    )
    report = _score(Prediction("p", (req_p, desc_p)), gold)
    assert report.requirement.true_positives == 1
    assert report.description.true_positives == 1
    assert report.description.false_positives == 0


def test_differing_resolution_description_does_not_pass():
    # A description aligned to gold on span, text, support, and target, differing ONLY in
    # resolution status, must not score a free true positive -- resolution is a different
    # reading for descriptions exactly as for the other dimensions. describes is None on both
    # so the only scored pair is this description (nothing else can inflate unsupported).
    gold_desc = entry(
        "p",
        DerivedKind.DESCRIPTION,
        "empty gesture",
        description_text="judgemental",
        describes=None,
        resolution=ResolutionStatus.RESOLVED,
    )
    gold = _authored(shared=(gold_desc,), exhaustive=True)
    pred_desc = entry(
        "p",
        DerivedKind.DESCRIPTION,
        "empty gesture",
        description_text="judgemental",
        describes=None,
        resolution=ResolutionStatus.UNRESOLVED,
    )
    report = _score(Prediction("p", (pred_desc,)), gold)
    assert (
        report.description.true_positives,
        report.description.false_positives,
        report.description.false_negatives,
    ) == (0, 1, 1)
    assert report.unsupported == 1


def test_matching_resolution_description_is_credited():
    # The control for the above: identical descriptions (same resolution) still score a clean
    # true positive, so the resolution check does not over-correct and deny correct credit.
    gold_desc = entry(
        "p",
        DerivedKind.DESCRIPTION,
        "empty gesture",
        description_text="judgemental",
        describes=None,
        resolution=ResolutionStatus.RESOLVED,
    )
    gold = _authored(shared=(gold_desc,), exhaustive=True)
    pred_desc = entry(
        "p",
        DerivedKind.DESCRIPTION,
        "empty gesture",
        description_text="judgemental",
        describes=None,
        resolution=ResolutionStatus.RESOLVED,
    )
    report = _score(Prediction("p", (pred_desc,)), gold)
    assert (
        report.description.true_positives,
        report.description.false_positives,
        report.description.false_negatives,
    ) == (1, 0, 0)
    assert report.unsupported == 0


def test_differing_resolution_description_with_describes_link_does_not_pass():
    # The two tests above short-circuit the `describes` arm with None; this exercises the full
    # _description_core predicate (text AND _status_eq AND _link_aligns) at once -- a
    # description that aligns on span, text, support, and target, differing only in resolution,
    # must still be penalized even with a live describes link.
    occ_g = entry("p", DerivedKind.OCCURRENCE, "empty gesture", base_concept="c")
    desc_g = entry(
        "p",
        DerivedKind.DESCRIPTION,
        "empty gesture",
        description_text="judgemental",
        describes=occ_g.annotation_id,
        resolution=ResolutionStatus.RESOLVED,
    )
    gold = _authored(shared=(occ_g, desc_g), exhaustive=True)
    occ_p = entry("p", DerivedKind.OCCURRENCE, "empty gesture", base_concept="c")
    desc_p = entry(
        "p",
        DerivedKind.DESCRIPTION,
        "empty gesture",
        description_text="judgemental",
        describes=occ_p.annotation_id,
        resolution=ResolutionStatus.UNRESOLVED,
    )
    report = _score(Prediction("p", (occ_p, desc_p)), gold)
    assert (
        report.description.true_positives,
        report.description.false_positives,
        report.description.false_negatives,
    ) == (0, 1, 1)


def test_differing_support_description_does_not_pass():
    # The resolution tests pin one arm of _status_eq; this pins the other, so a future refactor
    # that drops the support comparison for descriptions is also caught (an interpreted reading
    # must not pass as a literal extraction for the description dimension).
    gold_desc = entry(
        "p",
        DerivedKind.DESCRIPTION,
        "empty gesture",
        description_text="judgemental",
        describes=None,
        support=Support.LITERAL,
    )
    gold = _authored(shared=(gold_desc,), exhaustive=True)
    pred_desc = entry(
        "p",
        DerivedKind.DESCRIPTION,
        "empty gesture",
        description_text="judgemental",
        describes=None,
        support=Support.INTERPRETED,
    )
    report = _score(Prediction("p", (pred_desc,)), gold)
    assert (
        report.description.true_positives,
        report.description.false_positives,
        report.description.false_negatives,
    ) == (0, 1, 1)


def test_reference_wrong_mention_sharing_span_is_not_credited():
    # Both references share the evidence quote but resolve different mentions; the predicted
    # referent coincidentally equals gold's. The mention-span check must deny credit.
    gold_ref = entry(
        "p",
        DerivedKind.RESOLVED_REFERENCE,
        "the questioning mind looks for future answers",
        mention="mind",
        referent="the self",
    )
    gold = _authored(shared=(gold_ref,))
    wrong_mention = entry(
        "p",
        DerivedKind.RESOLVED_REFERENCE,
        "the questioning mind looks for future answers",
        mention="answers",
        referent="the self",
    )
    report = _score(Prediction("p", (wrong_mention,)), gold)
    assert report.reference.presence.true_positives == 1  # a reference is aligned there
    assert report.reference.referent_matches == 0  # but not the right mention


def test_condition_presence_recognizes_a_wrong_scope_condition():
    gold_condition = _condition(scope="right scope")
    gold = _authored(shared=(gold_condition,))
    wrong_scope = _condition(scope="wrong scope")  # present, correct content+attachment
    report = _score(Prediction("p", (wrong_scope,)), gold)
    c = report.condition
    assert (c.presence.true_positives, c.presence.false_positives, c.presence.false_negatives) == (
        1,
        0,
        0,
    )
    assert c.content_matches == 1
    assert c.scope_matches == 0  # the failure is recorded here, not in presence
    assert c.attachment_matches == 1


def test_shared_span_distinct_occurrences_self_predict_perfectly():
    # Two occurrences share one evidence span but read differently. Matching must prefer the
    # semantically-correct pairing, so a self-prediction scores both correct in any order --
    # span-only matching would pair them crosswise and report 0 TP / 2 FP / 2 FN.
    g1 = entry("p", DerivedKind.OCCURRENCE, "an empty gesture", base_concept="X", scope="s")
    g2 = entry("p", DerivedKind.OCCURRENCE, "an empty gesture", base_concept="Y", scope="s")
    gold = _authored(shared=(g1, g2), exhaustive=True)
    for order in itertools.permutations((g1, g2)):
        report = _score(Prediction("p", order), gold)
        assert report.qualification.true_positives == 2
        assert report.unsupported == 0


def test_same_text_descriptions_with_different_targets():
    # Two descriptions share evidence AND text, differing only in which occurrence they
    # attach to. Staged (describes-aware) matching must pair each to its own target.
    occ1 = entry("p", DerivedKind.OCCURRENCE, "Forgiveness", base_concept="c1", scope="s")
    occ2 = entry("p", DerivedKind.OCCURRENCE, "healing", base_concept="c2", scope="s")
    d1 = entry(
        "p", DerivedKind.DESCRIPTION, "empty gesture", description_text="same", describes=occ1.annotation_id
    )
    d2 = entry(
        "p", DerivedKind.DESCRIPTION, "empty gesture", description_text="same", describes=occ2.annotation_id
    )
    gold = _authored(shared=(occ1, occ2, d1, d2), exhaustive=True)
    for order in itertools.permutations((occ1, occ2, d1, d2)):
        report = _score(Prediction("p", order), gold)
        assert report.description.true_positives == 2
        assert report.description.false_positives == 0


def test_variant_selection_prefers_semantic_correctness_then_lowest_id():
    # Two variants differ only in a condition's scope. An exact prediction of one must select
    # THAT variant (presence would tie), with no spurious unsupported inference.
    cond_a = _condition(scope="scope A")
    cond_b = _condition(scope="scope B")
    gold = _authored(variants=(Variant("v1", (cond_a,)), Variant("v2", (cond_b,))), exhaustive=True)
    report = _score(Prediction("p", (cond_b,)), gold)
    assert report.chosen_variant_id == "v2"
    assert report.unsupported == 0

    # A genuine tie (identical variants) breaks to the LOWEST id, regardless of declared order.
    occ = entry("p", DerivedKind.OCCURRENCE, "Forgiveness", base_concept="c")
    tie = _authored(variants=(Variant("v2", (occ,)), Variant("v1", (occ,))), exhaustive=True)
    assert _score(Prediction("p", (occ,)), tie).chosen_variant_id == "v1"


def test_ambiguous_gold_mention_is_invalid_gold():
    # The mention occurs twice in the evidence quote, so its location is ambiguous; even an
    # identical prediction cannot be credited -- the quote must pin the mention.
    source = Source(id="p", book="ACIM", chapter=1, text="this and this again")
    ambiguous = entry(
        "p", DerivedKind.RESOLVED_REFERENCE, "this and this", mention="this", referent="x"
    )
    gold = DerivedGold(
        source_id="p",
        literal_status=AuthoringStatus.AUTHORED,
        derived_status=AuthoringStatus.AUTHORED,
        shared=(ambiguous,),
        variants=(Variant("v1"),),
        exhaustive=True,
    )
    with pytest.raises(GoldAnchorError):
        score_fidelity(Prediction("p", (ambiguous,)), (), gold, (), source)


def test_source_mismatch_raises():
    gold = _authored()
    other = entry("OTHER", DerivedKind.OCCURRENCE, "Forgiveness", base_concept="c")
    with pytest.raises(ValueError):
        score_fidelity(Prediction("p", (other,)), (), gold, (), SOURCE)
    with pytest.raises(ValueError):
        score_fidelity(Prediction("p"), (), gold, (), Source(id="elsewhere", book="A", chapter=1, text="x"))


def test_interpreted_reading_does_not_pass_as_literal():
    gold_occ = entry(
        "p", DerivedKind.OCCURRENCE, "empty gesture", base_concept="c", support=Support.INTERPRETED
    )
    gold = _authored(shared=(gold_occ,), exhaustive=True)
    literal = entry(
        "p", DerivedKind.OCCURRENCE, "empty gesture", base_concept="c", support=Support.LITERAL
    )
    report = _score(Prediction("p", (literal,)), gold)
    assert report.qualification.true_positives == 0
    assert report.unsupported == 1


@pytest.mark.parametrize(
    "rows,columns",
    [(0, 0), (0, 2), (2, 0), (1, 3), (1, 4), (4, 1),
     (2, 2), (2, 3), (3, 2), (3, 3)],
)
def test_weighted_matching_matches_exhaustive_assignment_oracle(rows, columns):
    # States: absent edge, wrong reading, correct reading. Enumerate assignments independently.
    for states in itertools.product(range(3), repeat=rows * columns):
        edges = [states[i * columns:(i + 1) * columns] for i in range(rows)]
        weight = min(rows, columns) + 1
        weights = [
            [0 if cell == 0 else 1 + weight * (cell == 2) for cell in row]
            for row in edges
        ]
        matching = _maximum_weight_matching(weights)
        matched = [(p, g) for g, p in enumerate(matching) if p != -1]
        assert len({p for p, _ in matched}) == len(matched)
        assert all(edges[p][g] != 0 for p, g in matched)
        actual = (sum(edges[p][g] == 2 for p, g in matched), len(matched))
        expected = (0, 0)
        for assignment in itertools.product(range(-1, columns), repeat=rows):
            chosen = [g for g in assignment if g != -1]
            if len(set(chosen)) != len(chosen):
                continue
            pairs = [(p, g) for p, g in enumerate(assignment) if g != -1]
            if any(edges[p][g] == 0 for p, g in pairs):
                continue
            expected = max(
                expected, (sum(edges[p][g] == 2 for p, g in pairs), len(pairs))
            )
        assert actual == expected


@pytest.mark.parametrize("weights", [[[1, 1], [1, 0]], [[4, 1], [4, 0]]])
def test_matching_reroutes_pairs_to_maximize_total(weights):
    assert _maximum_weight_matching(weights) == [1, 0]


def test_two_wrong_conditions_both_align_regardless_of_order():
    source = Source(id="p", book="ACIM", chapter=1, text="alpha beta gamma")
    g1 = replace(_condition(), evidence="alpha beta", condition_text="first")
    g2 = replace(_condition(), evidence="gamma", condition_text="second")
    broad = replace(_condition(), evidence=source.text, condition_text="wrong broad")
    narrow = replace(_condition(), evidence="beta", condition_text="wrong narrow")
    for order in itertools.permutations((broad, narrow)):
        report = score_fidelity(
            Prediction("p", order), (),
            _authored(shared=(g1, g2), exhaustive=True), (), source,
        )
        assert report.condition.presence.true_positives == 2
        assert report.condition.presence.false_positives == 0
        assert report.condition.presence.false_negatives == 0
        assert report.condition.fully_correct == 0
        assert report.unsupported == 2


@pytest.mark.parametrize("resolution", list(ResolutionStatus))
def test_reference_support_mismatch_loses_full_credit_only(resolution):
    reference = entry(
        "p", DerivedKind.RESOLVED_REFERENCE, "Without this", mention="this",
        referent="correction" if resolution is ResolutionStatus.RESOLVED else None,
        resolution=resolution,
    )
    predicted = replace(reference, support=Support.LITERAL)
    report = _score(
        Prediction("p", (predicted,)),
        _authored(shared=(reference,), exhaustive=True),
    )
    assert report.reference.fully_correct == 0
    assert report.unsupported == 1
    assert report.reference.referent_matches == (resolution is ResolutionStatus.RESOLVED)
    assert report.reference.abstention == (resolution is ResolutionStatus.UNRESOLVED)


@pytest.mark.parametrize("location", ["shared", "chosen", "unchosen"])
def test_gold_entry_source_mismatch_is_invalid_gold(location):
    good = entry("p", DerivedKind.OCCURRENCE, "Forgiveness", base_concept="c")
    bad = replace(good, source_id="other")
    gold = _authored(
        shared=(bad,) if location == "shared" else (),
        variants=(
            Variant("a", (bad if location == "chosen" else good,)),
            Variant("z", (bad if location == "unchosen" else good,)),
        ),
    )
    with pytest.raises(ValueError, match="does not own passage"):
        _score(Prediction("p", (good,)), gold)


# Blank mentions ("" / " ") are rejected at construction now (see test_fidelity_identity's
# blank-field checks), so they never reach anchoring; the cases here construct but fail to
# anchor unambiguously (absent from the evidence, or repeated).
@pytest.mark.parametrize("mention", [None, "absent", "this"])
def test_invalid_gold_mentions_raise_but_predictions_are_scoring_misses(mention):
    source = Source(id="p", book="ACIM", chapter=1, text="this and this again")
    valid = entry(
        "p", DerivedKind.RESOLVED_REFERENCE, "this again", mention="this", referent="x"
    )
    invalid = replace(valid, evidence=source.text, mention=mention)
    with pytest.raises(GoldAnchorError):
        score_fidelity(Prediction("p"), (), _authored(shared=(invalid,)), (), source)
    report = score_fidelity(
        Prediction("p", (invalid,)), (),
        _authored(shared=(valid,), exhaustive=True), (), source,
    )
    assert report.reference.referent_matches == 0
    assert report.reference.fully_correct == 0
    assert report.unsupported == 1


def test_same_span_wrong_conditions_have_stable_diagnostics():
    first = _condition(text="first", scope="one")
    second = _condition(text="second", scope="two")
    predicted = (replace(first, scope="wrong"), replace(second, scope="wrong"))
    reports = [
        _score(Prediction("p", order), _authored(shared=gold_order, exhaustive=True))
        for order in itertools.permutations(predicted)
        for gold_order in itertools.permutations((first, second))
    ]
    assert all(report == reports[0] for report in reports)


def _negated_forgiveness() -> PropositionSig:
    return replace(FORGIVENESS, polarity=Polarity.NEGATED)


def test_condition_on_opposite_polarity_proposition_is_present_but_not_correct():
    # F1: the predicted condition sits on the right span but attaches to the opposite-polarity
    # proposition. It is still PRESENT (aligned), but the attachment is wrong, so it is not
    # fully correct -- a dropped negation on the attachment cannot pass as a match.
    gold = _authored(shared=(_condition(attaches_to=FORGIVENESS),), exhaustive=True)
    predicted = _condition(attaches_to=_negated_forgiveness())
    report = _score(Prediction("p", (predicted,)), gold)
    assert report.condition.presence.true_positives == 1  # present on the right evidence
    assert report.condition.attachment_matches == 0  # but attached to the wrong reading
    assert report.condition.fully_correct == 0
    assert report.unsupported == 1


def test_duplicate_gold_entry_fails_before_scoring():
    # F3: two identical shared entries are an authoring mistake, caught before scoring rather
    # than silently deduplicated (which could turn two identical predictions into 2 TP).
    duplicate = _condition()
    gold = _authored(shared=(duplicate, replace(duplicate)), exhaustive=True)
    with pytest.raises(ValueError, match="duplicate entry"):
        _score(Prediction("p"), gold)


def test_duplicate_predictions_stay_one_tp_one_fp():
    # F3: the uniqueness rule is on GOLD, not predictions. One valid gold entry and two
    # identical predictions is still 1 TP (the gold is met once) + 1 FP (the excess).
    occurrence = entry("p", DerivedKind.OCCURRENCE, "Truth is always abundant", base_concept="truth")
    gold = _authored(shared=(occurrence,), exhaustive=True)
    report = _score(Prediction("p", (occurrence, replace(occurrence))), gold)
    assert report.qualification.true_positives == 1
    assert report.qualification.false_positives == 1


def test_entry_shared_across_variants_is_not_rejected_or_double_credited():
    # F3: one entry legitimately appearing in two alternative variants is NOT a duplicate
    # (each variant is its own bundle). It validates, and only the chosen variant is scored,
    # so it is credited once -- not twice.
    occurrence = entry("p", DerivedKind.OCCURRENCE, "Truth is always abundant", base_concept="truth")
    gold = _authored(
        variants=(Variant("a", (occurrence,)), Variant("z", (occurrence,))), exhaustive=True
    )
    report = _score(Prediction("p", (occurrence,)), gold)
    assert report.qualification.true_positives == 1
    assert report.qualification.false_positives == 0


def test_duplicate_variant_ids_rejected():
    # F3: variant ids identify the alternative readings; two with the same id is malformed.
    occurrence = entry("p", DerivedKind.OCCURRENCE, "Truth is always abundant", base_concept="truth")
    other = entry("p", DerivedKind.OCCURRENCE, "future answers", base_concept="questioning")
    gold = _authored(variants=(Variant("dup", (occurrence,)), Variant("dup", (other,))))
    with pytest.raises(ValueError, match="duplicate variant id"):
        _score(Prediction("p"), gold)
