"""Aspect-aware one-hop entity retrieval, for "how does God think?"-style questions.

Same read-time entity join as `find_claims_for_entity` (mention -> entity -> claims whose
subject or object is one of its forms), but ranked for a different intent: the relations
the question asks about, not an attributive description. The whole point is that the full
candidate set is gathered *before* the limit, so a relational claim the characterization
ranking would bury (`predicate=other`, e.g. "God knows His Children") is a candidate and
can rank up on an aspect match. Kept transport-free so it is unit-testable directly.

Each result is an `EntityRelation`: the whole `Claim` (qualifiers intact -- "you only in
peace" is never flattened to a bare edge) plus a retrieval *trace* explaining why it
surfaced. The trace is an explanation of retrieval, never a stored inference (honors the
roadmap's no-stored-inference rule); the tool wrapper converts it to the wire envelope.
"""

from dataclasses import dataclass

from application.retrieval.ranking import explain_aspect_match, rank_relational_claims
from domain.claims.models import Claim
from infrastructure.database.claims import list_claims
from infrastructure.database.resolutions import entity_for_mention

CHANNEL = "entity_relation"


@dataclass(frozen=True)
class EntityRelation:
    """One claim retrieved by the `entity_relation` channel, with the trace that explains
    its selection. `resolved_entity_id` is None when the mention resolved to no catalogued
    entity (it fell back to its own surface form). `matched_aspect` is where a requested
    aspect landed in the claim's wording (`"verb_phrase"`/`"object"`), or None if the
    claim surfaced on entity participation alone. `rank` is 0-based within this result."""

    claim: Claim
    seed_mention: str
    resolved_entity_id: str | None
    requested_aspects: tuple[str, ...]
    matched_aspect: str | None
    rank: int


def describe_entity(
    mention: str, requested_aspects: frozenset[str], limit: int = 20
) -> list[EntityRelation]:
    """Return claims about the entity `mention` belongs to, ranked for how it acts on the
    `requested_aspects` (e.g. `{"thinking"}` for "how does God think?"), each wrapped with
    its retrieval trace.

    A mention the resolver never merged resolves to just itself, like
    `find_claims_for_entity`. Empty mention -> [] by design. `limit` alone governs
    absence; ranking only reorders.
    """
    if not mention.strip():
        return []

    entity = entity_for_mention(mention)
    forms = frozenset(entity.mentions if entity is not None else {mention})
    matches = [
        claim
        for claim in list_claims()
        if claim.subject in forms or (claim.object is not None and claim.object in forms)
    ]
    ranked = rank_relational_claims(matches, forms, requested_aspects)[:limit]
    aspects = tuple(sorted(requested_aspects))
    entity_id = entity.entity_id if entity is not None else None
    return [
        EntityRelation(
            claim=claim,
            seed_mention=mention,
            resolved_entity_id=entity_id,
            requested_aspects=aspects,
            matched_aspect=explain_aspect_match(claim, requested_aspects),
            rank=rank,
        )
        for rank, claim in enumerate(ranked)
    ]
