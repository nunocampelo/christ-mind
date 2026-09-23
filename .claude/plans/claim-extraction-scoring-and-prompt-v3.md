# Claim extraction: scoring fixes and prompt v3

Run 1: `evaluation/runs/20260923T002530Z.jsonl`, prompt v2, dev split, via
`infrastructure.llm.anthropic_proxy`.

## Where run 1 landed

| Matching                                                       | Matched | P    | R    |
| -------------------------------------------------------------- | ------- | ---- | ---- |
| Current scorer (`loose`, case/whitespace only)                 | 26      | 0.30 | 0.31 |
| + ignore articles, quote style, punctuation                    | 38      | 0.44 | 0.46 |
| + phrase containment, overlapping evidence, same predicate     | 54      | 0.62 | 0.65 |

The two lower rows are one-off estimates from a scratch script, not the scorer. The
scorer today exposes two tiers, `loose` and `strict` (`ScoreReport.loose`, `.strict`
in `score.py`); step 1 enriches their normalisation and adds a third tier, `relaxed`.
Those three names — `loose` / `strict` / `relaxed` — are used consistently below and
in the results log; there is no separate "exact" tier.

What already works: 0 rejected candidates (every quote exact), polarity right on
every negation, mode and attribution right on almost every matched claim, and 4.8
claims per passage against the gold set's 4.6.

Most of the gap is surface wording the scorer treats as a miss. The rest is a
small set of real errors, listed in step 4, and predicate choices where the gold
set and the model reasonably disagree, listed in step 5.

## Steps

Each step is its own commit, and no step both changes how scores are measured and
changes the scores themselves at once. That way every change in the numbers can be
traced to its cause. (Steps 2 and 3 are tooling — output shape and a report — and
move no numbers at all.)

### 1. Scorer: normalise wording, add a relaxed tier

`evaluation/claims/score.py`

- Keep the existing `loose` and `strict` tiers (rename nothing); step 1 only enriches
  their normalisation and adds `relaxed` alongside them.
- `_normalize` for all tiers:
  - lowercase;
  - fold curly quotes and apostrophes (`’ ‘ “ ”`) to straight;
  - strip punctuation (`. , ? ! "`);
  - drop leading determiners (`the a an this that their his its`).
- Keep quantifiers (`all`, `no`) and modifiers (`particularly`, `Himself`). Dropping
  them is a judgment about meaning, not formatting, and a matched claim would then
  hide it.
- Add a `relaxed` `ClaimScore` to `ScoreReport`. A predicted and a gold claim match
  if:
  - they have the same source and predicate;
  - their evidence spans overlap;
  - for subject and object alike, one normalised phrase contains the other;
  - both objects are null, or neither is.
- Pair claims one-to-one, strict matches first, reusing `_pair_loose_matches`'
  approach, so one broad prediction can't match three gold claims.
- Report loose, strict and relaxed side by side, each answering a different question:
  - **loose** — regression detector for literal correctness (triple match after
    normalisation).
  - **strict** — the primary extraction-quality metric, and the one that must rise.
  - **relaxed** — a *diagnostic* for surface-form disagreement ("is the model
    extracting the same claim despite wording?"), never the optimization target.
    Tuning toward relaxed rewards increasingly broad predictions that score through
    containment; the one-to-one pairing below is the guard against that, but the
    metric still must not be the headline.
- Tests:
  - article and quote differences now match under `loose` and `strict`;
  - containment matches only when the evidence overlaps;
  - one prediction can't satisfy two gold claims;
  - a strict match already consuming its gold partner isn't re-counted under relaxed
    (the one-to-one invariant of the new pairing);
  - a reversed `causes` does not match under relaxed.
- Re-score run 1 with the new scorer (no new model call) and record all three tiers
  here. Note that enriching `_normalize` moves the `loose` and `strict` numbers too,
  not just the new `relaxed` tier — so this re-score, not the run-1 table above, is
  the baseline from now on, and every later number traces to it.

### 2. Run output: readable claim lines

`evaluation/claims/run.py`

Each claim line is currently `{"type": "claim", **asdict(claim), "evidence": ...}`,
so its keys follow the `Claim` dataclass order — `subject`, `predicate`, `object`,
`verb_phrase`, ... — which puts `predicate` between `subject` and `object` and buries
`verb_phrase`, making a line hard to read at a glance.

- Build the claim line with an explicit key order instead of `asdict`, leading with
  the fields a human scans:

      type, source_id, subject, verb_phrase, object, predicate, polarity, mode,
      attribution, evidence, evidence_start, evidence_end

  so "subject verb_phrase object" reads as the sentence, then the classification
  fields, then evidence and its offsets last.
- Output-shape change only — no scores move, so it's its own commit. It rewrites only
  the key order within each line, not the values, and the header/rejected/failed line
  shapes are unchanged.
- Re-emit run 1 (`--extractor` re-run not needed; reorder is cosmetic) or leave the
  existing committed run file as-is and note that lines written before this step keep
  the old order. New runs from here on use the readable order.

### 3. Near-miss report as a real tool

`evaluation/claims/near_miss.py`: `python -m evaluation.claims.near_miss <run file>`

- For each unmatched gold claim, show the predicted claim from the same source whose
  evidence overlaps it most, and which fields differ (subject, predicate, object,
  polarity, mode, attribution).
- End with a tally by differing field. This is the scratch script from run 1's
  analysis, made permanent. It's how steps 3 and 4 get checked on every run.
- Also list predictions that overlap no gold evidence at all. Those are either
  extra claims or gaps in the gold set, and deciding which needs a person to look.

### 4. Prompt v3: fix the real errors

`src/application/extraction/prompt.py`, bump `PROMPT_VERSION` to `"3"`

Run 1 errors, each needing a worked example rather than a restated rule, since the
rule was already there:

- **`causes` direction reversed (3 of 3 inverted forms):**
  - "interpretation arose out of misprojections" → subject `combined misprojections…`
  - "unwillingness arose from escape value" → subject `escape value`
  - "I was NOT punished because YOU were bad" → subject `your being bad`, `negated`

  Add an explicit instruction: for `causes`, the subject is the cause. "X arose
  from Y", "X because Y" and "X is the result of Y" all put Y first.
- **Relative clause swapped subject and object:** "a point which many very sincere
  Christians have misunderstood" → subject `many very sincere Christians`.
- **Double negative reproduced:** "No-one who is free of the scarcity-error could
  POSSIBLY make this mistake" → subject `one who is free of the scarcity-error`,
  `negated`. Add this sentence itself as the example.
- **`makes` on an ordinary "make":** limit `makes`/`creates` to the Course's sense
  (making by the ego or perception vs. creating by spirit). "Make a mistake" is
  `other`.
- **Embedded propositions not extracted:** "reawaken the awareness that the Spirit,
  not the body, is the altar" should also give `Spirit is altar of truth` and `body
  is not altar of truth`. New rule: a "that X" clause after
  awareness/belief/recognition/idea is extracted as its own claim(s). Its
  attribution comes from the frame: a "fallacious belief that X" makes X `others`.
- **Housekeeping:**
  - make the "did NOT cause" example's verb_phrase match the gold set ("did NOT
    cause", not "caused");
  - rewrap the over-long line in the negation rule.

Success: in step 3's report, none of these five error types appears on the dev
split.

### 5. Settle predicate conventions (decisions for the maintainer)

Each of these is a convention, not a fact about the text. Whichever way each one
goes, the gold set and the prompt change together in one commit.

| Text                                   | Gold now    | Model (run 1) | Recommendation |
| -------------------------------------- | ----------- | ------------- | -------------- |
| "are natural expressions of"           | `expresses` | `is`          | keep `expresses`: it's the predicate's purpose |
| "Miracles are healing"                 | `causes`    | `is`          | switch gold to `is`; the "effect adjective → causes" rule is too clever |
| "release the future"                   | `other`     | `causes`      | keep `other`; "release" isn't causation |
| "love is received through prayer"      | `other`     | `requires`    | keep `other`; a channel isn't a precondition |

Also decide **where the verb ends**: "Prayer | is the medium of | miracles" vs.
"prayer | is | medium of miracles". Recommendation: for copulas (`is`, `are`), the
verb is just the copula and the whole noun phrase is the object. That matches most
of the gold set, and relaxed matching tolerates the rest.

### 6. Run v3 several times, then decide

- At least three dev runs with identical settings (`tmp/compare_prompts.py` already
  does N runs and reports stdev; promote it or run it as-is). Two runs give one
  difference, not a floor; use the stdev across N≥3 as the noise floor and don't act
  on a change smaller than it.
- Record each run's loose, strict and relaxed scores in the results log below.
- Next step depends on the result:
  - **Relaxed R ≥ ~0.8 and no step 4 error types:** run the holdout once and record
    it. Then extend gold labelling to more passages, prioritising ones with
    `ego` attribution, since there are none yet.
  - **Otherwise:** iterate on the prompt against dev only, one change per run. The
    embedded-proposition rule (step 4) is the one to watch: it raises claim count and
    can cost precision, so if strict-P drops below the re-scored baseline it's the
    first change to isolate.

## Not in this plan

- Entity resolution ("miracle" vs "miracles"). Relaxed matching covers what's
  needed for scoring; resolving entities is its own increment (see Roadmap).
- A second provider. It's worth comparing once v3 is stable. Nothing in the runner
  needs to change for it.
- Growing the predicate list. `other` is still about a third of gold claims, but
  change it only once step 3's report shows which `other` verbs recur across more
  passages than T1.1 and T3.2. Resist expanding `Predicate` in general: it is a
  small set of relationship operators, and `verb_phrase` already carries the textual
  nuance ("causes" + verb_phrase "arises from"). Don't grow it into a taxonomy of
  overlapping verbs.

## Roadmap: after v3

Claim extraction is the foundation of an ACIM semantic model, not a detour. The next
real step after v3 is **not** concept extraction — it is `mentions → resolution`,
because that is what turns a bag of claims into a coherent model. The ordering below
is load-bearing; the layers depend on each other in this sequence.

**The invariant that governs the whole roadmap — identity precedes interpretation:**
entity resolution establishes which mentions refer to the same underlying entity
*without using semantic type*; semantic types and higher-order relationships are
derived from the resulting clusters and their claims, and never flow backward into
initial identity resolution.

The layers, in dependency order (add each directory only once it has real code — do
not scaffold `domain/entities/`, `domain/relations/`, `application/agent/` ahead of
need; `evaluation/` stays at the repo root, not under `src/`):

1. **Stable `claim_id` on the `Claim` model** — prerequisite, small. Today a claim is
   identified by `source_id` + evidence offsets; every layer above must reference
   claims by a stable id, not reconstructed offsets.
2. **`extract_mentions.py`** — surface expressions and their role (subject/object),
   keeping the text's own wording. No canonicalisation here.
3. **`resolve_entities.py`** — a candidate pipeline, **type-independent** (not
   semantics-free: embedding similarity and LLM adjudication are semantic; the point
   is that an entity's *assigned type* must never be an input to deciding identity):
   lexical normalisation → candidate generation (exact/alias, embedding, contextual
   retrieval) → LLM as the *last* adjudicator, not the first lookup. Identity answers
   "do these mentions refer to the same thing?" — distinct from typing's "what kind of
   thing is this?". Embedding closeness alone is not an identity decision:
   `"idea of separation"` and `"separation"` are close but not the same entity.
4. **Semantic typing** — downstream of identity, over resolved clusters and their
   claims (a materialised property later relation-interpretation and retrieval
   consume, not a decorative final read model). `unknown` is a permitted type; do not
   force everything into the ontology. Types emerge from usage across the corpus.
5. **`synthesize_relations.py`** — relations carry `kind: explicit | synthesized |
   inferred` and `supporting_claim_ids`, so a derived edge (separation → … → guilt) is
   never confused with a stated one.
6. **Agent layer** — retrieves entities, their related claims, and the source
   passages, and generates answers constrained to that context.

**Provenance + extraction-run version attach to every layer, not just claims.** The
governing rule: the LLM may *propose* semantic structure; the store keeps that
structure only together with its provenance and extraction version.

**Evaluation ladder — each level gets its own gold set:**

1. Claim extraction (current work).
2. Entity mention extraction.
3. **Entity resolution** — its own evaluated layer, a gold set of mention *pairs*
   labelled same/different (`("miracle","miracles") → same`,
   `("self","self-concept") → different`). This is what dissolves the identity-vs-type
   chicken-and-egg: identity is evaluated directly, before any typing. Without it you
   can post a strong claim score while silently building a terrible ontology, and the
   damage is invisible from the claim metrics alone.
4. Relation extraction.
5. Relation synthesis (derived only what the source supports).
6. Agent application (did the agent apply the model correctly to a situation?).

## Results log

| Run | Prompt | Split | Loose P/R | Strict P/R | Relaxed P/R | Notes |
| --- | ------ | ----- | --------- | ---------- | ----------- | ----- |
| 20260923T002530Z | v2 | dev | 0.30 / 0.31 | 0.29 / 0.30 | — | old scorer, before step 1 |
| 20260923T002530Z | v2 | dev | 0.43 / 0.45 | 0.40 / 0.42 | 0.62 / 0.65 | re-scored under step-1 scorer (no new call) — **this is the baseline from now on**; mode mismatches 2 |
| 20260923T075901Z | v2 | dev | 0.45 / 0.47 | 0.43 / 0.45 | 0.62 / 0.65 | fresh v2 run in the readable (step-2) format — the file to diff against v3; within run-to-run variance of the re-score; mode mismatches 2 |
| 20260923T081252Z | v3 (pre-sharpen) | dev | 0.44 / 0.48 | 0.40 / 0.45 | 0.62 / 0.69 | first v3 run. Relaxed R 0.65→0.69 (57 matched). Step-4 near-miss check: `causes` reversal fixed (all 3 now correct direction), relative-clause swap fixed, double-negative fixed, embedded proposition fixed; **`makes`-on-"make this mistake" survived once** (t3-2-1). Sharpened the `makes` rule after this run. |
| 20260923T081750Z | v3 | dev | 0.46 / 0.51 | 0.45 / 0.49 | 0.63 / 0.70 | sharpened-v3 run 1 of N=3 |
| 20260923T081927Z | v3 | dev | 0.46 / 0.52 | 0.45 / 0.51 | 0.63 / 0.71 | sharpened-v3 run 2 of N=3 |
| 20260923T082110Z | v3 | dev | 0.47 / 0.52 | 0.45 / 0.49 | 0.62 / 0.69 | sharpened-v3 run 3 of N=3 |

**Sharpened-v3, N=3 dev (mean ± stdev):** loose 0.460±0.006 / 0.514±0.007 · strict 0.446±0.001 / 0.498±0.007 · relaxed 0.626±0.005 / 0.699±0.012 (58±1 matched). Noise floor on relaxed R ≈ 0.012. All five step-4 error types cleared in all three runs (the only surviving `makes` is `intellectualizing makes the physical`, a genuine Course-sense make). vs. the re-scored v2 baseline (strict R 0.42 → 0.50, relaxed R 0.65 → 0.70): strict R gain (~0.08) and relaxed R gain (~0.05) both exceed the noise floor.
