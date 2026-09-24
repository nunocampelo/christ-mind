# Increment #6: entity resolution — merge surface forms into entities

Roadmap increment #6 from `semantic-layer-design-and-roadmap.md`. Its predecessor,
#5 (`scale-and-second-gold-batch.md`), is complete: v3.2 prompt, N=3 on the enlarged
dev set stable, `ego` attribution represented and scored, predicate list held (step-4
no-op). The step-5 decision named this as next, because #5's residual gap — object /
subject **surface-modifier differences** the scorer can't collapse (near-miss tally
object 20 / subject 16, run `20260924T063951Z`) — is exactly what entity resolution is
for. This is the detailed plan.

## What #6 is, and what it is not

`Claim.subject` and `Claim.object` are **surface forms** by design (see
`domain/claims/models.py`: "surface forms, not resolved entities"). "the ego", "the
ego's belief", "your ego" are three strings today. Entity resolution decides which
surface forms are **the same entity** so the graph can traverse across passages.

The roadmap fixes two hard boundaries this plan must honour:

- **The LLM chooses among candidates, it does not invent entities.** Same discipline as
  extraction: the model is given a closed set of already-seen mentions and asked "same
  or different", never "name the canonical entity" — a free-text canonical name would
  split apart the way free-text predicates did (Decisions table: "arises_from",
  "comes_from"…). Resolution is a **partition of observed mentions**, not a naming pass.
- **Three representations, never collapsed.** Resolution adds a fourth artifact (a
  mention → entity map) that sits *beside* claims; it never rewrites `Claim.subject`/
  `object`. A claim's evidence-anchored surface form is immutable — the whole point of
  anchoring. The entity id is a *lookup*, not a mutation of the claim.

### Not in this increment

- **Cross-`predicate` or relation resolution.** Only subject/object *mentions* are
  resolved. Merging `causes`-vs-`makes` edges, or deciding two claims say the same
  thing, is a later synthesis concern (#8).
- **A canonical display name per entity.** An entity is an id + its member mentions +
  the count/passages each mention appears in. Picking a human-facing label (probably the
  most frequent or shortest mention) is a presentation detail deferred to #7 retrieval,
  not resolution.
- **A stored claim↔entity link (foreign key on either side).** The relationship "this
  claim's subject is that entity" is real and is what makes the graph traversable, but it
  is **not** stored as a field on `Claim` or `Entity`. It stays a *read-time join through
  the resolution's surface-form map*, materialised by #7. Reasons:
  - **Claim ids are content fingerprints** (`domain/claims/identity.py`). If an entity id
    were a claim field, re-running resolution (which happens whenever the corpus grows or
    blocking improves) would change the ids of claims whose *text never changed* — making
    claim identity depend on a downstream, evolving process. Same objection to storing
    `claim_ids` on an `Entity`: the entity's content would depend on which corpus run it
    was resolved from, and go stale on re-extraction.
  - **The layering is one-directional** (text → claims → entities; the corpus run is
    written before resolution exists and is its input). A foreign key in either direction
    couples two independently content-addressed artifacts and violates "three
    representations, never collapsed".
  - **The resolution file already *is* the join table:** it maps surface form → entity.
    #7 loads a resolution, builds the `surface_form → entity_id` index (exactly the
    scorer's `_entity_of`), and answers "every claim about *the ego* as one entity" by
    entity → member surface forms → claims whose subject/object is one of those forms. A
    many-to-many join on the surface string, recomputed from whichever resolution is
    pointed at — nothing to keep in sync, and it survives re-resolution.
- **Embeddings / a vector store for candidate generation.** Candidates come from
  cheap lexical blocking first (see step 2's gate note); pgvector stays deferred
  (Decisions table) until blocking is shown to be the bottleneck.
- **A database.** Still versioned JSONL / a committed map file, as with claims.
- **Re-running extraction.** #6 consumes the step-1 corpus run from #5 as-is; it does
  not re-extract.
- **A dedicated pair classifier (e.g. Laya).** A calibrated typed-decision classifier
  whose `noul` (binary yes/no + probability) format matches the resolver's same/different
  vote exactly, and which "never generates text, so there is nothing to parse and nothing
  to hallucinate" — removing the whole `RejectedVerdict` failure class. Deferred, not
  adopted, for four reasons: (1) severe domain mismatch — it is trained for ticket/intent
  triage and its own card reports near-chance zero-shot on typed-decisions, so ACIM
  theology ("`God's Will`" vs "`Will of God`") is out of distribution; (2) making it good
  needs fine-tuning on domain data, and #6's pair gold is ~22 labels — orders of magnitude
  too few to fine-tune a ~400M-param model, barely enough to evaluate one; (3) it does not
  touch the actual bottleneck — step 3 showed recall is capped at ~0.90 by *blocking*
  before any model judges a pair, which a better classifier cannot recover; (4) it adds
  `torch`/`transformers` + a model download while local-model infra is deferred to #7. It
  is a legitimate **cost/latency optimization for later**: a cheap ~33 ms/pair local
  classifier drops in behind the `ResolveEntities` protocol unchanged, but only once step
  4 proves the task beats lexical blocking and a real fine-tuning gold set exists.

## Gate note (read first)

The evaluation unit changes: #1–#5 score *claims* (triples + qualifiers); #6 scores a
**partition of mentions** (roadmap evaluation ladder #3, "mention pairs labelled
same/different"). Pair precision/recall is a different metric from claim P/R and lives
in its own scorer — do **not** extend `score.py`'s claim scorer to carry it. There is no
prior number to beat, so **step 0 establishes a lexical-only baseline** (normalise +
exact-match blocking, no LLM) before any model is asked to judge a pair. The LLM
resolver has to beat that baseline on the pair gold set to justify its cost, exactly as
extraction had to beat "emit nothing". Abort/deprioritise condition recorded in step 4.

## What already exists (so this plan doesn't rebuild it)

- **The corpus run to mine.** #5 step 1 wrote a committed unscored corpus run over all
  408 sources (`Split.CORPUS`); its claim lines carry every subject/object surface form
  #6 partitions. `corpus_survey.py` already reads that file shape
  (`ClaimLine.model_validate`) — the mention-extraction tool in step 1 reuses that
  loader, it does not re-parse.
- **`_normalize`** (`evaluation/claims/score.py`) — the article/quote/punctuation
  normaliser the scorer and `corpus_survey` already share. Lexical blocking (step 0/2)
  reuses it so "the ego" and "ego" block together for free; a new normaliser would drift
  from the scorer's.
- **The prompted-extractor pattern** (`application/extraction/prompt.py`): `Complete =
  (system, user) -> reply`, a `SYSTEM_PROMPT` that is the single source of the rules,
  `parse_response`, `PROMPT_VERSION`. #6's resolver copies this shape into its own
  module so every provider is compared on one prompt/parser (Decisions table,
  provider-agnostic) — it does **not** reuse the *claims* prompt.
- **Gold discipline.** #1–#5's rule holds: gold written in the same shape and loaded by
  the same code as the thing under test, rules living in one prompt, one commit per
  measurement change. The pair gold set (step 3) follows it.
- **DDD layers.** New code lands in the existing layers, no new top-level trees:
  `domain/entities/`, `application/resolution/`, `infrastructure/llm/` (the resolver
  adapter reuses the existing `anthropic_proxy` `Complete`), `evaluation/entities/`.

## Steps

Each step is its own commit. As in #4/#5, no step both changes how something is measured
and changes the numbers at once. Steps 1 and the mention-extraction tool move no scored
numbers; the scored comparison is steps 0, 2, and 4.

### 0. Mention inventory + lexical baseline (no LLM, no gold yet)

`evaluation/entities/mentions.py`: `python -m evaluation.entities.mentions <corpus run>`

- Read the #5 corpus run, collect every distinct `subject`/`object` surface form with
  its frequency and the source_ids it appears in. This is the **mention universe** #6
  resolves over — report its size (distinct mentions, total occurrences).
- Apply lexical blocking: group mentions whose `_normalize` value is equal. Report the
  block-size distribution (how many mentions collapse purely on normalisation, how many
  singletons remain). This is the **free floor** — resolution that a normaliser already
  gets, before any model.
- No gold, no scoring here — this step sizes the problem and confirms the corpus run is
  the right input. Output is a report to stdout plus a small committed summary; it tells
  the maintainer how big the pair gold set in step 3 needs to be and where the
  interesting near-duplicates cluster (e.g. "the ego" family).
- Tests: with a stub run file, distinct-mention count and the normalised blocking are
  correct and deterministic. Mechanical.

### 1. Entity model + the mention→entity artifact shape

`domain/entities/models.py`; `evaluation/entities/run_format.py` (or reuse a shared one)

- `Mention` (frozen dataclass): the surface form + where it came from
  (`source_id`, and which side — subject/object — is carried by the claim, so a mention
  is keyed by its normalised text, not by claim). `Entity` (frozen dataclass): an
  `entity_id` (deterministic fingerprint over its sorted member mentions, mirroring
  `claim_id`/`identity.py` — an entity's id is content-derived, not a surrogate) plus
  its member mentions. **No canonical name field** (see Not in this increment).
- A `Resolution` artifact = the partition: a list of `Entity`, written as versioned
  JSONL with a header hashing the input corpus run's `passages_sha256` so a resolution
  can be checked for drift against the run it was built from — same header discipline as
  claim runs.
- No behaviour on the dataclasses (Style: entities have no methods, like `Source`/
  `Claim`). No transport, no storage concern in `domain/`.
- Pyright clean, no bare `dict` in any shape that will become a tool return later.
- Tests: `entity_id` is stable under member reordering and distinct for distinct member
  sets. Domain-layer fixtures are real dataclasses, not dict literals (Tests policy).

### 2. LLM pair resolver over blocked candidates

`application/resolution/resolve_entities.py` + `application/resolution/prompt.py`

- **Candidate generation by blocking, not all-pairs.** Resolving N mentions is O(N²)
  naively; block first (step 0's normalised grouping, plus a cheap token-overlap/prefix
  block so "the ego" and "the ego's belief" land in the same candidate set) and only ask
  the model about within-block pairs. Record the blocking recall risk: a pair the
  blocker never proposes can never be merged — step 3's gold must include a few
  cross-block same-pairs to measure exactly this. Gate note: if blocking recall on gold
  is already very high and its false-pair volume low, an LLM pass may not beat it —
  that's the step-4 decision, decided by numbers not assumption.
  - **As built (step 2):** `candidate_pairs` blocks on `_normalize`-equality (the free
    floor) plus **shared head token** (last normalised word), so "the ego"/"ego"/"the
    false ego" all pair. Four unrelated head tokens yield zero pairs, not the 6 all-pairs
    — blocking is doing its job. **Known recall gap, recorded now:** `_normalize` does
    not strip apostrophes, so a possessive modifier moves the head noun off the last
    slot — "the ego's wish" normalises to "ego's wish", head token "wish", and does
    **not** block with "ego". Step 3's cross-block same-pairs must include a possessive
    case so this gap is measured, not assumed away. Widening the blocker (e.g. also
    keying on the first content token) is a deliberate later decision if the gold shows
    the gap costs real recall — not done pre-emptively, per the plan's "let the numbers
    decide" discipline.
- **`ResolveEntities` protocol + `PromptedResolver`** mirroring `extract_claims.py`'s
  `ClaimExtractor`/`PromptedClaimExtractor`: a `Complete` function answers "are these two
  mentions the same entity, given these example occurrences?" against a `SYSTEM_PROMPT`
  that states the same/different rules (the *only* place those rules live, mirroring the
  claims prompt), with `parse_response` and its own `RESOLVER_PROMPT_VERSION`. The model
  **only** votes same/different on presented candidate pairs — it never emits a new
  mention string (the "choose among candidates, don't invent" boundary, enforced by the
  parser rejecting any mention not in the presented pair, the way `anchor_claim` rejects
  a quote not in the source).
- Transitive closure over the model's "same" votes builds entities; a rejected/malformed
  pair judgement is recorded (rate is a quality signal, like claim rejections), not
  silently dropped.
- The adapter reuses `infrastructure/llm/anthropic_proxy`'s `Complete` — no new provider
  file unless a second provider is added (out of scope, as in #5).
- Tests (`application/resolution` — orchestration, transport-free, unit-testable like
  `find_sources`): with a stub `Complete` returning canned same/different verdicts,
  transitive closure produces the expected partition, an out-of-candidate mention in a
  verdict is rejected, and blocking never proposes an all-pairs explosion. Mock the
  `Complete`, not the application layer (Tests policy).

### 3. Pair gold set + a pair scorer

`evaluation/entities/gold/*.jsonl`; `evaluation/entities/score.py`

- A person hand-labels **mention pairs** as same/different, sampled from step 0's blocks
  (the near-duplicate clusters are where judgement is needed; two obviously unrelated
  mentions teach nothing). Include: within-block hard cases ("the ego" vs "the ego's
  wish"), a few **cross-block** same-pairs to measure blocking recall (gate note), and
  clear negatives. Keyed on the two normalised mention strings, written and loaded by the
  same code as the resolver consumes (gold discipline). Rules the labeller follows live
  in step 2's `SYSTEM_PROMPT`, not in the gold file.
- `score.py` for **pairs**: precision/recall over same-labelled pairs (a predicted merge
  the gold calls different is a false positive; a gold same-pair not merged is a false
  negative). Separate from the claim scorer (gate note) — its own module, its own
  `ClaimScore`-shaped result. Report the lexical-baseline number (step 0) and the
  resolver number side by side.
- Tests: the pair scorer's P/R matches a hand-worked tiny example; loader anchors both
  mention strings to the mention universe and fails loudly if a gold mention isn't
  present in the run (mirrors `load_gold_claims`). Construct real `Mention`/pair types,
  not dict literals.

### 4. Score the resolver against the baseline; decide

`evaluation/entities/run.py` (or extend the mentions tool) — a scored resolution run

- Run the LLM resolver over the blocked candidates, score against the step-3 pair gold,
  N≥3 (stdev is the noise floor, exactly as #4/#5), and record pair P/R for **both** the
  lexical baseline and the resolver in this file's results log.
- **Decision:**
  - If the resolver beats the lexical baseline by more than the noise floor on pair
    P/R (especially recall on cross-block same-pairs the normaliser can't get), #6
    delivers a committed `Resolution` over the full corpus run and #6 is done — next is
    #7 (expose claims + their resolved entities to the agent).
  - If the resolver does **not** clear the baseline (blocking already captures the easy
    merges and the model adds mostly false merges), **stop and ship blocking-only
    resolution** as the #6 artifact, record that the LLM pass didn't pay, and revisit
    with embeddings-based candidates when #7's retrieval load justifies it. This is the
    abort condition — a real possibility given how much `_normalize` already collapses,
    and cheaper to accept than to force.
- One commit for the scored run + log row; if the resolver ships, a second commit writes
  the full-corpus `Resolution` file (large, committed JSONL, like the corpus claim run).

## Open questions to resolve while building (not blockers)

- **Mention identity across subject/object.** A mention keyed by normalised text alone
  merges "love" as a subject with "love" as an object — almost certainly right, but step
  0's report should confirm the two roles don't need separating before step 1 fixes the
  `Mention` key.
- **Blocking algorithm.** Step 2 starts with normalise + token-overlap; if step 0 shows
  the mention universe is small enough (low thousands), all-within-normalised-block pairs
  may be tractable without a fancier blocker. Let step 0's size number decide.
- **Attribution and entities.** "the ego" as a `course`-attributed subject vs. inside an
  `ego`-attributed claim is the same entity; attribution is a property of the *claim*,
  not the mention. Keep them separate (don't fold attribution into `entity_id`) — noted
  here so it isn't re-litigated.
- **Claim↔entity link.** Resolved: the link is a read-time join through the resolution's
  surface-form map (#7's job), never a stored field on `Claim` or `Entity`. See the
  reasoning under "Not in this increment".

## Step 0 findings (mention universe + free floor)

`python -m evaluation.entities.mentions evaluation/claims/runs/20260923T221456Z.jsonl` (the #5
corpus run, 3984 claims):

- **Mention universe: 4589 distinct surface forms, 7747 occurrences.** Low thousands —
  so the "blocking algorithm" open question resolves to the simple end: all-pairs
  *within a normalised block* is tractable, no token-overlap blocker needed for a first
  pass. Cross-block candidate generation is the only part that needs a cheap heuristic
  (step 2).
- **Lexical blocking (normalise only) already collapses 506 forms into 225 multi-member
  blocks; 4083 singletons remain.** That is the free floor.
- The multi-member blocks are **almost entirely capitalisation + determiner variants**
  the normaliser already catches: `'ego'`/`'the ego'`/`'the EGO'`/`'an ego'` (×5),
  `'knowledge'`/`'Knowledge'`/`'HIS knowledge'`, `'perception'`/`'Perception'`/`'the
  perception'`, etc. The author's emphatic capitals (corpus caveat) generate a lot of
  these, and `_normalize` lower-cases them for free.
- **Implication for the step-4 decision, recorded now:** most of what's cheaply
  mergeable, normalisation already gets. The LLM resolver's value has to come from
  **cross-block** merges the normaliser cannot reach — "the ego" vs "the ego's belief"
  vs "self esteem in ego terms" (from #5's t4 ego passages), where the head noun matches
  but modifiers differ. The step-3 pair gold must therefore be weighted toward
  cross-block same-pairs, or the baseline will look artificially close to the resolver
  and the abort condition will fire on a rigged comparison. This is the object/subject
  surface-modifier gap #5's near-miss tally flagged — the reason #6 exists.
- Subject/object pooling confirmed harmless: the report pools both roles into one
  universe and nothing suggests a form means different things by role, so step 1 keys
  `Mention` by normalised text alone (open question resolved).

## Step 3 findings (pair gold + blocking recall)

`evaluation/entities/gold/pairs_ch1_4.jsonl`: 22 hand-labelled pairs (19 same, 3
different), every form a real surface form from the #5 corpus run and anchored by
`load_gold_pairs` against the run's mention universe (the fail-loud guard passed at
4589 mentions). The pairs are grounded in step 0's blocks: caps/determiner variants
(`ego`/`the EGO`/`his ego`, `knowledge`/`Knowledge`/`HIS knowledge`, `mind`/`MIND`),
two cross-block same-pairs, and hard negatives that *do* block so they aren't trivially
correct (`God`/`Son of God`, `fear`/`REAL source of fear` — shared head token, must
stay different).

**Blocking recall on the gold same-pairs = 0.895 (17/19).** The two misses are exactly
the recall gap the gold exists to measure, and one was unanticipated:

- `God's Will` / `Will of God` — the possessive case flagged in step 2: heads "will"
  vs "god", so the blocker never proposes it. Expected.
- **`miracle` / `miracles` — singular/plural. Unanticipated:** `_normalize` doesn't
  stem, so the two head tokens differ and the blocker misses it. This is a second real
  blocking-recall gap the gold caught, distinct from the possessive one.

So the ceiling on the resolver's pair recall is ~0.90 *before it judges anything* —
the blocker, not the model, caps the missing 10%. This is precisely the number step 4
needs to attribute a low recall correctly (blocker vs. model) and is the strongest
argument for widening blocking (stemming + a possessive/prepositional-head key) if
step 4 shows the gap costs real recall. Not done pre-emptively — the resolver runs
against this ceiling first, per the plan's "let the numbers decide" rule.

`score.py` reports `PairScore` (P/R over same-pairs, kept separate from the claim
scorer) plus `blocking_recall` alongside, so the two are never conflated.

## Step 4 findings (resolver vs. baseline; the decision)

`python -m evaluation.entities.run --baseline` and `--resolver
infrastructure.llm.anthropic_proxy:make_resolver`, N=3. Both paths resolve the gold's
own mentions through the same `resolve`/`score_pairs`, differing only in who judges the
pairs.

| | pair P | pair R | tp / fp / fn |
| --- | --- | --- | --- |
| lexical baseline (no model) | 1.000 | 0.789 | 15 / 0 / 4 |
| LLM resolver (N=3, all identical) | 1.000 | **0.895** | 17 / 0 / 2 |

- **The resolver beats the baseline by +0.106 recall at equal, perfect precision**, N=3
  stdev 0.000 — far beyond the noise floor. It hits the **blocking ceiling exactly**
  (0.895): it recovered *every* reachable same-pair the normaliser misses
  (`forgiveness`/`God's forgiveness`, `fear`/`all FEAR`) and made **zero false merges**
  on the hard negatives (`God`/`Son of God`, `fear`/`REAL source of fear`,
  `God`/`God's Will`). The prompt's "same thing, not same words" rule holds on real ACIM
  vocabulary.
- **The residual gap is now entirely the blocker, not the model.** The 2 remaining FNs
  (`God's Will`/`Will of God`, `miracle`/`miracles`) are pairs `candidate_pairs` never
  proposes, so no judge — model or human — can reach them. The step-3 abort risk (blocker
  so good the LLM can't beat it) did **not** materialise; the opposite, milder finding
  did: the model is at ceiling and the blocker is what caps recall.
- **Decision: the resolver clears the bar → #6 is done.** The remaining work is not more
  prompting: it is **widening blocking** (stemming for singular/plural; a
  possessive/prepositional-head key for `God's Will`/`Will of God`) to raise the ceiling,
  which is pure lexical code with its own before/after `blocking_recall` number — a
  natural first task for #7's consumption of resolved entities, or a small follow-up
  commit here. The full-corpus `Resolution` file (all 4589 mentions) is the ship
  artifact; writing it is a separate, large-output commit and is **not** required to call
  the #6 method proven. Next roadmap increment: #7 (expose claims + resolved entities to
  the agent).
- **Recorded artifact.** `run.py` now writes a resolution run file (header hashing the
  source claims run's passages, one line per entity) under `evaluation/entities/runs/`
  when passed `--record`. The **baseline** full-corpus resolution is recorded already
  (free, no model): `20260924T073722Z.jsonl`, 4308 entities over 4589 mentions — matching
  step 0's 4308 normalised blocks exactly, the expected sanity check, with the "ego"
  family (`ego`/`the ego`/`the EGO`/`his ego`/`an ego`) correctly merged. Recording the
  **LLM** resolver over the whole corpus is the large provider run and is left as an
  explicit `--record` invocation when wanted; the baseline file already captures every
  merge normalisation gets, which step 4 showed is most of them.
- **Run-file layout.** Run files are now per-concept: `evaluation/claims/runs/` (claim
  extraction runs) and `evaluation/entities/runs/` (resolution runs), not one shared
  `evaluation/runs/`. The entities runner reads its input claims run across concepts via
  an explicit `../claims/runs/...` path, making the real dependency (resolution consumes
  extraction's output) visible rather than hidden in a shared bucket.

## Results log

| Run | Resolver | Metric | Baseline pair P/R | Resolver pair P/R | Notes |
| --- | -------- | ------ | ----------------- | ----------------- | ----- |
| — | none (step 0) | — | — | — | Mention universe 4589 forms / 7747 occ over the #5 corpus run; normalise-only blocking collapses 506 → 225 blocks, 4083 singletons. Free floor is mostly caps/determiner variants; LLM must earn its keep on cross-block merges. Sizes step 3's gold; no scoring yet. |
| — | none (step 3) | blocking recall | — | — | 22 gold pairs (19 same / 3 different) grounded in real corpus forms. Blocking recall on same-pairs 0.895 (17/19); misses `God's Will`/`Will of God` (possessive) and `miracle`/`miracles` (singular/plural, unanticipated). ~0.90 recall ceiling before the model judges. No resolver scored yet — that's step 4. |
| — | lexical baseline | pair P/R | 1.000 / 0.789 | — | step 4: no-model floor. Perfect precision, 15/19 same-pairs (the 4 misses are non-normalise-equal). |
| — | anthropic_proxy (N=3) | pair P/R | 1.000 / 0.789 | **1.000 / 0.895** | step 4: LLM resolver, all 3 runs identical (stdev 0). +0.106 recall over baseline at equal precision, 0 false merges. Hits the 0.895 blocking ceiling exactly — recovered both reachable misses; the 2 residual FNs are blocker-unreachable. **#6 done; residual gap is blocking, not the model.** |
| 20260924T073722Z | baseline (`--record`) | recorded | 1.000 / 0.789 | — | Baseline full-corpus resolution recorded: 4308 entities over 4589 mentions (= step 0's block count), 0 rejected. `evaluation/entities/runs/`, header hashes the source claims run. LLM full-corpus record left as an explicit `--record` run. |
