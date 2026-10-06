# Slice contract: fidelity schema integrity and independent layer reporting

Execution wrapper (SLICE_TEMPLATE shape) for the six findings specified in
[`0038_fidelity-schema-integrity-and-layer-reporting.md`](0038_fidelity-schema-integrity-and-layer-reporting.md).
0038 holds the detailed per-finding behavior and acceptance criteria; this file holds the
baseline, change manifest, declared evidence, and done-gate for the `/slice` run. Do not
restate 0038's findings here — read it alongside this.

## Outcome

The Stage 1 fidelity scaffold distinguishes assertion identity accurately (polarity/mode/
attribution on propositions), rejects invalid or duplicate gold without silently repairing
it, preserves source ownership across serialization, and reports literal and derived layers
independently — with the complete literal tier (loose/strict/relaxed + mismatch counts) and
three distinct coverage states (unauthored / not-run / authored-empty).

## Layers touched

- **Domain** (`src/domain/derivation/{models,identity,serialization}.py`) — the signature
  qualifiers (finding 1), explicit-null canonical encoding + blank-field rejection
  (finding 2), bundle uniqueness + source-ownership invariants (findings 3, 4), schema
  version. This is where identity/validation live; the plan forbids leaking them elsewhere.
- **Evaluation** (`evaluation/claims/fidelity/{score_fidelity,run,fixtures}.py`) —
  `_sig_eq` qualifier comparison (finding 1), the complete literal report + the **typed
  structured run record** (findings 5, 6), fixture updates for the versioned signature. The
  run record is a **pydantic `BaseModel` / frozen dataclass, never a `dict`** (CLAUDE.md
  no-dict rule), defined **eval-local** under `evaluation/claims/fidelity/` (it is a run
  artifact, not a domain entity — it does not belong in `domain/`). It is persisted as a
  JSON sibling of the existing `.txt` under `evaluation/claims/fidelity/runs/`
  (`<run_id>.json` alongside `<run_id>.txt`); the readable `.txt` summary stays.
- **Bundle/source invariants (single home, finding 3, 4):** uniqueness-by-recomputed-id
  within each effective bundle and per-entry source ownership are defined **once in
  `src/domain/derivation/`** and *called* by the loader/writer (`serialization.py`) and the
  scorer (`score_fidelity.py`) — not re-implemented in each, so loader/writer/scorer cannot
  disagree. `score_fidelity._check_sources`'s existing direct-input source check is
  preserved (finding 4 says keep it) and delegates to the shared guard; the shared
  ownership check validates **every variant, including ones that would not win scoring**.
- **Gold sidecars** (`evaluation/claims/fidelity/gold/*.derived.json`) — add the new
  `schema_version` field to the nine empty placeholders only; no annotations authored
  (plan scope).
- **Tests** (`tests/test_fidelity_{identity,serialization,score}.py`, new
  `tests/test_fidelity_run.py`) — the negative fixtures and layer-independence checks each
  finding's acceptance criteria demand.

**Schema version mechanism (findings 1, 2):** `DerivedGoldFile` gains a required
`schema_version: int` field with an explicit current value (bumped from the implicit v1 —
new value stated in code). A sidecar **missing `schema_version`, or at an older version,
that carries nonempty entries** fails load with an actionable schema error (fail-loud, not a
guessed reading); an empty placeholder is updated in place to the new version. A declared F2
negative fixture asserts this old-version/missing-qualifier load raises clearly.

No production `Claim` change, no extraction prompt/version change, no LLM/provider wiring,
no gold authoring, no authoring CLI/deriver, no corpus re-extraction, no graph projection.

## Baseline (recorded BEFORE implementation)

- **BASELINE_SHA:** `d314ff5` (clean tree — `git stash create` printed nothing, so HEAD).
- **Pre-existing dirty set:** empty (tracked-dirty none, untracked none). Every file this
  slice touches is therefore in scope.
- **Scratch dir:** `/var/folders/8f/w60jmnmd4ql06l5wftw9_rwr0000gn/T/slice-0038-1791143540/`
  — holds `BASELINE_SHA`, `tracked_dirty.txt`, `untracked.txt`, `baseline_oracle.txt`.
- **Baseline eval artifact (fidelity harness):**
  `evaluation/claims/fidelity/runs/20261004T195226Z.txt` — oracle perfect on every
  applicable dimension under unchanged synthetic conditions. The delta expectation for the
  post-change oracle is **zero** on valid self-predictions (compare semantic counts, not
  fingerprint bytes, which change with the versioned signature).

## Change manifest (vs BASELINE_SHA d314ff5)

- **Tracked edits:**
  - `src/domain/derivation/models.py` — qualifiers on `PropositionSig`; `DerivedValidationError`;
    `_reject_blank` + `__post_init__` blank-field rejection on `PropositionSig`/`DerivedEntry`.
  - `src/domain/derivation/identity.py` — presence-tagged null encoding (`_ABSENT`/`_PRESENT`,
    no truthiness collision); proposition qualifiers in `_sig`.
  - `src/domain/derivation/serialization.py` — `SCHEMA_VERSION=2`; `schema_version` field +
    fail-loud validator; `PropositionSigLine` qualifiers; `check_gold` on `from_gold`/`to_gold`.
  - `evaluation/claims/fidelity/score_fidelity.py` — `_check_sources` delegates to `check_gold`;
    `_sig_eq` compares qualifiers.
  - `evaluation/claims/fidelity/run.py` — `run_split` returns a typed `RunRecord` with per-layer
    three-state coverage, no fabricated empty prediction; persists `.json` + `.txt`.
  - `evaluation/claims/fidelity/fixtures.py` — qualifiers on the two `PropositionSig` fixtures.
  - `evaluation/claims/fidelity/gold/*.derived.json` (nine) — `schema_version: 2` added.
  - `tests/test_fidelity_identity.py` — F1 fingerprint-on-qualifier, F2 null/blank/collision.
  - `tests/test_fidelity_serialization.py` — F2 schema-version fail-loud + load-time blank,
    F4 foreign-entry (incl. non-winning variant); qualifier/`schema_version` fixups.
  - `tests/test_fidelity_score.py` — F1 opposite-polarity attachment, F3 bundle uniqueness
    (dup gold, dup predictions stay 1TP/1FP, cross-variant reuse, dup variant id); message fixups.
- **New / untracked files:**
  - `src/domain/derivation/validation.py` — the single home for `check_sources`/
    `check_bundle_uniqueness`/`check_gold`, called by loader, writer, and scorer.
  - `evaluation/claims/fidelity/report.py` — the typed `RunRecord`/`SourceRun`/`LiteralReport`/
    `DerivedReport` pydantic models (no dict) + readable rendering.
  - `tests/test_fidelity_run.py` — F5 literal-tier divergence over all three qualifier axes
    (polarity/mode/attribution, readable + JSON), F6 independent layer states + loader/scorer spy.
  - `.claude/plans/0039_fidelity-schema-integrity-slice-contract.md` — this contract.
  - `evaluation/claims/fidelity/runs/20261004T195226Z.txt` — baseline oracle artifact.
  - `evaluation/claims/fidelity/runs/20261004T201543Z.{txt,json}` — final oracle(txt)+dev(json/txt).

## Evidence (declared BEFORE implementation)

Per 0038 § Evidence/Verification: the proof is **deterministic schema/scorer/runner
behavior**, not extraction accuracy. Evidence type = **targeted tests + a deterministic eval
(oracle + dev) run**, since there is no model in the loop.

- `.venv/bin/python -m pytest tests/test_fidelity_identity.py
  tests/test_fidelity_serialization.py tests/test_fidelity_score.py
  tests/test_fidelity_run.py -q` — every finding has at least one **negative fixture** that
  must fail-or-score-as-specified (not merely a green oracle standing in for coverage).

  **Two distinct polarity axes — neither substitutes for the other** (the polarity-across-a-
  hop trap): the DERIVED `PropositionSig` polarity/mode/attribution flow through
  `identity._sig` + `_sig_eq` (F1); the LITERAL `Claim` polarity is scored by the unchanged
  `score_claims` (F5). Different code paths, each needs its own biting fixture.

  - **F1 (derived signature identity):** two entries identical except for a qualifier
    (polarity/mode/attribution) on their `attaches_to`/`reframed_proposition` must have (a)
    **distinct `compute_annotation_id`** — asserted directly, so a change that updates
    `_sig_eq` but forgets `identity._sig` still fails — AND (b) distinct `_sig_eq`. A
    condition present on the right evidence but attached to an opposite-polarity proposition
    is presence-TP, fails attachment correctness, and is not fully-correct.
  - **F2 (null vs blank vs separator):** two separate assertions — (a) blank/whitespace-only
    semantic content is **rejected at construction AND at sidecar load**; (b) explicit-null
    encoding **cannot collide** with an empty string or with the `_SEPARATOR`/`_NULL`
    sentinel strings: an entry whose field is literally the sentinel/separator string, and
    empty-string-vs-None, produce **distinct** fingerprints. Fingerprint stable under
    re-serialization, offset shift, and variant-membership change.
  - **F3 (bundle uniqueness):** duplicate gold (within shared, within a variant, or across
    shared+variant) fails **before scoring**; 1 valid gold + 2 duplicate predictions still
    scores 1 TP / 1 FP; an entry legitimately shared across coherent variants is **not**
    rejected and **not** double-credited; duplicate variant ids rejected.
  - **F4 (source ownership, every variant):** a foreign shared OR variant entry raises on
    serialization and on direct scoring. The foreign-variant fixture uses a variant that
    would **not** win scoring, proving non-winning variants are validated too.
  - **F5 (literal tier divergence):** a polarity-flipped predicted claim → loose TP=1,
    strict TP=0/FP=1/FN=1, polarity_mismatches=1, in the readable `.txt` **and** the typed
    JSON run record. Mode/attribution failures equally observable. `n/a` (no items) stays
    distinct from a real FP/precision-0. A green oracle cannot show this (self-prediction is
    perfect on every tier) — it must be its own fixture.
  - **F6 (independent layer coverage):** all four literal/derived authoring-status
    combinations load/score independently; a **not-run** (no prediction supplied) layer is
    never turned into an artificial all-missing benchmark result, and stays distinct from
    **unauthored** and **authored-empty**. Mechanism for "loader calls observed": the test
    **spies on `_load_gold`/`load_gold_claims`** (monkeypatch) and asserts the loader for an
    unauthored layer is **not invoked** — not merely that the final report text looks right.
- `.venv/bin/python -m pytest tests -q` — full root suite stays green.
- `.venv/bin/pyright` — zero errors.
- `.venv/bin/python -m evaluation.claims.fidelity.run --oracle` — perfect on applicable
  dimensions, zero count delta vs baseline artifact (fingerprint bytes may differ).
- `.venv/bin/python -m evaluation.claims.fidelity.run` — dev split reports coverage/
  applicability only (0/5 authored both layers); no reserved-report run while developing.

## Definition of done

0038 § Definition of done, verbatim, gated by the `/slice` completion gate: final
diff-reviewer `REVIEW: clean` and slice-validator `VALIDATION: pass` (pyright + the declared
suites + no-dict + empty-init). Gold authoring, Stage 2, authoring CLI, and joint
cross-kind graph optimization stay deferred. A green oracle is not claimed as benchmark
extraction performance. **Correction/review budget:** one implement pass, one fix pass, one
re-review — then present done or explicitly incomplete.
