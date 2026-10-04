# Fidelity schema integrity and independent layer reporting

## Outcome

The Stage 1 fidelity scaffold distinguishes assertion identity accurately, rejects invalid
or duplicate gold without silently repairing it, and reports literal and derived layers
independently. This addresses the six findings from the full implementation review after
0037; it is a separate follow-up to 0034, not a reopening of the completed matching slice.

## Scope

- Domain: derived proposition signatures, fingerprints, sidecar validation/serialization.
- Evaluation: signature comparison, layer applicability, coverage, and report output.
- Tests: domain boundaries, public scoring paths, and runner behavior.
- No production Claim changes, extraction prompt/version changes, LLM calls, gold authoring,
  authoring CLI, deriver, corpus re-extraction, or graph projection changes.
- Keep 0037's weighted matching and staged description correspondence behavior intact.

This document is a plan only. Record a fresh content baseline and change manifest before
implementation; do not modify other work already dirty at that time. The current staged
0037 slice and untracked 0036 plan remain outside this planning task.

## 1. Distinguish propositions beyond their surface triple

Extend `PropositionSig` and `PropositionSigLine` with explicit `Polarity`, `Mode`, and
`Attribution`, reusing the existing claim enums. These qualifiers participate in both
signature fingerprinting and `_sig_eq`; subject/object keep the existing text-comparison
rules. Null objects remain legitimate.

Qualifiers describe the proposition, independently of the derived entry's literal/
interpreted support or resolution status. Update condition attachments and requirement
reframings consistently. Do not infer missing qualifiers from predicted claims or assume
that every proposition is affirmed, assertive, and attributed to the Course.

Require qualifiers in the serialized signature. Update synthetic fixtures and tests
explicitly. Record this derived-sidecar format as a new schema version; update the nine
empty placeholders without creating annotations. Older nonempty sidecars missing required
qualifiers fail with an actionable schema error rather than acquiring a guessed reading.
No Claim identity or serialization migration is involved.

Acceptance:

- Same triple with different polarity, mode, or attribution has a distinct proposition
  signature and derived annotation fingerprint.
- A condition present on the right evidence but attached to an opposite-polarity
  proposition remains presence TP, fails attachment correctness, and is not fully correct.
- Requirement reframings differing on assertion qualifiers receive no full credit.
- Literal and derived layers stay separately inspectable; object-less propositions work.

## 2. Make missing content distinct from invalid blank content

Replace truthiness-based null encoding in `identity.py` with explicit `is None` handling.
Use an unambiguous canonical encoding with preserved field boundaries and enum values.
Do not change evidence text, normalize it for identity, or include offsets/variant
membership. Preserve ordered semantic tuples; sort only content that is actually a set.

Reject empty/whitespace-only strings for populated semantic fields, including required
content, optional scope/mode when supplied, proposition subjects, and non-null proposition
objects. Keep legitimate absent optional fields and null objects. Apply the same invariants
at domain construction and sidecar loading so direct dataclass inputs cannot bypass them.

Acceptance:

- Null is encoded explicitly and cannot collide with an empty string or field separators.
- Blank semantic content fails construction/loading instead of silently meaning absent.
- Fingerprints remain stable under re-serialization, offset shifts, and variant membership
  changes; substantive qualifier/content changes produce new IDs.
- Signature format changes have an explicit version/migration policy, including dependent
  description IDs and links. For valid in-memory objects, serialization round-trips preserve
  their links; inconsistent or stale graphs fail loudly instead of being partly repaired.

## 3. Enforce uniqueness within coherent gold bundles

Validate uniqueness by recomputed annotation ID in each effective bundle (shared entries
plus that variant). Reject repeats within shared, within a variant, or across shared and
that variant. A single entry may legitimately be present in different alternative variants;
that reuse must remain allowed. Require unique nonblank variant IDs as well.

Enforce this when loading/writing sidecars and when scoring direct `DerivedGold` objects.
Keep prediction duplicates as excess predictions: at most one TP per unique gold entry,
with excess predictions counted as FP. Do not silently deduplicate malformed gold, since
that would conceal authoring mistakes.

Acceptance:

- Duplicate gold fails before scoring and cannot turn two identical predictions into 2 TP.
- With one valid gold entry and two duplicate predictions, the existing 1 TP / 1 FP behavior
  is preserved.
- Sharing an entry across different coherent variants does not fail validation or double
  credit it in a single report.
- Shared/variant overlap and duplicate variant IDs are rejected with clear errors.

## 4. Preserve source ownership across serialization

Validate every shared and variant entry's source against the containing `DerivedGold`
before `from_gold` discards the per-entry source field. Do not rewrite foreign entries as
if they belonged to the passage. Preserve the existing scorer check for direct inputs and
validate every variant, including ones that would not win scoring.

The sidecar can continue to store the source ID once at passage level; duplication on disk
is unnecessary. Consolidate reusable graph invariants at their natural domain boundary
where practical, so loader, writer, and scorer cannot disagree.

Acceptance:

- A foreign shared or variant entry raises on serialization and on direct scoring.
- Valid source IDs and annotation links survive JSON and domain round-trips unchanged.
- Loading never silently fixes source ownership, content, or bundle membership.

## 5. Expose the complete literal accuracy report

Render and persist loose, strict, and relaxed precision/recall with TP/FP/FN, plus polarity,
mode, and attribution mismatch counts. Label strict as the primary literal accuracy tier;
do not present loose success as proof of qualifier fidelity. Keep `score_claims` unchanged.

Store structured run records with explicit applicability and schema version alongside a
readable summary; use the harness's `runs/` directory. Existing text artifacts remain
historical evidence, not inputs that must be rewritten. Define zero-denominator display
explicitly: unavailable precision/recall is `n/a`, while real FP/FN counts stay visible.

Acceptance:

- A polarity-flipped oracle claim reports loose TP=1 and strict TP=0, FP=1, FN=1,
  polarity_mismatches=1 in both readable and structured output.
- Mode and attribution failures are equally observable; relaxed remains a diagnostic tier.
- No authored literal items and no predictions yields `n/a`, not misleading 0% or 100%.
- Authored empty literal gold with an invented prediction reports the FP and precision 0;
  it must not disappear behind `n/a`.

## 6. Honor independent authoring and prediction availability

Track literal and derived coverage separately using their existing authoring statuses.
Only load and score a layer if its gold is authored and predictions for that layer are
actually available. Represent unavailable results explicitly in typed runner reports,
rather than constructing an empty prediction and treating it as a measured model output.

An explicitly supplied empty prediction is a real result and can produce FN; absent
prediction input is `not run`. An unauthored gold layer is `unauthored`, irrespective of
whether its placeholder file is empty. Authored empty gold is a legitimate negative target.
Keep these three cases distinct in both structured and readable output.

Without extractor/deriver wiring or offline prediction input, normal Stage 1 runs report
coverage/applicability only. The oracle continues to supply actual synthetic predictions.
This plan does not introduce any LLM/provider wiring. If offline prediction input is added,
keep it a narrow, typed local-file interface and include it in the implementation manifest.

Acceptance:

- Exercise all four literal/derived authoring-status combinations: each layer's coverage,
  loading, and applicability are independent.
- Authored literal + unauthored derived can produce literal scores when literal predictions
  are supplied; the reverse can produce derived scores without reading literal placeholders.
- No prediction available never becomes an artificial all-missing-model benchmark result.
- Invalid unauthored layer files are not consumed as gold for scoring; authored invalid files
  fail loudly. Tests observe loader calls as well as report text.
- Default dev/report runs show 0/5 and 0/4 authored for both layers until authoring occurs.
  No reserved-report tuning is performed.

## Implementation order and likely files

1. Domain signature/identity validation and schema versioning:
   `src/domain/derivation/{models,identity,serialization}.py`.
2. Shared source/bundle invariants and scorer signature comparison:
   `evaluation/claims/fidelity/score_fidelity.py` plus a domain validation module only if
   needed to avoid duplicated invariants.
3. Update `evaluation/claims/fidelity/fixtures.py` and empty gold sidecars explicitly.
4. Independent layer reports and complete literal metrics:
   `evaluation/claims/fidelity/run.py`; typed run serialization if needed.
5. Extend `tests/test_fidelity_{identity,serialization,score}.py`; add
   `tests/test_fidelity_run.py` for coverage, loading, rendering, and artifact round-trips.

Validate the domain changes before runner changes; retain oracle and weighted-assignment
regressions throughout. New IDs require consistent description links, not independent
recomputation of target IDs while retaining old pointers.

## Evidence and verification

The evidence is deterministic schema/scorer/runner behavior, not extraction accuracy.
Capture a fresh baseline oracle artifact under unchanged synthetic conditions before
implementation. After updating schema/fixtures, compare semantic counts, not fingerprint
bytes expected to change with the versioned signature. Expected score/count delta is zero
on valid self-predictions; tolerance is zero. The negative fixtures above must fail or score
as specified, rather than merely allowing a green oracle to stand in for coverage.

```sh
.venv/bin/python -m pytest tests/test_fidelity_identity.py tests/test_fidelity_serialization.py tests/test_fidelity_score.py tests/test_fidelity_run.py -q
.venv/bin/python -m pytest tests -q
.venv/bin/pyright
.venv/bin/python -m evaluation.claims.fidelity.run --oracle
.venv/bin/python -m evaluation.claims.fidelity.run
```

Only root tests are required unless implementation adds an app adapter change. Avoid
provider calls and reserved-report measurement while developing these invariants.

## Definition of done

- All six findings have regression checks on their public construction/loading/scoring or
  runner paths; synthetic self-prediction remains perfect on applicable dimensions.
- No duplicate-gold double credit, source rewriting, ambiguous proposition attachment, or
  fabricated missing-prediction score remains reachable through a supported API.
- Full declared tests and pyright pass; no tool dict returns or nonempty init files added.
- Independent review and validation of the final implementation return clean/pass if this
  plan is executed through `/slice`; bounded correction/review budget is declared then.
- Changes and evidence are staged together; commit remains the user's action.
- Gold authoring, authoring CLI, Stage 2, and joint cross-kind graph optimization stay
  deferred. A successful scaffold run is not claimed as benchmark extraction performance.
