# Increment #7: claims (and resolved entities) in retrieval

Roadmap increment #7 from `semantic-layer-design-and-roadmap.md`. Its predecessor, #6
(`entity-resolution.md`), is complete: the resolver beats the lexical baseline (pair R
0.895 vs 0.789 at P 1.0) and a full-corpus baseline resolution is recorded. #7 is where
extracted claims — and the resolved entities that group their surface forms — first
become **agent-facing tools**, alongside the existing `find_sources`.

## What #7 is

Today the agent has exactly one tool, `find_sources` (`apps/mcp-server`'s `server.py`),
backed by `application/retrieval/find_sources`. Claims and entities exist only as
evaluation artifacts (committed JSONL under `evaluation/`). #7 exposes them:

- **`find_claims`** — a sibling of `find_sources`: query → matching `Claim`s, each
  carrying its `source_id` so the agent can cite the passage the claim rests on.
- **`find_claims_for_entity`** — the resolved-entity view: given an entity (by any of
  its surface forms), return every claim whose subject or object is one of that entity's
  member forms. This is the read-time join #6 specified — the resolution file *is* the
  join table (surface form → entity), materialised here, never a stored field on `Claim`
  or `Entity`.

Both decisions locked before writing this plan: **the backing artifacts are promoted**
into the infrastructure layer (not read from `evaluation/`), and **the entity tool is in
#7 scope now** (not deferred to a later resolution).

## Design decisions carried in

- **Promote the artifacts into `infrastructure/database/data/`.** `find_claims` must not
  read a file under `evaluation/` — that crosses the `evaluation/` ↔ `src/` boundary the
  wrong way (the app depending on the eval harness). Instead the canonical claims run and
  the chosen resolution are **copied into `src/infrastructure/database/data/`** and read
  by `infrastructure/database/claims.py` / `resolutions.py`, exactly as `sources_acim.py`
  reads `data/acim/`. When a real datastore arrives, these become its seed, same as the
  sources placeholder.
- **The claim↔entity link stays a read-time join** (see #6's "Not in this increment").
  `find_claims_for_entity` builds `surface_form → entity_id` from the resolution at read
  time and fans out; no foreign key is written onto either content-addressed artifact, so
  re-resolution never invalidates a claim id.
- **Two named tools, not one with an optional `entity=` branch.** The caller picks the
  variant; the use case stays domain-shaped and each tool's result semantics are
  unambiguous.

## What already exists (so this plan doesn't rebuild it)

- **`find_sources` is the sibling to copy** in every respect: `find_sources(query,
  limit=5) -> list[Source]` in `application/retrieval/`, transport-free and unit-tested
  directly (`tests/test_retrieval.py`); the `server.py` `@mcp.tool()` wrapper does a
  field-by-field `Source -> SourceResult` conversion; `SourceResult` lives in
  `schemas/sources.py`, one module per concept. #7 mirrors this shape exactly.
- **`ClaimLine.to_claim()`** (`evaluation/claims/run_format.py`) already reconstructs a
  `Claim` from a run line, recomputing `claim_id`. The claims reader wraps this — it does
  **not** re-parse JSONL by hand.
- **`EntityLine.to_entity()`** (`evaluation/entities/run_format.py`) reconstructs an
  `Entity` from a resolution line the same way. The resolution reader wraps this.
- **The MCP component-test pattern** (`apps/mcp-server/tests/test_server.py`): boot the
  real `mcp` with `Client(mcp)`, call the tool, reconstruct the DTO from
  `structured_content`, assert on it. New tools follow this.
- **The `data/` placeholder pattern** (`sources_acim.py` + `data/acim/`): a file-backed
  reader with a module docstring saying *why* it's a placeholder for a real store.

## Steps

Each step is its own commit / PR, sequenced enabling-artifact → testable core → wire
boundary → entity join, so a reviewer can pin comments to a single concern.

### 1. Promote the claims artifact + `list_claims()` reader

`src/infrastructure/database/data/claims/`, `src/infrastructure/database/claims.py`

- Copy the canonical corpus claim run
  (`evaluation/claims/runs/20260923T221456Z.jsonl`, the #5 full-corpus run) into
  `src/infrastructure/database/data/claims/` as the seed the app reads. It is committed,
  like `data/acim/`.
- `claims.py`: `list_claims() -> list[Claim]`, reading that file and mapping each
  `type: "claim"` line through `ClaimLine.to_claim()`. Module docstring explains it's a
  placeholder for a real claim store behind this same signature (mirror
  `sources_acim.py`). **Fail loud** if the data file is missing — a missing store is not
  an empty result.
- Tests (`tests/`): `list_claims()` returns real `Claim`s (assert count > 0 and a known
  claim's fields by equality, not truthiness); a missing file raises rather than
  returning `[]`.

**As built (step 1, done).** Promoted the #5 corpus run to
`src/infrastructure/database/data/claims/corpus.jsonl` and added
`infrastructure/database/claims.py` (`list_claims()`), which serves **3984 claims**
(rejected/failed lines skipped), fails loud on a missing file, and parses at import into
a module-level cache like `sources_acim`. **Enabling refactor first (not in the original
step-1 sketch, but required):** the reader must reconstruct `Claim`s without `src/`
depending on `evaluation/`, so `ClaimLine` (+ `to_claim`/`from_claim`) moved from
`evaluation/claims/run_format.py` to `domain/claims/serialization.py`; that file is
deleted and its four evaluation importers (`run`, `corpus_survey`, `near_miss`,
`entities/mentions`) repointed. Serialization of a `Claim` is a domain concern, so this
is its natural home and the app no longer needs the eval harness to read its own data.
(A separate, pre-existing `src/ -> evaluation` leak remains: `resolve_entities.py`
imports `_normalize` from `evaluation.claims.score`. Not addressed here; flagged for a
later move of `_normalize` into a domain/shared home.)

### 2. `find_claims` use case (transport-free)

`src/application/retrieval/find_claims.py`

- `find_claims(query, limit=5) -> list[Claim]`, mirroring `find_sources`: case-insensitive
  substring match over `subject`, `object`, `verb_phrase`, and the evidence text, against
  `infrastructure.database.claims.list_claims()`. Empty query → `[]` **by design** (same
  intentional behavior as `find_sources`, distinct from a missing backing file).
- Tests (`tests/test_find_claims.py`): assert every result actually matches the needle
  (e.g. `all(needle in (c.subject + (c.object or "") + c.verb_phrase).lower() for c in
  results)`), not just `assert results`; preserve the empty-query `[]` contract; assert
  `limit` bounds the count. Construct/return real `Claim`s, no dict literals.

### 3. `find_claims` MCP tool + `ClaimResult` schema

`apps/mcp-server/src/mind_of_christ_mcp/schemas/claims.py`, `server.py`

- `ClaimResult` pydantic model in `schemas/claims.py` (its own module, not a field on
  `SourceResult`): the claim's real fields — `subject`, `predicate`, `object`,
  `verb_phrase`, `polarity`, `mode`, `attribution`, evidence offsets — plus `source_id`
  so the agent can cite the passage. Enums serialise as their `.value` strings; never a
  bare `dict`, never a leaked Python enum member name.
- `server.py`: register `find_claims`, field-by-field `Claim -> ClaimResult`. Tool
  description documents match scope (which fields are searched) and any result ordering.
  Wrapper stays thin — no retrieval logic, `limit` surfaced as-is, no auto-pagination.
- Tests (`apps/mcp-server/tests/test_server.py`): boot the real `mcp`, call `find_claims`,
  reconstruct `ClaimResult`s from `structured_content`, assert on them; no-match → `[]`;
  `limit` respected. Mock only the repository boundary if needed, not the application
  layer.

### 4. Promote a resolution + `find_claims_for_entity`

`src/infrastructure/database/data/resolutions/`,
`src/infrastructure/database/resolutions.py`,
`src/application/retrieval/find_claims_for_entity.py`, schema + tool

- Copy the chosen resolution run into
  `src/infrastructure/database/data/resolutions/` (the recorded baseline
  `20260924T073722Z.jsonl` for now; swap for the LLM full-corpus resolution once it's
  recorded — the reader doesn't change). `resolutions.py`: `load_resolution() ->
  list[Entity]` via `EntityLine.to_entity()`, plus a `surface_form -> entity_id` index
  builder (the same shape as the scorer's `_entity_of`). Fail loud on a missing file.
- `find_claims_for_entity(mention, limit=...) -> list[Claim]`: resolve `mention` to its
  entity via the index, gather the entity's member surface forms, and return
  `list_claims()` whose `subject` or `object` is one of those forms. A `mention` in no
  entity (singleton or absent) returns just its own claims — not an error. This is the
  many-to-many join on the surface string, recomputed from whichever resolution is
  loaded.
- Tool + schema: a `find_claims_for_entity` `@mcp.tool()` returning `ClaimResult`s (reuse
  the step-3 schema — same concept, a claim is a claim). Mirror the step-3 wrapper and
  tests.

## Not in this increment

- **Embeddings / semantic retrieval.** `find_claims` is substring match, mirroring
  `find_sources`'s placeholder. Ranking by relevance is a later change behind the same
  signature (roadmap's deferred embeddings row).
- **A real datastore.** Still committed JSONL seeded into `data/`. Move to a store when
  scale demands it, behind the `list_claims`/`load_resolution` signatures so the
  application layer doesn't shift.
- **Writing claims/entities back to the agent's context as "the Course says".** Retrieval
  returns what the text asserts, with attribution intact; synthesis/interpretation is #8.
- **Auth / identity forwarding.** The MCP server takes no external config and forwards no
  user token today; when it grows a downstream call, apply the same auth discipline as
  its peers then (not retrofitted here for tools that call no external service).

## Open questions to resolve while building (not blockers)

- **Duplicate results across `find_sources` and `find_claims`.** The roadmap flags that
  #7 before a full resolution risks duplicate-feeling results (a passage surfaced by both
  tools). Acceptable for now; the tool descriptions should make each tool's unit clear
  (passages vs. claims) so the agent picks deliberately.
- **Which resolution to promote.** Step 4 starts with the recorded baseline resolution;
  if the LLM full-corpus resolution is recorded during #7, swap the promoted file (reader
  unchanged) and note the swap.

## Results log

_(No scored metric in #7 — it's a tool-surface increment. Record per-PR: tool
registered, claim/entity counts served, and any duplicate-result observations from
manual/agent testing.)_

| PR | Tool | Backing artifact | Notes |
| -- | ---- | ---------------- | ----- |
| _(step 1 promotes the claims run; steps 2–4 fill rows as tools land)_ | | | |
