# Graph tier, step 1: `entity_relation` — aspect-aware one-hop retrieval (a diagnostic experiment)

## Context

`mind-of-god-004b` ("How does God think? What is the Mind of God?") is the last standing
black-box eval failure. Prior work showed the *tested embedding configurations* (MiniLM
1/5, mpnet 0/5, `text-embedding-3-large` 3072d 0/5) did not reach the required claims —
**not** that every semantic approach is exhausted, nor that a graph will fix it. The
working hypothesis this increment *tests* (does not assume):

> Relevant evidence is organized around the **entities and relations the question
> implies**, not around wording similar to the question.

Guiding rule for anything built here:

> **Query expansion may propose WHERE to look; only source-backed assertions may
> establish WHAT the text says.**

So "how does God think?" may explore claims about *knowing / thoughts / knowledge*
without ever declaring thinking ≡ knowing. Claims and source passages stay the authority;
this adds a retrieval channel, it does not add stored truth (honors the roadmap's
no-stored-inference rule). See `[[graph-tier-design-principles]]`.

### Ground truth (verified live against the corpus, 3984 claims)

Gate is `must_include_any_claim_ids` — citing **any one** of the five passes:

| claim_id | subject | verb | object | evidence span |
| --- | --- | --- | --- | --- |
| `f99fd11e` | **God** | knows | His Children | "God knows His Children with perfect certainty" |
| `53c77a24` | **God** | knows | you only in peace | "God knows you only in peace" |
| `ab816dad` | **God** | DID create | Soul in His Own Thought | "God DID create the Soul in His Own Thought…" |
| `efdccd0a` | God's Miracles | are as total as | His Thoughts | "God's Miracles are as total as His Thoughts…" |
| `eb3114c3` | God's Miracles | ARE | His Thoughts | "because they ARE His Thoughts" |

- **3 of 5 are God-subject claims** (`God` entity = `{GOD, God}`; 84 God-subject claims).
  They are **buried, not absent**: the two "knows" claims rank ~54/56 and the "creates"
  claim ~21 under `find_claims_for_entity("God")`, because `rank_characterization_claims`
  scores `predicate=other` (where "knows"/"thinks" live) at **0** and the default
  `limit=20` then cuts them. This is the concrete flooding bug: *generic God claims bury
  the specific relations before the limit.*
- **2 of 5** have subject `God's Miracles` — a **distinct** entity, correctly so. Their
  paragraph `t3-6-9` also contains "Each Soul knows God completely… the miraculous power
  of the Soul", so the paragraph itself connects God ↔ Soul ↔ Thoughts.
- **Doctrinal entities are already distinct** (`God`, `God's Miracles`, `His Thoughts`,
  `the Soul` are separate) — the gap is that nothing *connects* them at query time, not
  that they're mis-split. **Do not merge them to fix this** (that would encode theology
  into retrieval). This reverses the earlier "richer resolution" idea.
- **Trigger gap:** the orchestrator only auto-seeds `find_claims` (lexical+semantic) with
  mapped concepts; nothing calls the entity join for "God". Verified:
  `concept_query_terms(q)` and `meta_query_terms(q)` both return `[]`. So even perfect
  entity retrieval is inert until "God" reaches it.

### Corpus pin (so the A/B/C comparison uses one dataset)

The corpus file has **4007 records = 3984 `claim` + 19 `failed` + 3 `rejected` + 1
`header`** (verified). The earlier "4,007" counted file lines; `list_claims()` counts
parseable claims = 3984. **Same data, no drift.** There is no `corpus_run_id` in the
header line today (it's just `{"type":"claim"}` per record) — pin the comparison by the
corpus file's git blob hash and the fixture hash, and add a real `corpus_run_id` to the
header as a small precursor if the experiment needs versioned index caches.

## Approach: `entity_relation` — aspect-aware one-hop retrieval as a measured experiment

Named **`entity_relation`**, not "graph" — a one-hop entity lookup shouldn't imply
traversal. Build the minimum to run it and measure against baseline A **at the same
selection budget**, with two-hop (C) designed-for but disabled. One repaired case shows
feasibility, not improvement — carry relational probes + negative controls.

### Three connection types, kept separate (never collapsed)

1. **Spelling/grammatical variant** → may resolve to one entity when unambiguous (how
   `entity_for_mention` already works).
2. **Related vocabulary** (thinking→thoughts, knowing→knowledge) → **query expansion /
   aspect signal only**, proposes where to look and *weights* ranking; asserts no
   equivalence.
3. **Course-asserted relation** → must be backed by a claim + its passage.

Distinguish an **entity occurrence** (entity appears in a claim) from a **supported
relation** (the claim asserts a link). Never flatten to an entity→entity edge:
`53c77a24`'s object stays `"you only in peace"`. `describe_entity` returns whole `Claim`s,
so qualifiers survive. **Always preserve the original `predicate`/`verb_phrase`; retrieval
mappings (aspect → predicate/verb families) live separately, never mutate the claim.**

### Aspect-aware ranking (fixes "OTHER is a category, not a signal")

`OTHER` is an *extraction bucket*, not relevance — promoting all `OTHER` above `is` would
also promote miscellaneous unrelated predicates, and would rank "how does God think?" and
"how does God create?" identically. So ranking must receive the requested aspects:

- **`src/application/retrieval/ranking.py`** — add
  `rank_relational_claims(claims, entity_forms, requested_aspects)` beside
  `rank_characterization_claims` (per-intent strategy; don't mutate the existing one).
  Sort key, most significant first:
  1. **entity participation** — subject-position (the entity *acts*) > object > incidental
     (same position tiers as today);
  2. **aspect match** — the claim's original `verb_phrase`/`predicate`/`object` matches a
     requested aspect or its mapped family (e.g. aspect *thinking* weights `verb_phrase`
     "knows"/"thinks" and objects containing "Thought"/"knowledge"). A small, explicit
     aspect→family map, provenance attached, not a mutation of the claim;
  3. **predicate category** — only as a *fallback* tie-break among equal aspect matches
     (directed/creative over bare attribute), not the primary lever;
  4. polarity (affirmed > negated), then `claim_id` for deterministic order.
  Reorders only, never drops.

- **`src/application/retrieval/describe_entity.py`** (new; mirror
  `find_claims_for_entity.py`) — `describe_entity(mention, requested_aspects, limit=20) ->
  list[Claim]`. Gather **all** claims incident to the resolved entity (the full candidate
  set — this is the real fix: every relevant God assertion is a candidate *before* the
  limit), rank with `rank_relational_claims`, then apply `limit`. **Default limit stays
  20** — the relational win must not be confounded by a bigger budget (see the A/B/budget
  control below). Transport-free.

### Aspect + target extraction (general, not proper-noun-only)

A proper-noun detector fails for "what about *the ego* / *forgiveness*?". Instead extract
the **grammatical target** from supported question forms ("how does X …", "what is the
Mind of X", "how does X <verb>") and resolve it against the entity catalog; the verb/frame
yields the requested aspects (*think* → thinking/knowing; *create* → creating). A detector
sibling to `apps/agent/.../domain/concept_question.py`, pure syntactic (no corpus
reach-in). Aspects *propose where to look and weight ranking*; they never assert
equivalence.

### Trigger — narrow, budgeted, and behind the tool boundary

Two corrections to the earlier draft:

- **Narrow:** trigger `entity_relation` only from **entities explicitly named in a
  relational question** (the extracted grammatical target), *not* per-mapped-concept — ten
  mapped concepts must not fire ten 40-claim fetches. Dedupe resolved entity IDs; enforce a
  **total channel candidate budget**. Mapped-concept entity expansion is a *separate later
  experiment*.
- **Boundary:** the orchestrator is domain-layer and reaches the corpus **only through the
  MCP `ToolClient`** — it must not import `entity_for_mention`/`list_claims` directly
  (verified: today it imports only `map_situation` (injected protocol) + a type). So entity
  resolution for the trigger happens **through the new `describe_entity` MCP tool / the
  application layer**, never a domain→infrastructure import.

### Result envelope + retrieval trace (ClaimResult can't carry it)

MCP's `ClaimResult` is unchanged and **cannot** carry the explanation — so introduce a
typed envelope. New schema `apps/mcp-server/.../schemas/entity_relation.py`:
`EntityRelationCandidate(claim: ClaimResult, trace: RetrievalTrace)` with
`RetrievalTrace(seed_mention, resolved_entity_id, requested_aspects: list[str],
matched_aspect: str | None, match_reason: str, rank: int, channel: "entity_relation")`.
Pydantic `BaseModel`s, no bare dict. The `describe_entity` tool returns
`list[EntityRelationCandidate]`. The application use case returns the domain equivalent
(a frozen dataclass carrying `Claim` + trace fields); the tool wrapper converts.

### Three sets, recorded independently (not one "cited_claims")

To kill the diagnostic blind spot, record separately: (1) **candidates examined**, (2)
**evidence supplied to the answer model**, (3) **claims actually cited**. "Retrieved but
not selected" and "selected but not cited" must be distinguishable. This changes how the
orchestrator's `_absorb` handles the new channel — don't collapse straight into
`cited_claims`. Update the classifier too: if `entity_relation` now reaches a target,
`is_lexically_reachable=False` may still be true *for the lexical probe*, but the target
must no longer be reported as **unreachable by the current system** — add a
system-reachability signal alongside the lexical one in `evaluation/blackbox/classify.py`.

### Designed-for but NOT enabled: variant C (bounded two-hop)

Design records so a 2nd hop is possible (God → *Thoughts of God*) but leave it behind a
switch; enable only if B's measurement shows one-hop insufficient. Not GraphRAG community
summaries; closer to HippoRAG associative retrieval — bounded traversal before Personalized
PageRank. In-memory adjacency over 3984 claims, versioned by corpus blob + normalization
rules; no graph DB.

## First increment = diagnostic table + A / B0 / budget-control comparison

Per target claim record: entity resolved? / requested relation represented? / one-hop
reachable? / needs supported 2nd hop? / selected within budget? / used accurately (with
qualifiers) in the answer? Then compare, **model / prompt / corpus fixed**, and crucially
**separate the ranking change from the budget change**:

| Variant | Ranking | Selected limit |
| --- | --- | ---: |
| A | existing characterization | 20 |
| B0 | aspect-aware relational | 20 |
| Budget control | existing characterization | 40 |

Every variant gathers the **complete entity candidate set**; they differ only in
ranking/limit, compared at the **same final answer evidence budget**. The budget control
isolates "40 alone surfaces rank-21 `ab816dad`, any-gate passes" from a real relational
win. Measure **candidate recall**, **selected-evidence recall**, and **answer use**
*separately*.

## Acceptance criteria (usefulness, not fail→pass)

The any-of gate can pass on the weaker "God created the Soul" while the *knowing* claims
the question actually asks about go missing — so report **target coverage and answer
quality alongside the gate**, not just the gate:

- ≥1 independently-judged-relevant target reaches the **selected evidence** set;
- the answer **uses it accurately and preserves qualifiers** ("only in peace");
- several **independent relational probes** improve (not just this one case);
- **no observed regression** across the existing ~20/21 cases;
- **evidence size and latency** stay within the agreed budget.

## Verification

1. **Unit, transport-free — test aspect discrimination, not `OTHER > is`:**
   `tests/test_ranking.py` — a *thinking* question ranks "knows"/"Thought" evidence above
   unrelated *creation* evidence for the God forms (and vice-versa for a *create*
   question); `tests/test_describe_entity.py` — the full candidate set contains all
   God-subject targets, and object qualifiers survive selection.
2. **Suite + types:** `.venv/bin/python -m pytest tests -q && .venv/bin/pyright` (root),
   plus `apps/agent` and `apps/mcp-server` suites.
3. **Integration diagnostic (corpus-specific):** keep the "`describe_entity('God', think)`
   surfaces `{f99fd11e, 53c77a24}`" check as an *integration* test, not the unit gate.
4. **Black-box (live):** `python -m evaluation.blackbox.run --live` against
   `christ_mind_eval` (`[[eval-uses-christ-mind-eval-db]]`), reporting the acceptance
   criteria above — not merely `required_evidence_present` flipping.

## Constraints honored

No stored inference (a retrieval channel over stored claims; traces are explanations, not
edges); original predicate/verb preserved, aspect maps kept separate; no bare dict (typed
`EntityRelationCandidate`/`RetrievalTrace`); empty `__init__.py`, imports name the
defining module; modern typing; pyright standard. Doctrinal entities stay distinct.
Orchestrator stays behind the MCP tool boundary.
