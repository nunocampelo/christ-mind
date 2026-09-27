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
# invert. Query relevance adds a verb-phrase tier below object (a needle that only hits
# the verb phrase is a real but weak match); characterization does not use it.
_SUBJECT_POSITION = 100
_OBJECT_POSITION = 50
_VERB_PHRASE_POSITION = 10
_INCIDENTAL = 0


def _role_polarity(claim: Claim) -> tuple[int, int]:
    """The predicate-role and polarity sub-key shared by every ranking intent: role
    (higher is more characterizing), then polarity as a weak tie-break -- a negated claim
    sits just below an equal affirmed one, not at the bottom."""
    role = _ROLE_SCORE[_ROLE_OF[claim.predicate]]
    polarity = 1 if claim.polarity is Polarity.AFFIRMED else 0
    return (role, polarity)


def _score(claim: Claim, forms: frozenset[str]) -> tuple[int, int, int]:
    """Characterization sort key (higher is better), most significant first: entity
    position, then the shared role/polarity sub-key."""
    if claim.subject in forms:
        position = _SUBJECT_POSITION
    elif claim.object is not None and claim.object in forms:
        position = _OBJECT_POSITION
    else:
        position = _INCIDENTAL
    return (position, *_role_polarity(claim))


def rank_characterization_claims(claims: list[Claim], forms: frozenset[str]) -> list[Claim]:
    """Reorder `claims` so those characterizing the entity (the entity in subject
    position, described by an attributive predicate) come first.

    `forms` are the entity's surface forms, exactly as `find_claims_for_entity` already
    resolved them -- the same membership test decides subject/object position here.
    A stable sort keeps equal-scored claims in their input (corpus/extraction) order.
    """
    return sorted(claims, key=lambda c: _score(c, forms), reverse=True)


def _query_position(claim: Claim, needle: str) -> int:
    """Where a query substring lands in the claim, most-relevant first: a term in the
    subject is a definitional hit ("right-mindedness IS healing"), in the object a
    secondary mention, in the verb phrase weaker still, else incidental. Checked
    subject-first, so a needle in both subject and object counts as subject-position."""
    if needle in claim.subject.lower():
        return _SUBJECT_POSITION
    if claim.object is not None and needle in claim.object.lower():
        return _OBJECT_POSITION
    if needle in claim.verb_phrase.lower():
        return _VERB_PHRASE_POSITION
    return _INCIDENTAL


def rank_query_relevance(claims: list[Claim], needle: str) -> list[Claim]:
    """Reorder substring matches for a query so the most on-point come first: the query
    term in subject position beats object beats verb-phrase, then the shared role/polarity
    sub-key. A distinct intent from characterization (a raw query substring, not resolved
    entity forms), so it gets its own strategy per this module's contract. `needle` arrives
    already lowercased from the caller. Reorders only; the caller's `limit` alone drops."""
    return sorted(claims, key=lambda c: (_query_position(c, needle), *_role_polarity(c)), reverse=True)
