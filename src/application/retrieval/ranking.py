"""Deterministic, intent-specific claim ranking.

This is *not* a universal relevance function: the weights here answer "characterize
this entity" ("describe God", "tell me about the ego"), where the entity being in
subject position and described by an attributive predicate is what makes a claim
relevant. Other intents want different weights -- "what causes fear?" wants `fear` in
object position -- so each retrieval intent gets its own ranking strategy rather than
one `rank_claims` pretending the intents are interchangeable.

Ranking only reorders; it never drops a claim. `limit` (applied by the caller after
ranking) is the only thing that governs absence.
"""

from enum import Enum, auto

from domain.claims.models import Claim, Polarity, Predicate


class PredicateRole(Enum):
    """Groups the closed `Predicate` set by what the predicate does *to its subject*,
    so the characterization ranking can prefer roles explicitly rather than lumping
    unlike predicates ("is a property of" vs "is an effect of") together."""

    ATTRIBUTE = auto()
    CREATIVE = auto()
    RELATIONAL = auto()
    CAUSAL = auto()
    CONTRASTIVE = auto()
    OTHER = auto()


_ROLE_OF: dict[Predicate, PredicateRole] = {
    Predicate.IS: PredicateRole.ATTRIBUTE,
    Predicate.CREATES: PredicateRole.CREATIVE,
    Predicate.MAKES: PredicateRole.CREATIVE,
    Predicate.EXPRESSES: PredicateRole.RELATIONAL,
    Predicate.REQUIRES: PredicateRole.RELATIONAL,
    Predicate.UNDOES: PredicateRole.RELATIONAL,
    Predicate.CAUSES: PredicateRole.CAUSAL,
    Predicate.CONTRASTS_WITH: PredicateRole.CONTRASTIVE,
    Predicate.OTHER: PredicateRole.OTHER,
}

# For characterization, a property of the subject beats bringing something into being,
# beats a relation/effect, beats a mere contrast or catch-all.
_ROLE_SCORE: dict[PredicateRole, int] = {
    PredicateRole.ATTRIBUTE: 5,
    PredicateRole.CREATIVE: 4,
    PredicateRole.RELATIONAL: 3,
    PredicateRole.CAUSAL: 3,
    PredicateRole.CONTRASTIVE: 1,
    PredicateRole.OTHER: 0,
}

# Position dominates role: subject-position outranks any object-position claim
# regardless of predicate. The gap exceeds the widest role gap so the ordering can't
# invert.
_SUBJECT_POSITION = 100
_OBJECT_POSITION = 50
_INCIDENTAL = 0


def _score(claim: Claim, forms: frozenset[str]) -> tuple[int, int, int]:
    """Sort key (higher is better), most significant first: entity position, then
    predicate role, then polarity as a weak tie-break -- a negated claim ("God is NOT
    partial") is still characterizing, so it sits just below an equal affirmed claim,
    not at the bottom."""
    if claim.subject in forms:
        position = _SUBJECT_POSITION
    elif claim.object is not None and claim.object in forms:
        position = _OBJECT_POSITION
    else:
        position = _INCIDENTAL

    role = _ROLE_SCORE[_ROLE_OF[claim.predicate]]
    polarity = 1 if claim.polarity is Polarity.AFFIRMED else 0
    return (position, role, polarity)


def rank_characterization_claims(claims: list[Claim], forms: frozenset[str]) -> list[Claim]:
    """Reorder `claims` so those characterizing the entity (the entity in subject
    position, described by an attributive predicate) come first.

    `forms` are the entity's surface forms, exactly as `find_claims_for_entity` already
    resolved them -- the same membership test decides subject/object position here.
    A stable sort keeps equal-scored claims in their input (corpus/extraction) order.
    """
    return sorted(claims, key=lambda c: _score(c, forms), reverse=True)
