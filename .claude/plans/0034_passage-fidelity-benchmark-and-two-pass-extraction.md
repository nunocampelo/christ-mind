# Benchmark + two-pass extraction prototype for passage-faithful models

## Context

The `scripts/proto_forgiveness_condition.py` prototype established a *target representation*
for one passage (t3-1-5): a literal claim layer plus a separately-inspectable derived graph
(passage-scoped qualified occurrences, resolved references like "without this" → "without
correction", requirement reframings, descriptions kept distinct from concept nodes). That
fidelity came entirely from **manual interpretation on top of stored claims** — the current
single-pass extractor can't produce it.

The goal now is a pipeline that can reach that fidelity automatically. Per the agreed
mandate (and its corrections): a **two-pass** design — (1) extract evidence-backed literal
structure, (2) derive the graph representation, recording each transformation and its
evidence — with **literal and derived kept separately inspectable**, and **evaluation built
in from the start**. The prototype is a promising target, **not** proof of extraction
accuracy; the first deliverable is a small hand-reviewed benchmark (including
counterexamples) to measure the gap before any corpus re-extraction.

Two corrections carried from the mandate: an object-less claim is **not** inherently wrong
(it's legitimate language the pipeline must handle, not a bug), and drawing "entails
correction" as an unconditional requirement **is an interpretation**, not an extraction
error. So those are pipeline *behaviours to get right*, not defects to fix.

## Scope of THIS plan (benchmark first; prototype second; no corpus re-extraction)

Deliberately staged. This plan covers the benchmark and a two-pass prototype measured
against it. Re-extracting the corpus, bumping `PROMPT_VERSION`, and changing the committed
projection artifact are **explicitly deferred** to a follow-up, gated on benchmark results.

### Stage 1 — the fidelity benchmark (the first real deliverable)

A small gold set of **varied passages including counterexamples**, labelled at the target
fidelity, plus per-dimension metrics. Built by extending the existing harness, not a new one.

- **Gold passages** (new, under `evaluation/claims/fidelity/`): ~8–12 hand-reviewed
  passages chosen for variety and to include counterexamples — e.g. t3-1-5 (condition +
  reference + requirement reframing), a passage with a genuine symmetric contrast (so
  "rather than" vs real `contrasts_with` is tested both ways), an object-less claim that is
  correct as-is (counterexample: must NOT be "fixed"), a plain assertion with no conditions
  (counterexample: must NOT invent qualification), and a multi-reference passage.
- **Dev / report split (separate tuning from evaluation).** Partition the passages: a *dev*
  subset for tuning the deriver/prompt, and a *reserved report* subset that stays untouched
  during tuning and is scored only to report a result — mirroring the existing DEV/HOLDOUT
  split in `run.py`. t3-1-5 (the one the prototype shaped) belongs in **dev**, never report.
- **Literal gold** reuses the existing JSONL claim shape exactly (so `gold.py`'s
  `load_gold_claims` + `anchor_claim` load it unchanged — see
  `evaluation/claims/gold.py:24`). No new fields on `Claim`.
- **Derived gold** is a *separate* sidecar file per passage (new shape, NOT a `Claim`),
  capturing the target derived layer: qualified occurrences, resolved references,
  requirement reframings, descriptions, and for each the **exact supporting span** and
  whether it is literal or interpreted. Kept separate precisely so literal and derived stay
  independently inspectable and the derived schema can evolve without touching `Claim`
  identity/serialization. The schema must support:
  - **Stable annotation IDs + source spans, independent of predicted `claim_id`s.** Gold
    entries key on their own stable annotation ids and on source spans — never on a
    predicted claim's id. Predictions carry their own `claim_id`s; the scorer *aligns*
    predictions to gold by source span + content. This way an extraction difference shows up
    as a *measurable* mismatch, not a broken cross-file link.
  - **Multiple acceptable representations as coherent BUNDLES, not per-entry.** Accepting
    alternatives entry-by-entry could credit an internally contradictory mix (entry A from
    reading 1 + entry B from reading 2). So an "alternatives" group defines whole
    **compatible representation variants**; scoring picks the single best-matching variant
    and matches entries **one-to-one** within it. A prediction is credited for a variant
    only as a coherent whole.
  - **Explicit `unresolved`/ambiguous status.** A genuinely ambiguous reading is marked
    unresolved. The scorer must NOT penalize a prediction for leaving an unresolved item
    unresolved, and must NOT reward inventing a resolution the gold withheld. Report
    **abstention** (prediction left it unresolved, matching gold) and **unsupported
    resolution** (prediction resolved what gold left open) as their own counts.
- **Metrics** (the four the mandate names, plus ordinary claim accuracy). Each is scored
  against the derived/literal **gold**, not inferred from span mechanics:
  - *Ordinary claim accuracy* — reuse `score_claims` loose/strict/relaxed verbatim
    (`evaluation/claims/score.py:63`); no change.
  - *Condition preservation* — scored **independently of `mode`**. `mode_mismatches` only
    says a claim's mode label differs; it cannot tell whether "unless correction occurs"
    survived. So score the condition's **content** (the hinge text), its **presence/absence**,
    its **scope**, and its **attachment to the correct proposition** — four sub-checks
    against the gold's condition entries, reported separately from any mode metric.
  - *Reference resolution* — reported **separately** from condition preservation: were
    antecedents ("this", "it") resolved to the gold's supported referent? A wrong antecedent
    and a missing condition are distinct failures and must not be collapsed.
  - *Qualification* — were qualified occurrences created only where the gold supports them
    (and NOT on the counterexamples)? Report precision and recall separately; a false
    qualification on a plain-assertion passage is the headline failure.
  - *Unsupported inference* — the key guardrail, and **not** an anchoring check. A valid,
    unique quote or an overlapping span proves only *where* evidence comes from, never that
    it *supports* the interpretation. So this metric is scored by **gold comparison**: a
    derived element is unsupported if the gold does not license that reading of its span.
    Span validity (quote is real, unique, attached) is a separate *runtime* check (see
    Validation), not evidence of support. An optional LLM "does this span support this
    reading?" check is only an **additional signal**, flagged as such, never the arbiter;
    genuine unsupported-inference calls need human adjudication captured in the gold.
- Scoring code lives in a new `evaluation/claims/fidelity/score_fidelity.py`, reusing
  `_normalize` and `_phrase_contains` from `score.py` for text comparison so tiers stay
  consistent. A small runner mirrors `run.py`'s shape (header + per-dimension score lines,
  committed under a `runs/` dir).

### Stage 1b — interactive authoring tool (requested)

Authoring the derived gold is judgement-heavy; a CLI session assists it without doing the
judging, and is **staged to protect independence** — the author commits to a reading from
the passage alone before seeing any machine output:

1. **Passage-only phase.** Show *only* the full passage text. The author records derived
   entries — occurrences, resolved references, reframings, descriptions — each requiring
   selection of the **exact supporting span** (validated as a real unique substring by a
   dedicated span validator — see implementation notes; no dummy-`Claim` construction). The
   author may mark an entry `unresolved`/ambiguous or group entries into an **alternative
   variant** (coherent bundle, per #5). These **initial annotations are saved** before
   anything else is revealed.
2. **Reveal phase.** Only after step 1 is saved: reveal the extracted literal `Claim`s, then
   the prototype's output. The author may revise, but the initial annotations and every
   change are kept as **adjudication history** in the sidecar (so we can see what the author
   believed before the machine spoke).
3. **Prototype cross-check scope.** The `scripts/proto_forgiveness_condition.py` logic is
   **passage-specific and renderer-oriented** — it does not derive arbitrary passages. So
   the prototype diff is offered **only for `t3-1-5`** initially; other passages are authored
   passage-only + against the extracted literal claims, with no prototype diff until/unless
   a general deriver exists. The plan does not pretend the prototype generalizes.

The tool writes the derived sidecar + literal `.jsonl`; it never auto-fills a derived entry
from any machine output. It is a staged authoring aid and adjudication recorder, not a
generator.

### Stage 2 — the two-pass extractor prototype (measured against Stage 1)

- **Pass 1 (literal) — contract fixed for the baseline:** keep the existing
  `PromptedClaimExtractor` + production prompt **unchanged**. Pass 1's output is exactly
  today's anchored `Claim`s. Pass 2 receives the **complete `Source` text plus the anchored
  claims** — nothing more. ("Output capture" is deliberately not a thing in the baseline.)
  If experiments later show Pass 2 needs richer literal structure (e.g. the split
  "unless/rather than" hinge rejoined), that is introduced as a **versioned experimental
  sidecar + experimental prompt**, never by changing the production `Claim`, the production
  prompt, or `PROMPT_VERSION`. The baseline measures what the current extractor + a
  derivation pass can already do.
- **Pass 2 (derive):** a new `src/application/derivation/` orchestration package: a function
  `derive_graph(claims, source) -> DerivedModel` (pure, transport-free, unit-testable like
  `build_projection`), plus a `GraphDeriver` protocol so an LLM-backed or rule-backed
  implementation can be swapped and compared on the same benchmark. It consumes anchored
  `Claim`s + the full `Source`, and emits the derived layer (occurrences, resolved refs,
  reframings, descriptions) each carrying its source span and a literal/interpreted flag.
  This is where the prototype's hand-logic becomes real, generalized logic. The reusable
  **representation dataclasses live in the domain layer** (`src/domain/derivation/models.py`);
  only the orchestration lives in `application/` (see Key files).
- **Separation invariant:** Pass 1 output (`Claim`s) is never rewritten by Pass 2; the
  derived model references claims by `claim_id` **for its own internal links only** and adds
  a layer. Literal stays literal. (Gold, by contrast, never references predicted ids — #4.)
- **Validation pass (runtime, structural only).** A checker that asserts *mechanical*
  invariants: every entry's span is a real, unique substring of the source (span validity);
  every resolved reference points at a span that exists; conditions stay attached to a
  proposition; a necessary condition isn't structurally rewritten as a guarantee. These are
  checks the pipeline can make itself. **It does NOT judge semantic support** — a valid span
  is not evidence the span supports the reading. Unsupported-inference is a *scoring* concern
  (gold comparison + human adjudication, §Metrics), not a runtime check; an LLM support-check
  may run here but only emits an advisory signal, never a pass/fail.

## Key files

- New: `evaluation/claims/fidelity/` — gold passages (literal `.jsonl` + derived sidecars),
  `score_fidelity.py`, a small runner, and `author.py` (the interactive authoring tool).
- New: `src/domain/derivation/models.py` — the reusable derived representation dataclasses
  (occurrence, resolved-reference, reframing, description, each with span + literal/
  interpreted flag), in the **domain** layer (entities/representation, transport-free).
- New: `src/application/derivation/derive_graph.py` — the **orchestration** (`derive_graph`,
  `GraphDeriver` protocol), mirroring `src/application/projection/`'s pure/testable shape.
  `__init__.py` empty per repo convention.
- New: a dedicated **evidence-span validator** (e.g. `src/application/extraction/spans.py`
  or alongside `anchor_claim`): `validate_span(source, quote) -> (start, end)` with the same
  real-and-unique quote check, so span validation doesn't require constructing a dummy
  `CandidateClaim`/`Claim` just to reuse `anchor_claim`. `anchor_claim` can be refactored to
  call it, keeping one source of truth.
- New: `src/infrastructure/llm/anthropic_proxy.py` gains a `make_deriver()` factory
  (reusing `make_complete`) only once Pass 2 has an LLM-backed implementation.
- Reused unchanged: `extract_claims.py` (protocol, `anchor_claim`), `prompt.py`
  (Pass 1), `score.py` (`_normalize`, `_phrase_contains`, loose/strict/relaxed),
  `gold.py` (`load_gold_claims`), `domain/claims/*` (no new `Claim` fields — the derived
  layer is its own model, so `claim_id`/serialization are untouched).
- The `scripts/proto_forgiveness_condition.py` prototype stays as the reference for the
  target derived shape; `docs/qualified-concept-uses-survey.md` records the modelling rules.

## Verification

The oracle round-trip alone does NOT establish scorer correctness — **direct scorer unit
tests do** (#7). Build both:

```bash
# Stage 1: author a passage, passage-only first, then reveal (prototype diff only for t3-1-5)
.venv/bin/python -m evaluation.claims.fidelity.author --source t3-1-5

# oracle round-trip sanity: feeding gold back as the prediction scores perfectly on
# dimensions that HAVE applicable items; dimensions with no applicable items for a passage
# report "n/a" (count 0), never a misleading "100%".
.venv/bin/python -m evaluation.claims.fidelity.run --oracle
.venv/bin/pyright
.venv/bin/python -m pytest tests -q
```

**Scorer unit tests (the real proof of scorer correctness)** — hand-built prediction/gold
pairs asserting each failure mode scores as intended:
- a **missing condition** → condition-preservation FN (and does not hide behind a matching
  `mode`);
- a **wrong antecedent** → reference-resolution failure, condition-preservation unaffected
  (the two are independent, #2);
- an **invented qualification** on a plain-assertion passage → qualification *precision* hit
  (false positive), not just a recall number;
- a **contradictory alternative mix** (entry from variant 1 + entry from variant 2) → NOT
  credited; only a coherent single variant matches (#5);
- a **duplicate prediction** → counted once, not double-credited;
- an **unsupported resolution** of a gold-unresolved item → counted as unsupported
  resolution; a matching **abstention** → counted as abstention, neither penalized.

```bash
# Stage 2: run the two-pass extractor against the DEV split, inspect per-dimension scores;
# score the RESERVED report split only when reporting a result.
.venv/bin/python -m evaluation.claims.fidelity.run \
    --extractor infrastructure.llm.anthropic_proxy:make_extractor \
    --deriver infrastructure.llm.anthropic_proxy:make_deriver        # dev split
# expect: literal accuracy ~= current; per-dimension scores reported separately; the
# counterexample passages show qualification PRECISION (no invented occurrences).
```

Unit tests for `derive_graph` assert the t3-1-5 target (qualified occurrence with two
descriptions, "without this"→"without correction", requirement reframing flagged, no
occurrence→healing edge, object-less claim preserved) AND the counterexamples (plain
assertion yields no occurrence; genuine `contrasts_with` stays an edge; correct object-less
claim is not "repaired").

## Explicitly out of scope (deferred, gated on benchmark results)

- Re-extracting the corpus, bumping `PROMPT_VERSION`, regenerating
  `apps/web/public/graph/projection.json`, or wiring the derived layer into the `/graph` app.
- Any new field on the `Claim` dataclass / identity fingerprint / `ClaimLine`.
- Promoting qualified occurrences into shared senses ("worldly forgiveness") — still gated
  on cross-passage evidence per `docs/qualified-concept-uses-survey.md`.
- Commit is left to the user (per no-self-commit).

## Authoring decision (settled)

Derived gold is **hand-written from the passage alone first** — the author commits and saves
initial annotations before any extracted claims or prototype output are revealed (Stage 1b),
then may revise with full adjudication history kept. The prototype cross-check applies **only
to t3-1-5** (it is passage-specific, not a general deriver). Gold allows **multiple
acceptable representations as coherent variants** and marks **genuinely ambiguous readings
unresolved**. This keeps the benchmark an independent target rather than encoding the
prototype's assumptions as the correct answers.

## Review corrections folded in

All seven review points are reflected above: (1) anchoring/span-validity is runtime and
structural; semantic support is gold+human, LLM only advisory; (2) condition scoring is
independent of `mode` and separate from reference resolution; (3) Pass 1 keeps the
production extractor/prompt unchanged, Pass 2 gets source + anchored claims, richer structure
only via a versioned experimental sidecar; (4) gold keys on stable annotation ids + spans,
scorer aligns predictions by span/content; (5) alternatives score as coherent one-to-one
bundles, abstention/unsupported-resolution reported separately, oracle reports n/a (not
"100%") where no items apply; (6) authoring is passage-only-first with saved initial
annotations and adjudication history, prototype cross-check scoped to t3-1-5; (7) dev vs
reserved-report split, plus direct scorer unit tests (not just the oracle round-trip). Two
smaller: a dedicated span validator (no dummy-claim construction), and representation
dataclasses in the domain layer with orchestration in application.

## Stage 1 — SHIPPED (scaffold; 2026-10-04)

Stage 1 only, per the agreed sequencing. **Benchmark scaffold** (schema + scorer + runner +
proof tests, verified on synthetic fixtures); gold passages selected and frozen but
**unauthored** (authoring is Stage 1b). Stages 1b and 2 remain deferred. A second review
tightened the scorer contract before coding; all seven of its points are reflected below.

Delivered:
- `src/application/extraction/spans.py` — `validate_span` + the `Evidence*Error`s moved
  here; `extract_claims.py` imports them from here (no cycle) and `anchor_claim` now calls
  `validate_span`. No behaviour change (`tests/test_spans.py` guards the refactor).
- `src/domain/derivation/{models,identity,serialization}.py` — the derived-gold entities
  (`DerivedKind` incl. `CONDITION`; `Support`/`ResolutionStatus`/`AuthoringStatus`;
  `PropositionSig` gold-owned attachment; `DerivedEntry` with typed per-kind content;
  `Variant`; `DerivedGold` with separate literal/derived authoring status + `exhaustive`).
  `compute_annotation_id` is the content fingerprint (quote + kind + support + resolution +
  canonical content; excludes predicted ids / timestamps / notes / variant membership;
  substantive revision → new id, `adjudication_history` links old→new). Sidecar pydantic
  models recompute the id on load (never trusted), exactly as `ClaimLine`.
- `evaluation/claims/fidelity/` — `score_fidelity.py` (align-then-compare by anchored-span
  overlap + kind, one variant chosen for the whole report, precise n/a semantics, condition
  scored independently of `mode`, reference abstention vs unsupported-resolution split,
  unsupported-inference only where gold is `exhaustive`), `run.py` (dev/report split frozen;
  skips unauthored, reports coverage; `--oracle` over synthetic fixtures; `--report`),
  `fixtures.py` (shared synthetic cases), and seeded `gold/*.{derived.json,jsonl}` for the
  9 frozen passages (all unauthored).
- Tests: `tests/test_fidelity_{identity,serialization,score}.py` + `tests/test_spans.py`.
  `test_fidelity_score.py` is the real proof — one test per failure mode from Verification.

Verified: `.venv/bin/pyright` clean; `.venv/bin/python -m pytest tests -q` → 410 passed;
`--oracle` perfect on applicable dimensions, correct n/a elsewhere; dev/report runs report
`0 authored / N total` coverage and skip unauthored passages.

Second-review fixes folded in (span overlap was being treated as sufficient support):
- A dimension's **true positive now requires both alignment AND a correct reading** across
  all kind-specific fields (occurrence base-concept+scope, requirement proposition+mode,
  description text+target, condition content+scope+attachment). An aligned-but-wrong pair is
  FP + FN, not a free TP.
- **Alignment is field-exact-first, then overlap** — deterministic and order-independent
  even when entries share an evidence quote.
- **Unsupported inference** now counts wrong readings on valid spans (aligned-but-wrong) as
  well as unmatched predictions, where gold is `exhaustive`; matching abstention is excluded
  by construction.
- **Gold anchored strictly** (`GoldAnchorError`) — invalid gold evidence raises, it never
  degrades to a silent scoring miss (prediction misses still handled separately).
- **Sidecar enforces per-kind required/allowed fields + resolution rules + no dangling
  `describes` links**; the allowed/required sets derive from a `ContentField` enum asserted
  against `DerivedEntry`'s fields, so a rename can't silently drift.
- **`--oracle` asserts correctness** (`OracleError`) and fails loudly on a broken round-trip;
  fixtures now cover requirement, description, and a nonempty literal layer, plus abstention.

Third-review fixes (matching/attachment correctness):
- **Maximum-cardinality span matching** (augmenting paths / Kuhn's), replacing the greedy
  first-overlap pass — order-independent and provably optimal even when a broad prediction
  overlaps several gold spans. True positive still requires a correct reading on top.
- **Id-valued links (`describes`) are compared through alignment**, not by fingerprint: a
  description is attachment-correct when its predicted target presence-aligns to the gold
  target, so a differing evidence quote on the target no longer breaks a correct link.
- **Reference matching compares the resolved mention by its span**, so a different mention
  sharing the evidence quote is not credited for a coincidentally-correct referent.
- **Presence vs correctness separated** for conditions and references: presence recognizes
  the aligned entry; the field sub-counts (content/scope/attachment, referent/abstention)
  carry correctness independently. A present-but-wrong-scope condition is presence TP with
  scope 0/1.
- **Oracle assertions check expected counts computed from the gold** (per-dimension item
  counts, condition field counts, referent/abstention counts, literal loose/strict/relaxed)
  and that every dimension is exercised — an accidentally empty or over-counting report
  can no longer pass.
Fourth-review fixes (matching preference, variant key, mentions, source/status):
- **Correctness-preferring matching.** `_span_pairs` now maximizes semantically-correct
  pairs first (Kuhn's over correct-only edges), then augments with remaining overlaps — so
  two entries sharing an evidence span pair to the partner they actually read alike and a
  self-prediction never mismatches its own entries, in any input order.
- **Staged description matching + target constraint.** Non-description kinds match first and
  build the correspondence; descriptions match last using text + `describes` mapped through
  it (so two same-text descriptions with different targets are distinguished). The sidecar
  now enforces that `describes` targets a **non-description** entry (no link cycle).
- **Variant selection by fully-correct counts** (not presence) with a **lowest-id**
  tie-break, so variants differing only in a condition's content/scope don't tie and let an
  exact prediction pick the wrong one.
- **Exact, unambiguous mentions.** A mention must occur exactly once in its evidence quote;
  matching compares exact mention boundaries (ambiguous gold mention → no credit).
- **Source + interpretation status.** `score_fidelity` validates source/gold/prediction ids
  and every entry's source; `support` (and non-reference `resolution`) join every
  correctness check, so an interpreted reading can't pass as literal extraction.
- Final: `pyright` clean, `pytest tests -q` → 422 passed; `--oracle` exits 0.

Frozen split (hypotheses; derived layers unauthored): **DEV** t3-1-5, t3-1-6, t3-4-4,
t1-1-3, t1-1-56 — **REPORT** t2-3-9, t1-1-65, t2-1-13, t4-5-10. Expanding toward 12 is a
versioned split amendment made before tuning, not an ad-hoc expansion.
