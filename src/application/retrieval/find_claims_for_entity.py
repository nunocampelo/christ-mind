"""Retrieves every claim about a resolved entity, given any of its surface forms.

This is the read-time join entity resolution was built for (see the increment #6
plan): the resolution maps surface form -> entity, and a claim names its subject and
object as surface forms, so "all claims about the ego as one entity" is entity ->
member forms -> claims whose subject or object is one of those forms. The link is
computed here, never stored on `Claim` or `Entity`, so re-resolving never invalidates a
claim id. Kept transport-free so it can be unit tested directly, like `find_claims`.
"""

from domain.claims.models import Claim
from infrastructure.database.claims import list_claims
from infrastructure.database.resolutions import entity_for_mention


def find_claims_for_entity(mention: str, limit: int = 20) -> list[Claim]:
    """Return claims whose subject or object names the entity `mention` belongs to.

    A mention the resolution never merged (a singleton, or a form the resolver never
    saw) resolves to just itself, so its own claims still come back -- not an error.
    Empty query -> [] by design, like `find_claims`.
    """
    if not mention.strip():
        return []

    entity = entity_for_mention(mention)
    forms = entity.mentions if entity is not None else {mention}
    matches = [
        claim
        for claim in list_claims()
        if claim.subject in forms or (claim.object is not None and claim.object in forms)
    ]
    return matches[:limit]
