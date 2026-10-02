# Increment #5: scale extraction, second gold batch, predicate-list review

Roadmap increment #5 from `semantic-layer-design-and-roadmap.md`. Its predecessor,
#4 (`claim-extraction-scoring-and-prompt-v3.md`), is complete: prompt v3.1, N=3 dev
runs, all step-4 error types cleared. This is the detailed plan for #5, written now
that #4 holds.

## Gate note (read first)

The roadmap says #5 comes "once #4 holds on the holdout", and step 6 of the v3 plan
gates the holdout on relaxed R ≥ ~0.8. We are at **relaxed R 0.72** (v3.1, N=3), and
the v3.1 log's own conclusion is that the remaining dev gap is dominated by
surface-modifier subject/object differences and gold-vs-model convention edges —
**the entity-resolution layer's job (#6), not more prompt iteration.** So relaxed R is
plateaued by design, not by an unfinished prompt.

Decision embedded in this plan: **do not treat 0.8 relaxed R as a hard blocker for
#5.** Instead, step 0 runs the holdout **once** to get an honest generalization number
on the current prompt before any gold grows, and #5 proceeds regardless. Rationale:
the point of #5 is to expose the extractor to unlabelled corpus and to build the
`ego`/`other`-verb evidence that #6 depends on — waiting for a prompt-only metric to
clear a gate that the log says only #6 can move would stall the roadmap on the wrong
layer. If the holdout comes back far below dev (say strict R < ~0.35, a real
generalization failure rather than the expected small drop), stop and reopen the
prompt instead of scaling — recorded as the abort condition in step 0.

## What already exists (so this plan doesn't rebuild it)

- **Corpus is fully parsed:** `infrastructure.database.sources_acim.list_acim_sources()`
  returns **408 `Source`s** across chapters 1–4 (ch1 112, ch2 111, ch3 80, ch4 105).
  "Scale: extract chapters 1–4 into versioned JSONL" is therefore *not* a parser task —
  the sources are already there; what's missing is running the extractor over them and
  committing the output.
- **Runner writes versioned JSONL** (`evaluation/claims/run.py`): header line hashes
  passages + gold, one `ClaimLine` per claim, rejected/failed lines. But it only ever
  targets **gold-covered sources** (`targets = [s for s in sources if s.id in
  gold_source_ids]`), so today it extracts 23 of 408 sources. Scaling to the full
  corpus needs a code path that targets sources with no gold.
- **Gold covers 23 sources**, all T1.1 + T3.2. Attribution distribution: `course` 80,
  `others` 3, **`ego` 0**, `hypothetical` 0. Predicate distribution: `other` 32, `is`
  28, `causes` 13, `expresses` 3, `requires` 3, `contrasts_with` 1, `makes` 1,
  `creates` 1, `undoes` 1.
- **The prompt already documents `ego`** (`prompt.py`: `attribution` is "ego" when the
  view is attributed to the ego). No gold example exercises it — that's the gap, not a
  missing rule.
- **Tooling to reuse as-is:** `near_miss.py` (unmatched-gold diagnostic + no-overlap
  predictions), `tmp/compare_prompts.py` (N-run stdev on the dev set), `score.py`
  (loose/strict/relaxed).

## Steps

Each step is its own commit. As in #4, no step both changes how something is measured
and changes the numbers at once.

### 0. Holdout once, on the current v3.1 prompt (baseline before gold grows)

`python -m evaluation.claims.run --extractor infrastructure.llm.anthropic_proxy:make_extractor --holdout`

- Run the existing holdout (`t1_1_holdout.jsonl`, 5 principles) **once**. This is the
  generalization number the v3 plan deferred; it must be taken **before** the gold set
  grows, or "holdout" stops meaning "never looked at while tuning".
- Record loose/strict/relaxed in this file's results log, tagged `holdout`.
- **Abort condition:** if strict R on the holdout is far below the dev mean (< ~0.35
  vs. dev ~0.53), that's a real generalization failure — stop, do not scale, reopen the
  prompt. Otherwise proceed to step 1. (A modest drop is expected and fine.)
- No code change; commit is the run file + log row.

### 1. Full-corpus extraction run, unscored, versioned

`evaluation/claims/run.py`

- Add a way to extract over **all** `list_acim_sources()`, not just gold-covered
  sources, and write the run without scoring (there's no gold for most of it).
- Shape: a `--all` flag (mutually exclusive with `--holdout`). When set, `targets =
  list(sources)`, `split` records as a new `Split.CORPUS = "corpus"`, `gold` is empty,
  and `score_claims` is skipped — the header's `score` becomes `ScoreReport | None`
  (or a sentinel), `gold_sha256` becomes `""`. Keep the passages hash — it's what lets
  a later run be checked for corpus drift.
- This is the "extract chapters 1–4 into versioned JSONL" deliverable. The file is
  large (≈408 sources × ~4–5 claims) and **is committed** — it's the raw material step
  2 mines and increment #6 resolves entities over.
- Tests (`evaluation/claims/` — this is runner logic, not transport, so it's testable
  directly): with a stub extractor and stub sources, `--all` targets every source,
  writes no `score` header field / a null one, and still writes claim lines. Assert the
  header shape, not scores.
- Watch: `RunHeader.score: ScoreReport` is currently non-optional and `asdict`-ed into
  the header line. Making it optional touches `RunHeader`, `_summary` (which prints
  `report.loose` etc. — guard on `--all`), and `main`. Keep `run()`'s return type
  honest (`report: ScoreReport | None`).
- Output-plus-behavior: this step *does* produce numbers (claim counts) but no *scores*,
  so it can't regress the dev/holdout metrics. Commit separately from step 3 anyway.

### 2. Mine the corpus run for the second gold batch's targets

`evaluation/claims/corpus_survey.py`: `python -m evaluation.claims.corpus_survey <corpus run file>`

A read-only reporting tool over the step-1 run file. It does **not** label anything —
it tells a person *which passages are worth labelling next*, so the second gold batch
is chosen by evidence, not by hand-picking. It answers the two things #5 needs:

- **`ego`-attribution candidates:** list sources where the model already emitted
  `attribution: "ego"` (or `others`), with the evidence span. These are the passages
  most likely to *contain* an ego-attributed view — the human labeller starts here.
  Expected to cluster in chapters 3–4 (ego/perception theology). If the model emitted
  **zero** `ego` across 408 sources, that itself is a finding — record it; it means
  either the corpus slice is thin on ego material or the rule needs a worked example
  (mirror the #4 step-4 approach), and the gold batch should be sourced by a human
  reading ch3–4 directly rather than following the model.
- **Recurring `other` verbs:** tally `verb_phrase` (normalised via `score._normalize`)
  across all claims whose `predicate == "other"`, most frequent first, with source
  counts. This is the direct input to the predicate-list review (step 4): the roadmap
  says grow the predicate list "only once step 3's report shows which `other` verbs
  recur across more passages than T1.1 and T3.2." This report *is* that check.
- Tests: with a stub run file, the `ego`/`others` listing picks the right lines and the
  `other`-verb tally counts by normalised verb across sources. Small and mechanical.

### 3. Second gold batch, including `ego` attribution

`evaluation/claims/gold/` — new file(s); `GOLD_FILES[Split.DEV]` extended

- Using step 2's `ego` candidates, a person hand-labels a new batch of passages from
  **chapters 3–4**, following `SYSTEM_PROMPT` exactly (the labelling rules live only
  there — see the gold README). The batch's explicit goal: **at least a handful of
  genuine `ego`-attribution claims**, since dev currently has zero and the roadmap
  flags that as the gap. Also pick up any `hypothetical` cases encountered.
- New file, e.g. `t3_x.jsonl` / `t4_x.jsonl`, keyed on `source_id` (never principle
  number — OE numbering repeats; see corpus caveats). Same line shape as existing gold
  (subject, verb_phrase, object first).
- Add the new file(s) to `GOLD_FILES[Split.DEV]`. This changes `gold_sha256` on every
  future run, so **this commit is a gold change only** — no prompt change, no re-scored
  claim of improvement in the same commit.
- **Re-baseline:** because the dev gold set just grew, the v3.1 dev numbers no longer
  compare to future runs. Run N=3 on the **unchanged v3.1 prompt** against the enlarged
  dev set and record it as the new baseline (mirrors #4's "re-score is the baseline
  from now on" discipline). Update `tmp/compare_prompts.py` only if it hardcodes gold
  files — it reads `GOLD_FILES[Split.DEV]`, so it picks up the new files for free.
- Loader check: `load_gold_claims` anchors every gold quote against parsed
  `Source.text` and fails loudly if a quote is missing/ambiguous. Run
  `python -m evaluation.claims.run` (dev) after adding the file — an unanchorable label
  fails here, which is the intended guard, not a surprise.
- **Do not touch the holdout file.** Growing dev is fine; the holdout stays the 5
  principles from step 0 so its number keeps meaning something.

### 4. Predicate-list review (decision for the maintainer)

`domain/claims/models.py` (`Predicate` enum) + `src/application/extraction/prompt.py`
if a predicate is added; otherwise a documented no-op.

- Read step 2's recurring-`other`-verb tally. The roadmap's bar: add a predicate only
  for a relationship operator that **recurs across more passages than the current
  T1.1+T3.2 gold** and isn't already covered by an existing predicate + `verb_phrase`.
- The roadmap is deliberately conservative here ("Resist expanding `Predicate` … it is
  a small set of relationship operators, and `verb_phrase` already carries the textual
  nuance … Don't grow it into a taxonomy of overlapping verbs"). Default outcome is
  **no change**, recorded with the tally that justified it.
- **If** a predicate is added: it's a closed-enum change to `Predicate`, so it's also a
  relabelling event — update `SYSTEM_PROMPT`'s predicate list + rule, bump
  `PROMPT_VERSION`, and re-check any gold claim currently labelled `other` that the new
  predicate now covers (relabel it in the same commit). One predicate per commit, with
  the before/after `other`-share in the log.

**Outcome — no predicate added.** The recurring-`other`-verb tally did not surface a
relationship operator recurring across more passages than the T1.1+T3.2 gold and not
already covered by an existing predicate + `verb_phrase`, so `Predicate` is unchanged
(the roadmap's conservative default). The one prompt change in this window
(commit `cac0fa4`, **v3.2**) was *not* a predicate addition — it was a parse-failure
fix: the v3.1 corpus run's 19 failed sources traced to the model putting a mode value
(usually `normative`) in the `predicate` field, which `parse_candidate` rejects and
which fails the whole source. v3.2 adds an explicit rule that `predicate` and `mode`
are separate fields with separate value lists. Measured on those 19 sources, N=3:
failure rate 50.9% (v3.1) → 29.8% (v3.2); residual failures are malformed JSON, which
a prompt rule can't fix. Commit `9cb3245` (repair the model's duplicated claims-header
before parsing) is a parser-robustness fix in the same vein. Neither touches the enum
or the labelling rules, so neither is a relabelling event — the gold set is unchanged
from step 3.

### 5. Run v3.1 (or v3.2 if step 4 changed the prompt) N≥3 on the enlarged dev set

- N≥3 dev runs, identical settings, via `tmp/compare_prompts.py` (or the runner). Use
  the stdev across N as the noise floor exactly as #4 did; don't act on a change smaller
  than it.
- Run `near_miss.py` on one run to confirm no regression of #4's five error types on the
  enlarged set, and to see the new `ego` claims' near-misses.
- Record loose/strict/relaxed for each run and the mean±stdev summary in the log.
- **Decide next** (this is what unblocks #6, entity resolution):
  - If the enlarged dev set is stable and `ego`/`hypothetical` are now represented and
    scored, #5 is done — write the #6 plan (`resolve_entities`), whose gold set is
    mention *pairs* labelled same/different (roadmap evaluation ladder #3).
  - If the `ego` batch tanks precision or exposes a new systematic error, iterate the
    prompt against dev only, one change per run, before declaring #5 done.

## Not in this increment

- **Entity resolution (#6).** #5 deliberately stops at "more labelled claims across more
  attribution/predicate variety." Merging surface forms is the next increment and has
  its own gold set (mention pairs).
- **A database / embeddings.** Still versioned JSONL. The corpus run file (step 1) is
  large but committed JSONL is fine at this scale; move to a store when #7 retrieval
  needs it (roadmap's deferred row).
- **Chapters beyond 4.** The corpus on disk is 1–4; scaling further is a data task, not
  this plan.
- **A second provider.** Worth comparing once #5 is stable (the v3 plan's "not in this
  plan" note still holds); nothing in the runner needs to change for it.

## Results log

| Run | Prompt | Split | Loose P/R | Strict P/R | Relaxed P/R | Notes |
| --- | ------ | ----- | --------- | ---------- | ----------- | ----- |
| 20260923T214245Z | v3.1 | holdout | 0.47 / 0.55 | 0.47 / 0.55 | 0.56 / 0.66 | first holdout, taken before gold grows. Strict R 0.55 ≈ dev mean 0.53 (no generalization failure — well above the ~0.35 abort floor); relaxed R 0.66 vs dev 0.72, the expected modest drop. 0 rejected, 0 failed, 0 polarity/mode/attribution mismatches. **Proceed to step 1.** |
| 20260923T221456Z | v3.1 | corpus | — | — | — | step 1: full-corpus extraction, all 408 sources, unscored. 3984 claims, 3 rejected, 19 failed. Failures = model emitting a mode value in the predicate field; reproducible serially, spread across all chapters. Step 2 survey found 37 ego claims across 15 ch-4 sources (seed for the gold batch). |
| 20260923T224451Z | v3.1 | dev+ego | 0.59 / 0.63 | 0.56 / 0.60 | 0.75 / 0.80 | step 3 re-baseline run 1 of 3, on the **enlarged** dev set (t1_1 + t3_2 + t4_ego). New baseline from here — not comparable to the pre-ego dev numbers. |
| 20260923T224527Z | v3.1 | dev+ego | 0.60 / 0.63 | 0.56 / 0.60 | 0.76 / 0.80 | re-baseline run 2 of 3 |
| 20260923T224600Z | v3.1 | dev+ego | 0.59 / 0.65 | 0.55 / 0.60 | 0.76 / 0.82 | re-baseline run 3 of 3 |
| 20260924T063845Z | v3.2 | dev+ego | 0.59 / 0.63 | 0.54 / 0.58 | 0.74 / 0.79 | step 5 run 1 of 3, v3.2 on the same enlarged dev set. 1 rejected (evidence_ambiguous), **0 failed** (v3.2's predicate/mode fix — cf. v3.1 corpus 19 failed). Mismatches: polarity 2, mode 1, attribution 5. |
| 20260924T063919Z | v3.2 | dev+ego | 0.60 / 0.65 | 0.57 / 0.62 | 0.74 / 0.80 | step 5 run 2 of 3. 1 rejected, 0 failed. Mismatches: polarity 1, mode 2, attribution 3. |
| 20260924T063951Z | v3.2 | dev+ego | 0.65 / 0.70 | 0.62 / 0.67 | 0.79 / 0.85 | step 5 run 3 of 3. 1 rejected, 0 failed. Mismatches: polarity 1, mode 2, attribution 3. |

**Step-5, v3.2, N=3 enlarged dev (mean ± stdev):** loose 0.613±0.036 / 0.661±0.039 ·
strict 0.577±0.038 / 0.622±0.042 · relaxed 0.757±0.032 / **0.816±0.033**. Directly
comparable to the step-3 v3.1 baseline (same gold set). Every mean is at or above the
v3.1 baseline (strict R 0.622 vs 0.595; relaxed R 0.816 vs 0.808), but the stdevs here
(~0.04) are an order of magnitude wider than step 3's (~0.01), so **the apparent gain
is within the noise floor** — v3.2 is not a scored improvement over v3.1 on dev, and
isn't claimed as one. Its measured effect is the parse-failure drop on the corpus run
(step 4 outcome), which dev — already near-zero failures under v3.1 — doesn't exercise:
0 failed sources across all three v3.2 dev runs. `near_miss.py` on run 3
(`20260924T063951Z`): differing-field tally object 20 / subject 16 / predicate 15 /
**mode 2**, plus 3 no-overlap predictions. None of #4's five error types resurface; the
gap is the same subject/object surface-modifier spread that step 3 flagged as
entity-resolution (#6) territory. Attribution near-misses stay low (3–5/run).

**Step-5 decision: #5 is done → write the #6 plan.** The enlarged dev set is stable
across N=3 (strict R exactly consistent in character, relaxed R comfortably above the
old 0.8 gate), `ego` is represented and scored with the model handling it well (only a
handful of attribution near-misses), the predicate list held (step 4 no-op), and the
residual gap is object/subject surface-form differences — exactly what increment #6
(`resolve_entities`, gold set = mention pairs labelled same/different) is for. No new
systematic error was exposed that would send us back to prompt iteration. Next: write
the #6 plan.

**Step-3 re-baseline, v3.1, N=3 enlarged dev (mean ± stdev):** loose 0.591±0.004 / 0.635±0.008 · strict 0.554±0.005 / **0.595±0.000** · relaxed 0.753±0.005 / **0.808±0.011**. This is the new baseline; the pre-ego dev numbers (v3.1 strict R 0.53, relaxed R 0.72) no longer compare. Strict R is exactly stable across runs (same 94 claims match every time). Relaxed R ~0.81 sits above the old 0.8 gate, **but is inflated by the t4_ego claims being seeded from the model's own corpus output** — not a clean generalization signal. Attribution near-misses only 2/run: the model handles `ego` well on this set. The remaining gap is object (24) / subject (20) surface-modifier differences — entity-resolution territory (#6), not more prompting. All #4 error types still clear. No prompt change here, so this run is directly attributable to the gold growth alone.
