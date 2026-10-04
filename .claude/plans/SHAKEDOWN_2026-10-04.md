# Slice-workflow shakedown — 2026-10-04

**Status recorded honestly:** *review and validation agents exercised; full `/slice`
workflow untested.* This run exercised baseline-snapshot capture and scoped read-only
review/validation of a **pre-existing dirty set**, reviewed retrospectively. It did **not**
exercise the mode the design targets — capture-before-implement, then isolate
newly-written changes via `git diff BASELINE_SHA` — because the fidelity work predated the
baseline, so that diff was empty and the slice-vs-background isolation mechanism never ran.
The plan-critic and the before/after baseline were not exercised at all.

## Baseline captured

- `BASELINE_SHA` (`git stash create`): `6271f9242ce02740662c91cf490a0741b07a3a3d`
- `git diff 6271f924` at capture: empty (tree == baseline) — expected.
- Pre-existing dirty set (tracked, `git diff --name-only HEAD 6271f924`):
  `.claude/plans/0034_...md`, `src/application/extraction/extract_claims.py`
- Untracked (`git ls-files --others --exclude-standard`): the 5 workflow files under
  `.claude/` **plus** the 14 fidelity files. The 14 fidelity files were the review scope;
  the 5 workflow files were held out of scope.

Because the fidelity files were in the pre-existing dirty set, they were reviewed
**retrospectively as the slice**, not isolated as new-since-baseline changes.

## Scope reviewed (manifest handed to agents)

**Code reviewed by diff-reviewer (14 files):**
- Tracked edit (1): `src/application/extraction/extract_claims.py`
- New (13): `src/application/extraction/spans.py`;
  `src/domain/derivation/{__init__,identity,models,serialization}.py` (4);
  `evaluation/claims/fidelity/{__init__,fixtures,run,score_fidelity}.py` (4);
  `tests/test_fidelity_{identity,score,serialization}.py` + `tests/test_spans.py` (4).

**Gold data read as fixtures during validation (18 files, NOT code-reviewed):**
`evaluation/claims/fidelity/gold/` holds 9 passages × 2 files each —
`{t1-1-3, t1-1-56, t1-1-65, t2-1-13, t2-3-9, t3-1-5, t3-1-6, t3-4-4, t4-5-10}` ×
`{.jsonl, .derived.json}`. The `.derived.json` sidecars carry each passage's
`derived_status` (all `unauthored` in this run), which is what the dev/report runs key on.
The validator read these; the diff-reviewer did not treat them as code under review.

Out of scope entirely (held out, correctly): `.claude/agents/`, `.claude/commands/`,
`.claude/plans/SLICE_TEMPLATE.md`.

## Reproduction commands + raw results (re-run by the lead, not just relayed)

- `.venv/bin/python -m pytest tests/test_fidelity_identity.py tests/test_fidelity_score.py tests/test_fidelity_serialization.py tests/test_spans.py -q` → `38 passed`
- `.venv/bin/python -m pytest tests -q` → `422 passed`
- `.venv/bin/pyright` → `0 errors, 0 warnings, 0 informations`
- `.venv/bin/python -m evaluation.claims.fidelity.run --oracle` → exit 0; final line
  `oracle OK: every dimension exercised and perfect, abstention honoured`; every applicable
  dimension perfect, non-applicable dimensions correctly `n/a` (not a misleading 100%).
- **Artifact:** that oracle run wrote `evaluation/claims/fidelity/runs/20261004T130844Z.txt`
  (1611 bytes). Correction to the earlier draft of this file: the runner writes an artifact
  after *every* successful invocation (oracle and unauthored dev/report alike), so the
  validator's own runs produced artifacts too — the "no runs/ dir" state only held before
  anything was run from the lead side. The `runs/` dir exists now.
- `.venv/bin/python -m evaluation.claims.fidelity.run` (dev) and `--report`: score nothing
  (`coverage 0 authored`), because all 9 gold passages are `unauthored` stubs — correct for
  a scaffold, not a failure.

## Eval comparison contract — exception taken, stated explicitly

The validator did **not** follow the standard eval comparison contract (baseline artifact +
expected delta + tolerance). It took a **scaffold-specific exception**: the gold passages
are all `"derived_status": "unauthored"` stubs, Stage 2's extractor/deriver path is
deferred, so there is no extraction being measured and no baseline/threshold to compare
against. Proof-of-correctness therefore rests on `tests/test_fidelity_score.py`'s
per-failure-mode assertions and the `--oracle` self-check, not on a metric delta. This
exception is legitimate for a scaffold but must be named, not left implicit.

## Agent verdicts (raw)

- diff-reviewer: `REVIEW: clean` — **disputed, see finding below.**
- slice-validator: `VALIDATION: pass`.

## Open finding — the reviewer should NOT have returned clean

`evaluation/claims/fidelity/score_fidelity.py:390` `_description_core` compares `support`
but not `resolution`. Every other non-reference core (occurrence/requirement/condition,
lines 369/377/386) calls `_status_eq`, whose own docstring (358-362) states that outside
references "a differing resolution status is a different reading." Serialization permits a
DESCRIPTION with `resolution=UNRESOLVED` (it constrains resolution only for
RESOLVED_REFERENCE), so two descriptions differing *only* in resolution match as correct —
a reachable inconsistency between the domain model and the scorer. The reviewer filed this
as a "non-blocking observation" because fixtures don't exercise it; that is insufficient.
**Resolution:** either reject the state explicitly in serialization (forbid non-default
resolution on DESCRIPTION) or compare it in `_description_core` — then this becomes a
closed, tested decision rather than a latent gap.

## Recommended regression checks (from validator; pin behavior, not product decisions)

1. `test_unsupported_resolution_counts_as_unsupported_inference_when_exhaustive` — pins that
   `_unsupported` already counts an incorrect aligned reference when `exhaustive=True`.
   (A pin-down test, not a new product decision — `_unsupported` already does this.)
2. `tests/test_fidelity_run.py`: `test_split_membership_frozen` +
   `test_unauthored_is_skipped_not_scored` — pin the frozen dev/report split and the
   unauthored→skip path (`run.py` is currently untested).
3. `test_mention_absent_from_evidence_gets_no_credit` — low priority; the `first < 0` path
   exists but is unasserted.

## Process fixes this run surfaced

- diff-reviewer instructions must treat **a domain-model invariant the scorer doesn't
  honor as a FINDING, not an observation** — consistency-with-tests is not sufficient when
  the schema admits a state the scorer mis-scores.
- The evidence package (this file) is the required artifact — summaries relayed in chat are
  not evidence; reproduction commands + raw verdicts + artifact paths must be captured.
