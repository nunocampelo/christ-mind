"""Hybrid retrieval: the lexical and semantic channels merged into a single
`list[Claim]` result, deduped by claim_id. Round-robin interleave with lexical
wins ties, so a case the lexical channel already handles stays lexical-driven
(the classifier's A cases don't drift into B on hybrid). The semantic channel
adds material only where lexical missed.

Both channels retrieve `2 * global_limit` internally so the interleave has room
after dedupe; the final cap is `global_limit`. No cross-channel score comparison
-- cosine similarity and lexical position are in different units; ordering is
the only signal that carries between them.

The one env-var lever: `RETRIEVAL_MODE=lexical` collapses to pure lexical. Its
purpose is A/B eval comparisons (reproduce the baseline against the same 21-case
gold under the hybrid code path) and a one-line production revert if the hybrid
channel misbehaves at load.

Architectural invariant (see PR-4a design discussion): `find_claims_hybrid` is
the application-layer entry point. The MCP `find_claims` tool adapter calls it;
the orchestrator (which owns orchestration context like the raw user situation)
may also call it directly for the seeded batch. The MCP tool schema stays
narrow -- the raw situation is orchestration context, not part of the
LLM-facing contract. PR-4b threads a `situation: str | None` kwarg through this
function for the orchestrator's seeded-batch path only.
"""

import os
from itertools import zip_longest

from application.retrieval.find_claims import find_claims_batch
from application.retrieval.find_claims_semantic import find_claims_semantic
from domain.claims.models import Claim


def find_claims_hybrid(
    queries: list[str],
    limit_per_query: int = 5,
    global_limit: int = 12,
) -> list[Claim]:
    """The default retrieval path for claims. Merges lexical (substring match on
    subject/object/verb_phrase, ranker-ordered) with semantic (embedding cosine
    similarity over the claim triple + evidence)."""
    if os.getenv("RETRIEVAL_MODE", "hybrid") == "lexical":
        return find_claims_batch(queries, limit_per_query, global_limit)

    # Widen each channel's global cap so the merge has material to interleave
    # after dedupe. `limit_per_query` is untouched: within one query, both
    # channels stay honest to their per-query budget.
    widened = global_limit * 2
    lex = find_claims_batch(queries, limit_per_query, widened)
    sem = find_claims_semantic(queries, limit_per_query, widened)

    merged: list[Claim] = []
    seen: set[str] = set()
    for lex_claim, sem_claim in zip_longest(lex, sem):
        for claim in (lex_claim, sem_claim):
            if claim is None or claim.claim_id in seen:
                continue
            seen.add(claim.claim_id)
            merged.append(claim)
            if len(merged) >= global_limit:
                return merged
    return merged
