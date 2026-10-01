from application.retrieval.ranking import (
    rank_characterization_claims,
    rank_query_relevance,
    rank_relational_claims,
)
from domain.claims.models import Attribution, Claim, Mode, Polarity, Predicate

FORMS = frozenset({"God"})


def _claim(
    claim_id: str,
    subject: str,
    predicate: Predicate,
    object: str | None,
    polarity: Polarity = Polarity.AFFIRMED,
    attribution: Attribution = Attribution.COURSE,
    verb_phrase: str = "",
) -> Claim:
    return Claim(
        claim_id=claim_id,
        source_id="t1-1-1",
        subject=subject,
        predicate=predicate,
        object=object,
        verb_phrase=verb_phrase,
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


# --- query-relevance ranking (the find_claims intent) ---

# needle "rm" (a stand-in for the lowercased query) landing in each position.
_RM_SUBJECT = _claim("subj", "rm", Predicate.IS, "healing")  # definitional hit
_RM_OBJECT = _claim("obj", "fear", Predicate.OTHER, "rm")
_RM_VERB = _claim("verb", "fear", Predicate.OTHER, "peace", verb_phrase="upsets rm")
_RM_NONE = _claim("none", "love", Predicate.IS, "maximal", verb_phrase="extends")


def test_query_position_orders_subject_object_verb_incidental():
    ranked = rank_query_relevance([_RM_NONE, _RM_VERB, _RM_OBJECT, _RM_SUBJECT], "rm")
    assert [c.claim_id for c in ranked] == ["subj", "obj", "verb", "none"]


def test_query_subject_beats_object_even_when_matching_both():
    # A needle in both subject and object is classified subject-position (checked first).
    both = _claim("both", "rm", Predicate.OTHER, "rm concern")
    object_only = _claim("objonly", "fear", Predicate.IS, "rm")
    ranked = rank_query_relevance([object_only, both], "rm")
    assert [c.claim_id for c in ranked] == ["both", "objonly"]


def test_query_role_orders_two_subject_matches():
    is_claim = _claim("is", "rm", Predicate.IS, "healing")
    other_claim = _claim("other", "rm", Predicate.OTHER, "something")
    ranked = rank_query_relevance([other_claim, is_claim], "rm")
    assert [c.claim_id for c in ranked] == ["is", "other"]


def test_query_negated_subject_sits_below_affirmed_subject():
    affirmed = _claim("aff", "rm", Predicate.IS, "healing")
    negated = _claim("neg", "rm", Predicate.IS, "sickness", polarity=Polarity.NEGATED)
    ranked = rank_query_relevance([negated, affirmed], "rm")
    assert [c.claim_id for c in ranked] == ["aff", "neg"]


def test_query_tight_subject_beats_incidental_subject_hit():
    # Both are subject-position hits for the needle "rm", but "rm" the whole subject is
    # what a user asking about "rm" actually wants -- a longer subject that just happens
    # to contain "rm" as a substring is an incidental mention. Specificity tie-breaks
    # below position but above role, so a definitional "rm IS healing" still beats
    # "rm details ARE minor" only when the subjects are the same length.
    tight = _claim("tight", "rm", Predicate.IS, "healing")
    loose = _claim("loose", "rm details", Predicate.IS, "important")
    ranked = rank_query_relevance([loose, tight], "rm")
    assert [c.claim_id for c in ranked] == ["tight", "loose"]


def test_query_specificity_tie_break_leaves_role_intact_at_equal_length():
    # Same subject length -> the specificity tie-break contributes nothing, so role
    # still decides between two same-length subjects (IS beats OTHER).
    is_claim = _claim("is", "rm", Predicate.IS, "healing")
    other_claim = _claim("other", "rm", Predicate.OTHER, "something")
    ranked = rank_query_relevance([other_claim, is_claim], "rm")
    assert [c.claim_id for c in ranked] == ["is", "other"]


def test_query_stable_tie_break_keeps_input_order():
    first = _claim("first", "rm", Predicate.IS, "healing")
    second = _claim("second", "rm", Predicate.IS, "wholeness")
    ranked = rank_query_relevance([first, second], "rm")
    assert [c.claim_id for c in ranked] == ["first", "second"]


def test_query_ranking_is_a_permutation_never_drops():
    claims = [_RM_NONE, _RM_VERB, _RM_OBJECT, _RM_SUBJECT]
    ranked = rank_query_relevance(claims, "rm")
    assert {c.claim_id for c in ranked} == {c.claim_id for c in claims}
    assert len(ranked) == len(claims)


# --- relational ranking (the describe_entity intent) ---
#
# Aspect DISCRIMINATION is the property under test, not "OTHER > is": a thinking question
# must prefer knowing evidence, a creating question creation evidence -- from the same
# candidate set, with the same entity forms.

_KNOWS = _claim("knows", "God", Predicate.OTHER, "His Children", verb_phrase="knows")
_CREATES = _claim("creates", "God", Predicate.CREATES, "the Soul", verb_phrase="created")
_THINKING = frozenset({"thinking"})
_CREATING = frozenset({"creating"})


def test_relational_thinking_prefers_knowing_over_creation():
    ranked = rank_relational_claims([_CREATES, _KNOWS], FORMS, _THINKING)
    assert [c.claim_id for c in ranked] == ["knows", "creates"]


def test_relational_creating_prefers_creation_over_knowing():
    # Same candidates and forms as the thinking case -- only the aspect changes, and the
    # order flips. This is the discrimination the plan requires: the two questions must
    # not rank identically.
    ranked = rank_relational_claims([_KNOWS, _CREATES], FORMS, _CREATING)
    assert [c.claim_id for c in ranked] == ["creates", "knows"]


def test_relational_aspect_match_beats_predicate_role():
    # The whole point: an `other`/"knows" claim (role 0) outranks an attributive `is`
    # (role 5) under a thinking aspect, because aspect match sits above role. Role alone
    # would bury exactly the evidence "how does God think?" needs.
    is_claim = _claim("is", "God", Predicate.IS, "love")
    ranked = rank_relational_claims([is_claim, _KNOWS], FORMS, _THINKING)
    assert [c.claim_id for c in ranked] == ["knows", "is"]


def test_relational_verb_aspect_beats_object_aspect():
    # "knows" in the verb phrase (the entity's own action) outranks a claim that only
    # grazes the aspect in its object ("created knowledge").
    verb_hit = _claim("verb", "God", Predicate.OTHER, "His Children", verb_phrase="knows")
    object_hit = _claim(
        "object", "God", Predicate.CREATES, "knowledge", verb_phrase="created"
    )
    ranked = rank_relational_claims([object_hit, verb_hit], FORMS, _THINKING)
    assert [c.claim_id for c in ranked] == ["verb", "object"]


def test_relational_subject_position_beats_object_position():
    subject = _claim("subj", "God", Predicate.OTHER, "His Children", verb_phrase="knows")
    obj = _claim("obj", "man", Predicate.OTHER, "God", verb_phrase="knows")
    ranked = rank_relational_claims([obj, subject], FORMS, _THINKING)
    assert [c.claim_id for c in ranked] == ["subj", "obj"]


def test_relational_empty_aspects_degrade_to_position_and_role():
    # No aspect -> aspect match is uniformly 0, so entity position + role decide, and
    # ranking must not raise.
    is_claim = _claim("is", "God", Predicate.IS, "love")
    ranked = rank_relational_claims([_KNOWS, is_claim], FORMS, frozenset())
    assert [c.claim_id for c in ranked] == ["is", "knows"]


def test_relational_ranking_is_a_permutation_never_drops():
    claims = [_KNOWS, _CREATES]
    ranked = rank_relational_claims(claims, FORMS, _THINKING)
    assert {c.claim_id for c in ranked} == {c.claim_id for c in claims}
    assert len(ranked) == len(claims)
