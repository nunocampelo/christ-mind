"""Semantic claim retrieval, mirroring `find_claims_batch`'s signature so a
caller can swap the two -- or run them side by side under `find_claims_hybrid`
-- without any shape adaptation. Every claim from the semantic index is a real
domain `Claim` (loaded from the same corpus tuple lexical retrieval uses); the
similarity scores stay inside this module because callers downstream only order
by the shared query-relevance ranker, not raw cosine sim (which is in a
different unit from lexical position).
"""

from infrastructure.database.claims import list_claims
from infrastructure.embeddings.embedder import Embedder, SentenceTransformersEmbedder
from infrastructure.embeddings.claim_index import ClaimIndex, get_claim_index
from domain.claims.models import Claim


def _find_claims_semantic_single(
    query: str, index: ClaimIndex, embedder: Embedder, limit: int
) -> list[Claim]:
    """Top-`limit` claims for one query, in similarity order. Whitespace-only
    queries return [] to mirror lexical `find_claims`'s treatment of a bare
    query as a no-op."""
    if not query.strip():
        return []
    query_vec = embedder.embed([query])[0]
    scored = index.top_k(query_vec, k=limit)
    by_id = {c.claim_id: c for c in list_claims()}
    # An index built against a stale corpus could reference a claim_id no longer
    # in list_claims(); skip rather than raise so a running server degrades
    # gracefully -- the cache invalidation logic in index.load_or_build should
    # keep this to a cold-cache edge case.
    return [by_id[cid] for cid, _score in scored if cid in by_id]


def find_claims_semantic(
    queries: list[str],
    limit_per_query: int = 5,
    global_limit: int = 12,
    index: ClaimIndex | None = None,
    embedder: Embedder | None = None,
) -> list[Claim]:
    """Semantic counterpart of `find_claims_batch`. Same round-robin interleave
    (so one productive query cannot consume the whole `global_limit`), same
    dedupe by claim_id keeping the first appearance in round-robin order.

    `index` and `embedder` are DI hooks -- production callers pass nothing and
    the module-level singleton (built lazily on first call, cached to disk)
    resolves. Tests pass their own so torch never loads and the corpus index
    is not touched.
    """
    active_index = index if index is not None else get_claim_index()
    active_embedder = embedder if embedder is not None else SentenceTransformersEmbedder()
    per_query = [
        _find_claims_semantic_single(q, active_index, active_embedder, limit_per_query)
        for q in queries
        if q.strip()
    ]

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
