from application.retrieval.ranking import rank_characterization_claims
from domain.claims.models import Attribution, Claim, Mode, Polarity, Predicate

FORMS = frozenset({"God"})


def _claim(
    claim_id: str,
    subject: str,
    predicate: Predicate,
    object: str | None,
    polarity: Polarity = Polarity.AFFIRMED,
    attribution: Attribution = Attribution.COURSE,
) -> Claim:
    return Claim(
        claim_id=claim_id,
        source_id="t1-1-1",
        subject=subject,
        predicate=predicate,
        object=object,
        verb_phrase="",
        polarity=polarity,
        mode=Mode.ASSERTION,
        attribution=attribution,
        evidence_start=0,
        evidence_end=1,
    )


ATTRIBUTE = _claim("attr", "God", Predicate.IS, "merciful")
NEGATED_ATTRIBUTE = _claim(
    "neg", "God", Predicate.IS, "partial", polarity=Polarity.NEGATED
)
INCIDENTAL = _claim("obj", "man", Predicate.OTHER, "God")


def test_subject_characterizing_claim_ranks_first():
    ranked = rank_characterization_claims([INCIDENTAL, ATTRIBUTE], FORMS)
    assert [c.claim_id for c in ranked] == ["attr", "obj"]


def test_negated_subject_claim_sits_between_affirmed_subject_and_incidental():
    ranked = rank_characterization_claims(
        [INCIDENTAL, NEGATED_ATTRIBUTE, ATTRIBUTE], FORMS
    )
    # "God is NOT partial" is still characterizing: below the affirmed attribute, but
    # above the incidental object match -- polarity is a tie-break, not a filter.
    assert [c.claim_id for c in ranked] == ["attr", "neg", "obj"]


def test_predicate_role_orders_two_subject_claims():
    is_claim = _claim("is", "God", Predicate.IS, "love")
    creates_claim = _claim("creates", "God", Predicate.CREATES, "Souls")
    ranked = rank_characterization_claims([creates_claim, is_claim], FORMS)
    assert [c.claim_id for c in ranked] == ["is", "creates"]


def test_stable_tie_break_keeps_input_order():
    first = _claim("first", "God", Predicate.IS, "love")
    second = _claim("second", "God", Predicate.IS, "peace")
    ranked = rank_characterization_claims([first, second], FORMS)
    assert [c.claim_id for c in ranked] == ["first", "second"]


def test_ranking_never_drops_a_claim():
    claims = [INCIDENTAL, NEGATED_ATTRIBUTE, ATTRIBUTE]
    ranked = rank_characterization_claims(claims, FORMS)
    assert {c.claim_id for c in ranked} == {c.claim_id for c in claims}
    assert len(ranked) == len(claims)
