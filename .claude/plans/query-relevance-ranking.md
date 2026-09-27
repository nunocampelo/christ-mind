# Increment #11 — query-relevance ranking for `find_claims`

## Context

The black-box eval (#10) surfaced one genuine retrieval failure that persisted across three
runs: `right-mindedness-009` — the agent never cites `t2-2-13` ("right-mindedness IS
healing"), the Course's actual definition, so its answer stays vague and gating-fails on
`required_source_present`. Diagnosed precisely:

- The defining claim **is** matched by `find_claims("right-mindedness")` — not a
  retrieval-absence problem (that would be #12 embeddings).
- It's dropped by the **`limit_per_query=5`** cut because `find_claims` returned matches in
  **corpus order**, and the definition sits at corpus position 12 of 29 matches — so it
  never survives the per-query slice; `global_limit`/round-robin never see it.
- Root cause: no relevance ordering. A definitional subject-position claim ("X IS Y") lost
  to incidental mentions ("fear intruding on your X…") purely by file position.

**Fix = ranking, not bigger limits.** Ranking puts the definition at rank 0 so it survives a
*small* limit — recall without flooding the agent. Limits unchanged.

Scope: only the query-relevance ranker. Question-mode/intent selection has no scaffolding
and stays future; `find_claims` gets one relevance function per `ranking.py`'s "one strategy
per intent" rule.

## What was built

### `src/application/retrieval/ranking.py`
- Extracted `_role_polarity(claim) -> tuple[int, int]` (the role+polarity sub-key), shared by
  both rankers — mechanically the old `_score` lines, characterization behavior unchanged.
- Added `_VERB_PHRASE_POSITION = 10` (four-tier ladder: subject 100 > object 50 >
  verb_phrase 10 > incidental 0).
- Added `rank_query_relevance(claims, needle)` with `_query_position` (subject/object/
  verb_phrase/incidental by substring, subject checked first, `object is None` guarded),
  sort key `(_query_position, *_role_polarity)`, stable `sorted(reverse=True)`. Reorders
  only; caller's `limit` alone drops.

### `src/application/retrieval/find_claims.py`
- One line: `return rank_query_relevance(matches, needle)[:limit]` (was `matches[:limit]`).
  Ranks within each query before the per-query slice, so the best match survives
  `limit_per_query` and thus round-robin + `global_limit`. `find_claims_batch`, the MCP
  wrapper, orchestrator, and `map_situation` untouched.

### Tests
- `tests/test_ranking.py` — `rank_query_relevance` block: four-tier order, subject-beats-both,
  role tie-break, negated-below-affirmed, stable order, and a **permutation invariant**
  (`set(ranked)==set(input)`). Existing characterization tests pass unchanged.
- `tests/test_find_claims.py` — **limit-boundary regression** (definitional match placed past
  `limit` in a monkeypatched corpus, returned at `limit=1`) + a **real-corpus** assertion
  that `t2-2-13` surfaces in `find_claims("right-mindedness", limit=5)`.

## Verified

- Full suite green (226), pyright clean.
- Mechanism: `t2-2-13` now in `find_claims_batch(~10 concepts, global_limit=12)` — absent
  before, present after, **no limit raised**.
- Pending: black-box `--live` run to confirm `right-mindedness-009` moves toward PASS across
  a couple of runs (per #10 noise-floor finding), no regression in strong cases.

## Out of scope

Question-mode/intent classification; embeddings (#12, only if the eval later shows *absence*
misses); limit changes; `find_sources` ranking.
