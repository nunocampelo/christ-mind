"""Claim retrieval, kept independent of any transport layer so it can be unit
tested directly, mirroring `find_sources`.
"""

from domain.claims.models import Claim
from infrastructure.database.claims import list_claims


def find_claims(query: str, limit: int = 5) -> list[Claim]:
    """Return claims whose surface forms match the query.

    Case-insensitive substring match over subject, object, and verb_phrase -- the
    claim's own words. (A `Claim` holds evidence as offsets into `Source.text`, not
    the quote itself, so evidence text isn't searched here.) Placeholder for a real
    retrieval implementation behind the same signature.
    """
    if not query.strip():
        return []

    needle = query.strip().lower()
    matches = [
        claim
        for claim in list_claims()
        if needle in claim.subject.lower()
        or (claim.object is not None and needle in claim.object.lower())
        or needle in claim.verb_phrase.lower()
    ]
    return matches[:limit]
