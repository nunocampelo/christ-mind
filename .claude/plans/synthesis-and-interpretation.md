# Increment #8: deterministic cross-passage claim chains

Roadmap increment #8, **scoped to the deterministic half only**: cross-passage chaining
over stored claims. Its predecessor, #7 (`claims-in-retrieval.md`), is complete — three
live MCP tools (`find_sources`, `find_claims`, `find_claims_for_entity`) over committed
JSONL, no LLM in the retrieval path. The roadmap's #8 row also names situation→concept
mapping; that half is an LLM pass with a different risk profile and is **split out to #9**
(see "Deferred to #9"). #8 establishes one architectural invariant and nothing else:
**stored claims remain the evidence; a transitive conclusion is computed at answer time
and labelled inferred — never stored, never presented as the Course speaking.**

## What #8 is (and the rejected alternative it is not)

The roadmap's Decisions table **rejected** precomputing/storing A→C from A→B + B→C:
"Causal chains aren't reliably transitive … Stored inferred links would grow the graph
while making it less trustworthy. The agent should chain cited claims when answering, not
rely on precomputed links." #8 honours that exactly:

- **No new stored artifact.** Chaining is a pure, deterministic walk computed **per call**
  over the already-stored claims/entities. Nothing is cached or persisted — reintroducing
  a stored chain graph, even as a "cache", is the rejected design.
- **The chain is inferred; its links are stated.** A returned chain is marked
  `inferred: true` at the aggregate level, while every link in it stays an individual,
  `course`-attributed `Claim` with its `source_id`. The agent gets a machine-readable
  split: "these are the Course's stated claims; the connection between them is my
  inference."

## Design decisions carried in (from the #8 design review)

1. **Result cardinality: multiple chains.** A call returns `ChainResult{ inferred: bool,
   subject_mention, predicate, chains: list[ClaimChain] }`, where `ClaimChain{ links:
   list[ClaimResult] }`. `inferred` sits on the aggregate, **never** on a `ClaimResult`
   (that would blur stored claim vs. synthesized relationship). `ClaimResult` is the #7
   schema, reused unchanged.
2. **Same-predicate traversal.** The supplied predicate is walked at **every** hop:
   `chain_claims("fear", causes, 3)` walks `fear --causes--> X --causes--> Y --causes-->
   Z`. Cross-predicate reasoning (`causes → requires → …`) is a different inference rule
   and gets its own future design — not smuggled in here.
3. **BFS, deterministic order.** Breadth-first so shortest chains come first and `max_hops`
   is intuitive; ties broken by a stable key (`claim_id`) so identical corpora always
   produce identical output regardless of storage order — required for equality-based
   tests. `limit` = first N chains.
4. **Extension rule (precise).** A claim may extend a chain **iff** `polarity ==
   affirmed` AND `attribution == course` AND `predicate ==` the requested predicate. A
   `negated` claim is a **non-edge** for traversal (not merely non-terminal): "X does NOT
   cause Y" never becomes a causal step. An `ego`/`others`/`hypothetical` claim likewise
   cannot become an inferential edge — "the ego believes X causes Y" must not turn into
   "X causes Y → …" as though the Course asserted it. Such claims are still retrievable as
   evidence via #7's tools; they just don't extend a synthesized chain.
5. **Per-path cycle guard.** Terminate before revisiting an entity already in the
   *current* path (`A → B → C → A` stops). Guard is path-local, **not** a global visited
   set, because two legitimate chains may converge on one entity (`A → B → D` and
   `A → C → D`) and a global set would wrongly suppress the second.

## What already exists (so this plan doesn't rebuild it)

- **The entity-resolved claim set + join.** `find_claims_for_entity` (#7) already resolves
  a mention to its entity and returns claims across all member surface forms, via
  `infrastructure.database.resolutions.entity_for_mention` + `list_claims`. The chain
  walker reuses this join to hop: a link's object → its entity → the next hop's subject.
- **`ClaimResult` + the thin-wrapper pattern.** #7's `schemas/claims.py` and the
  `_to_claim_result` helper in `server.py` are reused as-is; `chain_claims` returns
  `ClaimResult`s inside chains, no new claim shape.
- **`Predicate` semantics.** `domain/claims/models.py` documents `causes` as one-directional
  cause→effect and keeps `makes`/`creates` distinct — the directed predicates #8 walks.
- **Transport-free retrieval convention.** `find_claims`/`find_claims_for_entity` live in
  `application/retrieval/` and are unit-tested with no MCP transport. `chain_claims` lives
  in `application/synthesis/` and follows the same discipline.

## Steps

Each step its own commit / PR, enabling core → wire boundary.

### 1. `chain_claims` use case (transport-free, no LLM)

`src/application/synthesis/chain_claims.py`

- `chain_claims(subject_mention, predicate, max_hops=3, limit=10) -> list[ClaimChain]`
  (a domain-level chain type of `list[Claim]`, converted to the wire shape in `server.py`
  — not `ClaimResult` here, per the transport boundary).
- BFS from the seed mention's entity, extending only on claims satisfying the step-5
  extension rule, hopping object-entity → next subject-entity via the resolutions index.
  Path-local cycle guard; stable `claim_id` tie-break; bounded by `max_hops` and `limit`.
- Empty/blank mention → `[]` by design (mirrors `find_claims`).
- Tests (`tests/test_chain_claims.py`): on a small hand-built fixture (real `Claim`s +
  a stub resolution), assert **exact** chains by equality (not truthiness); a `negated`
  link and an `ego`-attributed link each fail to extend; a cycle terminates; two chains
  converging on one entity both survive (per-path guard); `max_hops`/`limit` bound the
  output; wrong-predicate claims are not walked. Mock the repository boundary, not the
  application layer.

### 2. `chain_claims` MCP tool + `ChainResult` schema

`apps/mcp-server/src/mind_of_christ_mcp/schemas/chains.py`, `server.py`

- `schemas/chains.py`: `ClaimChain{ links: list[ClaimResult] }` and `ChainResult{
  inferred: bool, subject_mention: str, predicate: str, chains: list[ClaimChain] }`
  (predicate as its `.value` string, like `ClaimResult`'s enums). No bare `dict`;
  `inferred` only at the `ChainResult` level.
- `server.py`: register `chain_claims`, converting each domain chain's `Claim`s through
  the existing `_to_claim_result` helper. Description states plainly that it returns an
  **inferred** path of **stated, Course-attributed** claims, walks a single predicate at
  every hop, orders chains shortest-first, and is bounded by `max_hops`/`limit` (surfaced
  as-is, no auto-expansion of the reachable subgraph).
- Tests (`apps/mcp-server/tests/test_server.py`): boot the real `mcp`, call `chain_claims`,
  reconstruct `ChainResult`, assert `inferred is True`, that each link is a real
  `ClaimResult` with a `source_id`, and that no returned link is negated/non-course.

## Deferred to #9 (situation → concept mapping)

The roadmap's #8 also named situation→concept mapping. It is **#9**, not #8, because it is
the one place an LLM enters the reasoning path and its failure modes are probabilistic —
mixing it with deterministic chaining would make failures hard to localize. #9 shape:

- `map_situation(free_text) -> candidate concept mentions`, a `PromptedSituationMapper`
  over a `Complete` (mirroring the extractor/resolver adapters), own `SYSTEM_PROMPT` +
  `MAP_VERSION`, parser rejecting invented structure. Deliberately **dumb**: "I keep
  getting angry when criticized" → `["anger", "criticism", "judgment", …]`, **never** "this
  is caused by…". The agent then feeds those mentions into #7's retrieval and #8's
  chaining — the LLM interprets only the user's situation, everything downstream stays
  deterministic and cited.
- **Scored against a small situation→concept gold set** (decided): a handful of
  representative situations with expected concepts, its own scorer, matching the "narrow
  passes scored against gold" principle used for extraction (#4) and resolution (#6). It
  need not be large — just enough to prove the mapper reliably produces the expected
  concepts before it's built on.

The resulting progression: **#7 retrieval → #8 deterministic synthesis over retrieved
claims → #9 probabilistic situation→concept mapping → agent composes them.** The LLM only
interprets the situation; retrieval and chaining stay deterministic and cited.

## Not in this increment

- **A stored inference graph / chain cache.** The rejected design; chains are computed per
  call.
- **Cross-predicate chaining** (`causes → requires → …`). A distinct inference rule with
  its own design; #8 walks one predicate.
- **Ranking chains by relevance/strength.** Chains come back shortest-first,
  deterministically; scoring which chain is "best" is later work.
- **Embeddings / a datastore.** Same committed JSONL as #7, read behind the existing
  `list_claims`/resolutions signatures.

## Open questions — resolved while building

- **Seed attribution.** *Resolved: seed may be non-`course`.* The tentative lean was "seed
  also `course`", but the walker allows the hop-0 claim to be `ego`/`hypothetical`/`negated`
  so a query can start from "the ego believes X causes Y" and show where the Course's own
  claims lead from there. Only the *extensions* (hop 1+) require `affirmed` + `course`; the
  aggregate is still labelled `inferred` and every extension link stays stated and
  Course-attributed, so the invariant holds. See the `chain_claims` docstring and the
  `seed=` branch in `_extensions`.
- **`undoes` direction.** *Resolved: no per-predicate special-casing.* `chain_claims` walks
  whatever `Predicate` it is handed subject→object at every hop; it has no hardcoded
  "default predicate set", so `undoes` (or any predicate) chains the same way. Whether a
  given predicate is *worth* chaining is left to the caller, not baked into the walker.

## Results log

_(No scored metric in #8 — deterministic tool surface, like #7. Record per-PR: tool
registered, example chains produced on the real corpus, and any traversal edge cases hit.)_

| PR | Tool | Notes |
| -- | ---- | ----- |
| `e56563e` (steps 1+2) | `chain_claims` use case (`application/synthesis/chain_claims.py`) + MCP tool (`schemas/chains.py`, `server.py`) | Both steps landed in one commit. On the committed corpus (3984 claims, 425 `causes`), `chain_claims("fear", CAUSES, max_hops=2)` yields multi-hop chains, e.g. `fear → emptiness → "screen for the misuse of projection"`. Both open questions resolved (seed may be non-`course`; no per-predicate special-casing — see above). 161 tests pass; pyright clean. |
