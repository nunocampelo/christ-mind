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


def find_claims_batch(
    queries: list[str],
    limit_per_query: int = 5,
    global_limit: int = 12,
) -> list[Claim]:
    """Run `find_claims` for each query, then merge into one budget-bounded set.

    Balanced allocation: the per-query results are interleaved round-robin rather than
    concatenated, so one productive query can't consume the whole `global_limit` while
    others also match. Deduped by `claim_id`, first occurrence (in round-robin order)
    winning. Whitespace-only queries are skipped; an empty list returns `[]`.
    """
    per_query = [find_claims(q, limit=limit_per_query) for q in queries if q.strip()]

    merged: list[Claim] = []
    seen: set[str] = set()
    for rank in range(max((len(m) for m in per_query), default=0)):
        for matches in per_query:
            if rank >= len(matches):
                continue
            claim = matches[rank]
            if claim.claim_id in seen:
                continue
            seen.add(claim.claim_id)
            merged.append(claim)
            if len(merged) >= global_limit:
                return merged
    return merged
