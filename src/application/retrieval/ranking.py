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

import re
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
    term in subject position beats object beats verb-phrase, then a subject-specificity
    tie-break (a shorter subject that the needle nearly fills -- `'the course'` for
    `"course"` -- outranks a longer subject where the needle is embedded incidentally --
    `'first point in this course'`), then the shared role/polarity sub-key. A distinct
    intent from characterization (a raw query substring, not resolved entity forms), so
    it gets its own strategy per this module's contract. `needle` arrives already
    lowercased from the caller. Reorders only; the caller's `limit` alone drops."""
    return sorted(
        claims,
        key=lambda c: (
            _query_position(c, needle),
            -len(c.subject),
            *_role_polarity(c),
        ),
        reverse=True,
    )


# --- relational intent: "how does X act/relate/think" ---
#
# An aspect ("thinking") names WHERE to look, not a claim that two words mean the same
# thing: it maps to the STEMS the Course's wordings for that aspect start with, and a
# claim matches when a word of its verb_phrase or object is prefixed by one. The map is
# the single place this "related vocabulary" lives, kept apart from the claim so ranking
# never rewrites what a passage says (see the graph-tier plan's three connection types).
# Stems, not whole words, so "know" catches "knows"/"knowing"/"known" and "thought"
# catches "thoughts" -- the corpus keeps the author's own inflections. Match is
# per-word-prefix, so a stem never leaks across a word boundary.
_ASPECT_FAMILIES: dict[str, frozenset[str]] = {
    "thinking": frozenset({"think", "thought", "know", "knowledge", "mind", "idea"}),
    "creating": frozenset({"create", "made", "make", "giv", "extend"}),
    "willing": frozenset({"will", "intend", "choos", "chose"}),
    "loving": frozenset({"love", "cherish", "care"}),
}

# An aspect matched in the entity's own action (the verb phrase, "God KNOWS") is a
# stronger "how does X act" signal than a match that only grazes the object ("God created
# KNOWLEDGE" mentions the aspect incidentally). Kept above predicate role so a "knows"
# claim isn't sunk by `other`'s low role.
_VERB_ASPECT_MATCH = 2
_OBJECT_ASPECT_MATCH = 1
_NO_ASPECT_MATCH = 0


def _aspect_stems(requested_aspects: frozenset[str]) -> frozenset[str]:
    """The stems an aspect request expands to. An aspect not in the map contributes its
    own literal term as a stem, so a caller can pass a raw wording ("peace") directly."""
    stems: set[str] = set()
    for aspect in requested_aspects:
        stems |= _ASPECT_FAMILIES.get(aspect, frozenset({aspect}))
    return frozenset(s.lower() for s in stems)


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z]+", text.lower()))


def _has_stem(text: str, stems: frozenset[str]) -> bool:
    return any(word.startswith(stem) for word in _words(text) for stem in stems)


def _aspect_match(claim: Claim, stems: frozenset[str]) -> int:
    """How the claim's own wording carries a requested aspect: in the verb phrase (the
    entity's action) beats in the object beats not at all. Per-word prefix match so
    "know" catches "knows"/"knowing" without leaking across a word boundary."""
    if _has_stem(claim.verb_phrase, stems):
        return _VERB_ASPECT_MATCH
    if claim.object is not None and _has_stem(claim.object, stems):
        return _OBJECT_ASPECT_MATCH
    return _NO_ASPECT_MATCH


def explain_aspect_match(claim: Claim, requested_aspects: frozenset[str]) -> str | None:
    """Where a requested aspect landed in the claim's own wording -- `"verb_phrase"`,
    `"object"`, or `None` for no match -- so a caller can record *why* a claim ranked as
    it did (the retrieval trace) without re-deriving the match. Uses the same per-word
    prefix match and same verb-over-object precedence as the ranking."""
    tier = _aspect_match(claim, _aspect_stems(requested_aspects))
    if tier == _VERB_ASPECT_MATCH:
        return "verb_phrase"
    if tier == _OBJECT_ASPECT_MATCH:
        return "object"
    return None


def _relational_score(
    claim: Claim, forms: frozenset[str], stems: frozenset[str]
) -> tuple[int, int, int, int]:
    """Relational sort key (higher is better), most significant first: entity position
    (the entity *acting* in subject position beats object beats incidental), then how the
    claim's wording matches a requested aspect (verb beats object beats none), then
    predicate role as a fallback among equal aspect matches, then polarity. Aspect match
    dominates role on purpose -- `other`/"knows" is where the answer to "how does God
    think?" lives, and role alone (an extraction bucket) would bury it."""
    if claim.subject in forms:
        position = _SUBJECT_POSITION
    elif claim.object is not None and claim.object in forms:
        position = _OBJECT_POSITION
    else:
        position = _INCIDENTAL
    role, polarity = _role_polarity(claim)
    return (position, _aspect_match(claim, stems), role, polarity)


def rank_relational_claims(
    claims: list[Claim], forms: frozenset[str], requested_aspects: frozenset[str]
) -> list[Claim]:
    """Reorder `claims` for "how does X act/relate/think": the entity acting (subject
    position) on a claim whose wording matches a requested aspect comes first.

    Distinct from characterization on purpose. Characterization prefers an attributive
    `is` and scores `predicate=other` last; but "how does God think?" is answered by
    "God knows His Children" -- an `other`/"knows" claim characterization drops to the
    floor. So this intent ranks by *aspect match on the claim's own wording* above
    predicate role, and role (an extraction category, not a relevance signal) is only a
    tie-break among equal aspect matches. `forms` are the entity's surface forms;
    `requested_aspects` name what the question asks (expanded via `_ASPECT_FAMILIES`). An
    empty aspect set degrades to entity-position + role, never raising. Reorders only;
    the caller's `limit` alone drops."""
    stems = _aspect_stems(requested_aspects)
    return sorted(
        claims,
        key=lambda c: _relational_score(c, forms, stems),
        reverse=True,
    )
