from pydantic import BaseModel

from mind_of_christ_mcp.schemas.claims import ClaimResult


class RetrievalTrace(BaseModel):
    """Why a claim surfaced on the `entity_relation` channel: the seed mention, the entity
    it resolved to (None when the mention matched no catalogued entity), the aspects the
    question asked, where an aspect landed in the claim's wording (`"verb_phrase"` /
    `"object"`, or None on entity participation alone), the 0-based rank, and the channel
    name. An explanation of retrieval, not a stored inference."""

    seed_mention: str
    resolved_entity_id: str | None
    requested_aspects: list[str]
    matched_aspect: str | None
    rank: int
    channel: str


class EntityRelationCandidate(BaseModel):
    """One `describe_entity` result: the whole claim (qualifiers intact) plus its trace.
    A distinct envelope from `ClaimResult` because `ClaimResult` cannot carry the trace."""

    claim: ClaimResult
    trace: RetrievalTrace
