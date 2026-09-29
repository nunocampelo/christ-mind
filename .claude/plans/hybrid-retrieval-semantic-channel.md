# Hybrid retrieval: semantic recall as a second channel

## OUTCOME (2026-09-29, after implementation + live eval)

**Shipped:** PR-1..4a — the semantic channel (local `all-MiniLM-L6-v2`), the
claim index + disk cache, `find_claims_semantic`, and `find_claims_hybrid` as
the default behind the MCP `find_claims` tool, with a `RETRIEVAL_MODE=lexical`
kill switch. 398 tests green, zero regressions across the 20 passing cases.

**Did NOT close the target case, and that is the deliverable** — the hypothesis
"class B ⇒ embeddings fix it" was *disproved with evidence*, not merely left
unimproved. Two live runs (`20260929T211321Z` lexical baseline,
`20260929T212129Z` hybrid) are identical: 20/21, `mind-of-god-004b` still fails
`B[all 5 required ids]`.

**Conceptual correction the experiment forces.** The A/B/C classifier establishes
only:

```
A — lexically reachable, but retrieval missed it   (lexical/ranking problem)
B — not lexically reachable by any plausible query  (beyond-lexical)
C — retrieved, but synthesis failed                 (synthesis problem)
```

It does NOT establish `B ⇒ embeddings are sufficient`. The classifier stays
exactly as defined; the experiment adds a **diagnostic sub-split of B**, layered
on top (probe-derived, not part of the stable classifier):

```
B — beyond-lexical
├── B1 semantic-recoverable   embeddings reach the evidence at a usable rank
└── B2 graph/relational       embeddings cannot reach it at any rank
```

**Two INDEPENDENT findings — keep them separate, they are different future
problems:**

1. **Merge suppression (retrieval-design problem, not capability).** Required
   claims 1–2 (`eb3114c3c10e65c7`, and for mpnet `ab816dad26ee5551`) ARE
   semantically reachable (rank 6–12 in isolation), but the round-robin merge +
   `global_limit=12` evicts them once the mapped-concept queries consume slots.
   This is a **rerank/merge-tier** issue and is fixable WITHOUT graphs. Recorded
   as a known limitation of the current hybrid merge — do not read the live 0/5
   as "the semantic channel is weak."

2. **Embedding-unreachable (retrieval-capability problem → graph tier).**
   Required claims 3–5 (`God knows His Children`, `God knows you only in peace`,
   `God DID create the Soul`) are **unreachable at any rank by any query in
   either MiniLM or mpnet**. The link "How does God think?" → "God knows you only
   in peace" is *relational inference* (God's knowing is a property of God's
   mind), not similarity. This is B2 — the graph/relational tier.

**Conclusion.** The progression `lexical → semantic → rerank → graph → synthesis`
now has experimental support, not just architectural intuition. The hybrid layer
is **kept** as the substrate the rerank and graph tiers build on. Decisions taken:

- **PR-4b (situation-routing) NOT wired** — the probe showed it doesn't help this
  case; wiring it now would be speculative. Wire it when a B1 case proves it.
- **Model stays MiniLM** — mpnet's marginally-better isolation numbers vanished
  in the merge, so its extra cost (768-dim, ~12MB, slower encode) buys nothing.
- **Do NOT build the graph yet.** The diagnosis says "graph", but there is not
  yet evidence for a *particular graph architecture*. The next experiment must
  first answer: **what graph operation makes claims 3–5 reachable?** Evidence
  justifies investigating the tier, not committing a design.

See memory `hybrid-retrieval-graph-tier-finding` for the durable takeaway.

---

## Context

The last black-box run (`20260929T201054Z`, 20/21 passing, produced with the
`failure_classification` evaluator in place) reports the compass reading:

```
A: 0    B: 5    C: 0
```

Every remaining failure is class **B** — semantic retrieval required. All five
concentrate in one case, `mind-of-god-004b` ("How does God think? What is the
Mind of God?"), whose required claims (`God's Miracles are His Thoughts`,
`God knows His Children`, `God knows you only in peace`, ...) do not share any
plausible token with the question. The lexical channel has done everything it
can — the reachability probe confirms no tokenization of the question surfaces
any of the required claims in top-12.

This increment adds a **second retrieval channel** — semantic (embeddings) —
alongside the existing lexical one, merges them, and returns the union to the
same MCP tool the orchestrator already uses. The lexical channel remains
authoritative for its wins; the semantic channel bridges the surface-form gap
the classifier's B bucket named.

Two decisions were pinned by the user before this plan:
- **Provider: local `sentence-transformers`** — no proxy round-trip, deterministic
  in tests, zero external-service risk. `cproxy` speaks Anthropic Messages only.
- **Merge point: `find_claims_hybrid` as the new default behind the existing
  `find_claims` MCP tool.** No tool-schema growth. The orchestrator sees the same
  tool it does today.

Success metric for this increment (measured against the same 21-case gold set,
same classifier, same reachability probe):

- `mind-of-god-004b` moves from `fail` → `pass` OR its classifier detail moves
  from B to A/C. Either resolves it or narrows it to a subsequent-fixable class.
- No case that currently passes regresses. Ranker + dedupe wins stay intact.
- Overall pass rate ≥ 20/21.

## Architecture

Three new modules, one dependency pin, one small env var, one MCP-tool import
swap. Everything else stays.

### Module map (new files marked NEW)

```
src/domain/embeddings/                            NEW
  models.py               ClaimEmbedding frozen dataclass; the shape only

src/infrastructure/embeddings/                    NEW
  embedder.py             Embedder protocol + SentenceTransformersEmbedder impl
  claim_index.py          Module-level FAISS-free index: numpy matmul,
                          cosine similarity, top-k. Loaded once at import
                          time from a precomputed .npz cache; rebuilds on
                          corpus_run_id mismatch.

src/application/retrieval/                        MODIFIED
  find_claims_semantic.py NEW  -- mirror of find_claims_batch signature
  hybrid.py               NEW  -- find_claims_hybrid: round-robin merge
  ranking.py              (unchanged)
  find_claims.py          (unchanged; still lexical-only)

evaluation/blackbox/reachability.py               (unchanged this increment;
                                                  probes lexical channel only,
                                                  which is exactly what A/B
                                                  requires -- B measures the
                                                  semantic gap over the lexical
                                                  channel by construction)

apps/mcp-server/src/mind_of_christ_mcp/server.py  MODIFIED
                                                  swap _find_claims_batch import
                                                  for find_claims_hybrid; the
                                                  wrapper signature is unchanged
```

### Data flow (unchanged from caller's perspective)

```
orchestrator seeded batch → MCP find_claims tool → find_claims_hybrid
                                                       │
                            ┌──────────────────────────┼──────────────────────────┐
                            ↓                          ↓                          │
                    find_claims_batch          find_claims_semantic               │
                    (lexical, unchanged)       (new; embeddings)                  │
                            └──────────────────────────┬──────────────────────────┘
                                                       ↓
                                          round-robin merge, dedupe by claim_id
                                                       ↓
                                          rank_query_relevance final tie-break
                                                       ↓
                                                  list[Claim]
```

### Sequence of the increment (5 PRs, each independently reviewable)

**PR-1 · Embedder protocol + local model + tests.** Pure infrastructure.
No behavior change to any caller. Adds `sentence-transformers` pin. Adds
`ClaimEmbedding` dataclass. Adds `SentenceTransformersEmbedder` and a
`Embedder` protocol so tests can inject a fake. **No index yet.**

**PR-2 · Claim index build + on-disk cache.** Import-time index over
`list_claims()` — 4,007 vectors — cached at
`src/infrastructure/database/data/claims/embeddings_<model>_<corpus_run_id>.npz`.
Cache invalidates on `corpus_run_id` change (already captured in the run header).
`top_k(query_vec, k)` returns `list[tuple[claim_id, score]]`. Pure infra, no
callers yet.

**PR-3 · `find_claims_semantic` — a lexical-shaped mirror.** Same signature as
`find_claims_batch` — `(queries, limit_per_query, global_limit) -> list[Claim]`.
Embeds each query, calls index `top_k`, round-robin interleaves and dedupes
mirroring `find_claims_batch`. Unit-testable in isolation with a stub Embedder
that returns deterministic vectors.

**PR-4 · `find_claims_hybrid` + MCP tool swap.** New `hybrid.py` runs the two
channels, merges. Change one import in `apps/mcp-server/src/mind_of_christ_mcp/
server.py` from `find_claims_batch as _find_claims_batch` to `find_claims_hybrid
as _find_claims_hybrid`. The tool wrapper's signature is unchanged; the LLM sees
no schema difference. Run pyright + full test suite; expect all green.

**PR-5 · Live eval + report.** Re-run black-box against the same 21-case gold
set. Verify `mind-of-god-004b` outcome. Commit the new run artifact under
`evaluation/blackbox/runs/`. Update `evaluation/blackbox/README.md`'s
"Retrieval channels" section (add one paragraph naming the hybrid default and
where to disable it via env var for A/B eval comparisons — see below).

## Design details (the parts that would otherwise be re-derived)

### Embedder protocol

```python
class Embedder(Protocol):
    dim: int
    model_id: str  # for cache key
    def embed(self, texts: list[str]) -> list[list[float]]: ...
```

DI at the constructor, following the `Complete` / `ChatStream` seam already
established. Real impl wraps `sentence_transformers.SentenceTransformer` with
`normalize_embeddings=True` (so cosine sim collapses to a dot product — matmul
in the index).

### Model choice: `all-MiniLM-L6-v2`

384-dim, ~90MB on disk, ~100ms cold-load, ~15ms/query batch on CPU. Small enough
to check into the environment without a git-lfs decision; fast enough that a
21-case eval run doesn't materially slow down. If it under-performs on the ACIM
domain specifically, PR-6 (not in this plan) is to swap the model — the
`model_id` cache key means the swap is invalidation-safe.

**What the embedder is fed per claim** — a decision that materially shapes recall:

```python
f"{claim.subject} {claim.verb_phrase} {claim.object or ''} :: {evidence_text}"
```

Subject + verb + object gives the triple's structure; the sliced evidence
sentence gives it context. The `::` separator is a soft cue. Verified informally
against `mind-of-god-004b`'s claims — the embedding of "God's Miracles are as
total as His Thoughts because they ARE His Thoughts" against the query "How does
God think?" scores comfortably above the mean.

### Index shape

```
_MATRIX: np.ndarray of shape (N, dim), float32, unit-normed
_CLAIM_IDS: tuple[str, ...] parallel to matrix rows
```

`top_k(query_vec, k)`:
```python
scores = _MATRIX @ query_vec
top = np.argpartition(-scores, k)[:k]
top = top[np.argsort(-scores[top])]
return [(_CLAIM_IDS[i], float(scores[i])) for i in top]
```

Numpy only — no FAISS pin. 4,007 × 384 × 4 bytes = **~6MB** matrix. Trivial
memory, no GPU, no index-server. If corpus grows past ~100k claims this stops
being enough and we swap to FAISS; that day is not today.

### On-disk cache

At import, `index.py` checks for
`data/claims/embeddings_<model_id>_<corpus_run_id>.npz`. Hit → load. Miss →
build (embed all claims via the injected Embedder), save, load. `corpus_run_id`
comes from the corpus jsonl header (already read by `evaluation/blackbox/run.py:
_corpus_run_id`). Cache files are committable — reviewers see exactly what
vectors are being scored against.

**Cache key rationale**: model change (better recall) or corpus change (new
claims) both invalidate. Neither happens often; when they do, invalidation is
loud (a rebuild takes seconds) rather than silent (stale vectors).

### `find_claims_hybrid` merge rule

```python
def find_claims_hybrid(
    queries: list[str], limit_per_query: int = 5, global_limit: int = 12
) -> list[Claim]:
    lex = find_claims_batch(queries, limit_per_query, global_limit=global_limit * 2)
    sem = find_claims_semantic(queries, limit_per_query, global_limit=global_limit * 2)
    # Round-robin interleave: lex[0], sem[0], lex[1], sem[1], ... dedupe by claim_id,
    # cap at global_limit. Lexical wins ties (first appearance in interleave).
    merged: list[Claim] = []
    seen: set[str] = set()
    for pair in zip_longest(lex, sem):
        for claim in pair:
            if claim is None or claim.claim_id in seen:
                continue
            seen.add(claim.claim_id)
            merged.append(claim)
            if len(merged) >= global_limit:
                return merged
    return merged
```

Both channels retrieve `2 * global_limit` internally so the interleave has
material to work with after dedupe. **Lexical wins interleave ties** — a claim
that both channels rank first shows up in the merged output at position 0 with
lexical's evidence, preserving current behavior on cases the lexical channel
already handles. Semantic wins the *next* slot.

**Rank preservation via ordering only** — no cross-channel score comparison. Two
reasons: cosine similarity and lexical position-score are in different units,
normalizing them is a whole new tuning surface; and the interleave-with-lex-first
rule gives us the "hybrid = strict superset" property that makes the classifier
readable (a case that used to be A passing lexically stays lexical-driven).

### Env-var kill switch

`RETRIEVAL_MODE` env var, values `hybrid` (default) / `lexical`. Read at the top
of `find_claims_hybrid` (per the load_env pattern). One-line branch:

```python
if os.getenv("RETRIEVAL_MODE", "hybrid") == "lexical":
    return find_claims_batch(queries, limit_per_query, global_limit)
```

Two purposes:
- **A/B eval comparisons**: re-run gold with `RETRIEVAL_MODE=lexical` to
  reproduce the current-run baseline and confirm hybrid didn't regress anything.
- **Production revert**: if hybrid misbehaves at real user load, set the env var
  in the a2a-server's `.env` — no code change, no redeploy.

Documented in `.env.example` alongside `ANTHROPIC_BASE_URL`.

## Testing strategy

### Offline unit tests (no live proxy, no model download)

**Embedder** — a `StubEmbedder` in a test file returns deterministic vectors
via a hash-to-vector function. Tests: `Embedder` protocol conformance, dim/id
attributes, batch shape stability.

**Index** — build with the `StubEmbedder` over a 5-claim toy tuple; assert
top-k returns expected orderings; assert cache round-trip (write → new import →
same output).

**`find_claims_semantic`** — inject the toy index; assert same shape and dedupe
contract as `find_claims_batch`, exercised with the same fixtures.

**`find_claims_hybrid`** — inject stubs for both channels; assert the
round-robin interleave, lexical-wins-ties, and global_limit cut. Assert
`RETRIEVAL_MODE=lexical` collapses to pure lexical.

### Deterministic reachability probe

`evaluation/blackbox/reachability.py` **does not change this increment**. The
A/B distinction *is* the lexical-channel probe by construction — B means
"lexical cannot reach this". If we made reachability hybrid-aware, we'd lose
the ability to say "the semantic channel closed the B gap". Keep it lexical-only
so PR-5's re-run report reads cleanly.

### Live black-box eval (PR-5)

Two runs, back-to-back:

```
RETRIEVAL_MODE=lexical  .venv/bin/python -m evaluation.blackbox.run --live --record
# expected: 20/21, mind-of-god-004b B[...] (baseline reproduction)

.venv/bin/python -m evaluation.blackbox.run --live --record
# expected: 21/21 OR mind-of-god-004b advances (A/C, or specific ids resolved)
```

Both artifacts committed. The diff between them is the increment's return.

## What this does not do

- **No re-embedding of Sources.** Only Claims are indexed. If a case's required
  evidence lives at the Source level (`must_include_source_ids`), semantic
  retrieval doesn't touch it — Source retrieval stays lexical. No current gold
  case needs Source-level semantic retrieval per the last classifier run.
- **No cross-encoder rerank.** After the round-robin merge, the existing
  `rank_query_relevance` is the final ordering — no learned reranker. If the
  hybrid layer leaves residual B (semantically-retrieved but poorly-ordered),
  the next increment is the cross-encoder; not now.
- **No knowledge-graph traversal.** Per the earlier architectural discussion
  (from user's response this session), that's the layer *after* hybrid, gated
  on residual failures that hybrid leaves.
- **No change to `find_sources` / `find_claims_for_entity` / `chain_claims`.**
  Only `find_claims` gets the hybrid channel. Extending later is a mechanical
  copy of the same pattern; leaving them alone keeps this PR shape small.

## Verification checklist

At the end of PR-4:

1. `.venv/bin/pyright` — clean.
2. `.venv/bin/python -m pytest tests apps/agent/tests apps/a2a-server/tests -q`
   — all green, including the new embedder/index/semantic/hybrid tests.
3. Run the existing `.venv/bin/python -m pytest tests/test_blackbox_*.py -q` —
   confirm reachability and classifier tests unchanged.
4. Bring up the a2a-server locally, ask `"How does God think?"` in the chat
   UI (or via `apps/mcp-server/scripts/call_tool.py find_claims`), confirm the
   returned claims now include one of `mind-of-god-004b`'s required ids.

At the end of PR-5:

5. Run 1: `RETRIEVAL_MODE=lexical --live --record`. Expect the 20/21 baseline,
   `mind-of-god-004b` fail B[...].
6. Run 2: default `--live --record`. Expect improvement on
   `mind-of-god-004b`. Both artifacts under `evaluation/blackbox/runs/`.
7. Diff the two artifacts to name the deltas: pass-rate change, per-case
   classification changes, any newly-failing case.
8. Update `evaluation/blackbox/README.md` with the new hybrid-default paragraph
   and the `RETRIEVAL_MODE` kill switch.

## Files to touch (representative, not exhaustive)

**New:**
- `src/domain/embeddings/models.py`
- `src/infrastructure/embeddings/embedder.py`
- `src/infrastructure/embeddings/index.py`
- `src/application/retrieval/find_claims_semantic.py`
- `src/application/retrieval/hybrid.py`
- `tests/test_embedder.py`, `tests/test_embedding_index.py`,
  `tests/test_find_claims_semantic.py`, `tests/test_find_claims_hybrid.py`
- `src/infrastructure/database/data/claims/embeddings_all-MiniLM-L6-v2_<corpus_run_id>.npz`
  (cache; committed for review-ability)

**Modified:**
- `pyproject.toml` — pin `sentence-transformers==<latest>`, `numpy==<latest>`
- `apps/mcp-server/src/mind_of_christ_mcp/server.py` — swap import from
  `_find_claims_batch` to `find_claims_hybrid`
- `.env.example` — document `RETRIEVAL_MODE` optional override
- `evaluation/blackbox/README.md` — one paragraph on hybrid + kill switch

**Unchanged (called out because a reviewer might expect them to change):**
- `apps/agent/src/mind_of_christ_agent/domain/orchestrator.py` — the seeded
  batch calls the MCP tool by name; the tool now uses hybrid under the same
  wrapper.
- `evaluation/blackbox/reachability.py` — deliberately lexical-only; see
  Testing above.
- `evaluation/blackbox/classify.py` — A/B/C semantics unchanged; the meaning
  of B refines from "no channel reaches" to "the lexical channel does not
  reach", which is exactly what it always meant.
