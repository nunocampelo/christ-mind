# Slice contract: fidelity-gold authoring tool (tool + tests + write path)

Execution wrapper (SLICE_TEMPLATE shape) for the tool portion of
[`0040_fidelity-gold-authoring-tool-and-first-passage.md`](0040_fidelity-gold-authoring-tool-and-first-passage.md).
0040 holds the Stage-1b rationale and the full-passage goal; this slice delivers **only the
authoring tool, its tests, and the derived-sidecar + literal-`.jsonl` write path** — not the
interactive authoring of real `t3-1-5` gold (a separate human-in-the-loop step, per 0040's
agreed sequencing).

> **Internal/library slice (not independently user-demonstrable) — user-agreed.** This slice
> delivers a typed core (`write_gold`) with **no command the user can run** to watch it behave;
> its outcome is observable only through the test suite. Per the user-demonstrable rule
> (SLICE_TEMPLATE § Evidence), that makes it an internal slice, which is acceptable **only
> because the user explicitly chose this split** ("keep the slice split" — core now,
> interactive front-end as the next slice). The runnable `python -m ...author --source t3-1-5`
> front-end is the named follow-up that makes the behavior user-testable end-to-end. Recorded
> here so the slice is not mislabeled as a complete vertical slice.

## Outcome

An authoring module, `evaluation/claims/fidelity/author.py`, can take a drafted set of literal
+ derived entries for one passage, validate each entry's evidence span against the real source
text, and write a well-formed `<source_id>.derived.json` sidecar plus a literal `<id>.jsonl`
that the existing loaders (`DerivedGoldFile.to_gold`, `load_gold_claims`) read back unchanged —
rejecting a bad span, a foreign source, or a malformed bundle loudly rather than writing it.

## Layers touched

- **Evaluation** (`evaluation/claims/fidelity/author.py`, new) — the authoring/write
  orchestration: build `DerivedGold` + literal `CandidateClaim` lines from drafted input,
  span-validate via the existing `validate_span`, serialize through the existing
  `DerivedGoldFile.from_gold`. This is an eval-harness tool, so it belongs under `evaluation/`,
  not `domain/`/`application/` (mirrors `run.py`, which already lives there).

  **Public signature is typed, no loose dict (change 4).** `write_gold(...)` accepts typed
  domain objects — a `DerivedGold` plus a sequence of literal `CandidateClaim`s (the
  quote-based, offset-free shape, since the author has no offsets yet; `extract_claims.py:34`).
  A `dict` appears only as a transient at the one serialization boundary the loader requires
  (the literal `.jsonl` line), never in the tool's public signature.

  **Literal `.jsonl` writer shape — pinned (change 2).** The literal line is written as a
  **`ClaimLine.from_claim(...).model_dump()` superset with `source_id` present**, matching what
  `load_gold_claims` reads: `parse_candidate` (`extract_claims.py:45`) consumes
  subject/verb_phrase/object/predicate/polarity/mode/attribution/evidence and ignores extras,
  and `load_gold_claims` reads `record["source_id"]` separately (`gold.py:33`). The written
  offsets (`evidence_start/end`) are recomputed by `anchor_claim` on readback, so they are
  advisory on disk. Because the tool has only a `CandidateClaim` (no offsets) at author time,
  it builds the line from the candidate's fields + `source_id` directly rather than
  constructing a `Claim`; the test asserts the written line equals that one chosen serializer's
  output byte-for-byte, not merely that `load_gold_claims` succeeds.

  **Source text comes from `list_acim_sources()` (change 5).** Span validation anchors against
  the ACIM corpus via `list_acim_sources()` + a local `{s.id: s}` map — **not** `source_for_id`
  (backed by the generic `list_sources()`); anchoring against the wrong corpus would silently
  mis-point or fail.
- **Tests** (`tests/test_fidelity_author.py`, new) — the span-rejection, write/read round-trip,
  and "never writes an unvalidated/foreign entry" invariants.

No domain change (reuses `domain/derivation/*`, `domain/claims/*` as-is), no
`application/extraction` change (reuses `validate_span`, `parse_candidate` unchanged), no new
`Claim` field, no interactive `input()` loop in this slice (deferred — see Remaining
limitations), no real gold authored, no LLM/deriver, no corpus re-extraction.

## Baseline (recorded BEFORE implementation)

- **BASELINE_SHA:** `5dfd024` (clean tree — `git stash create` printed nothing, so HEAD).
- **Pre-existing dirty set (out of scope):**
  - `.claude/plans/0040_fidelity-gold-authoring-tool-and-first-passage.md` (the plan, already
    written)
  - `evaluation/claims/fidelity/runs/20261006T200617Z.txt` (a stray oracle run from earlier
    state-checking; untouched by this slice)
- **Scratch dir:** `/tmp/slice-0040-1791317935/` — holds `BASELINE_SHA`, `tracked_dirty.txt`
  (empty), `untracked.txt`, and copies of the untracked files.
- **Baseline eval artifact:** not an eval-delta slice. The tool's correctness is proven by
  targeted tests + a write/read round-trip, not by a metric moving. **The oracle is a narrow
  guard only (change 5a):** `run.py` never calls `load_gold_claims` and never reads the
  `.jsonl` for scoring (the literal layer is `NOT_RUN` at Stage 1 — `run.py:_source_run`), so a
  green oracle proves only that the derived-sidecar schema/scorer path is undisturbed. The
  literal `.jsonl` round-trip the slice's main outcome rests on is proven **solely by the
  slice's own test** over real `list_acim_sources()` text — a first-class, non-optional
  acceptance criterion, not something the oracle covers.
- **Real gold sidecars untouched (change 1):** the nine `evaluation/claims/fidelity/gold/
  *.derived.json` placeholders (incl. `t3-1-5.derived.json`) are **not** in the pre-existing
  dirty set and are **not** in this slice's change manifest — editing them would be out of
  scope. The real `t3-1-5` gold is authored in the separate human session, not here. 0040's
  §Files/§Verification are superseded by this contract for scope (see 0040 header pointer).

## Change manifest (vs BASELINE_SHA 5dfd024)

- **Tracked edits:** none.
- **New / untracked files:**
  - `evaluation/claims/fidelity/author.py` — `write_gold` + helpers (the validated write path);
    docstring notes IO-atomicity-between-two-writes is out of scope (validator rec 3).
  - `tests/test_fidelity_author.py` — 11 tests (derived + live-corpus round-trip, byte-identical
    line, 7 reject cases incl. ambiguous-literal, mid-bundle partial-write).
  - `.claude/plans/0041_fidelity-authoring-tool-slice-contract.md` — this contract.
  - `.claude/plans/0040_...md` — parent design doc (pre-existing in dirty set; header pointer
    added reconciling scope — not a slice code deliverable).

## Evidence (declared BEFORE implementation)

- **Type:** targeted tests (the outcome is deterministic write/validate/read behavior; no model
  in the loop, so no eval delta).
- **Reproduce with:**
  - `.venv/bin/python -m pytest tests/test_fidelity_author.py -q`
  - `.venv/bin/python -m pytest tests -q` (full root suite stays green)
  - `.venv/bin/pyright` (zero errors)
  - `.venv/bin/python -m evaluation.claims.fidelity.run --oracle` (unchanged, still perfect —
    regression guard that the write path didn't disturb the scorer/loader)
- **Test suites to run:** root `tests/` only. The slice touches `evaluation/` + `tests/`; no
  app adapter (`apps/*`) is involved, so no app suite applies.
- **Expected behavior (happy path):** given a drafted `DerivedGold` + literal candidate lines
  for a passage whose spans are real unique substrings of the source, `author.write_gold(...)`
  writes `<id>.derived.json` and `<id>.jsonl`; reloading via `DerivedGoldFile.model_validate_json(...).to_gold()`
  and `load_gold_claims(...)` returns gold equal in content to what was authored (annotation
  ids recomputed, literal claims anchored), with `literal_status`/`derived_status` = `AUTHORED`.
- **Relevant failure cases (must be exercised, not happy-path-only):**
  - A derived entry whose `evidence` quote is **not** in the source → raises
    `EvidenceNotFoundError` (distinct from ambiguous); nothing is written.
  - A derived entry whose quote occurs **twice** → raises `AmbiguousEvidenceError`; nothing
    written. (The missing-vs-ambiguous distinction is surfaced, not collapsed.)
  - A **foreign** entry (source_id ≠ the passage) → `check_gold`/`check_sources` raises
    `DerivedValidationError` on write; nothing written.
  - A **duplicate** entry within a bundle → `check_bundle_uniqueness` raises on write.
  - A literal candidate line whose `evidence` isn't a unique substring → `anchor_claim`/
    `load_gold_claims` surfaces it on readback (the tool writes the quote; anchoring is where
    a bad literal span bites, exactly as production gold does).
  - **Partial-write guard (mid-bundle, change 3):** a bundle whose **first entry is valid and a
    later entry fails** (`validate_span` or `check_gold`) leaves **both** files absent on disk
    afterward — tested explicitly, not just declared as a property. **Mechanism:** validate
    everything first (all spans → build `DerivedGold` → `from_gold`/`check_gold`) **before any
    `write_text`**. The two writes (derived sidecar + literal `.jsonl`) are separate, so the
    guard covers the window between them: the derived sidecar and the `.jsonl` are written only
    after *all* validation of *both* layers has passed, so a validation failure never leaves one
    file written and the other missing.

## Acceptance criteria

- **Derived round-trip:** `to_gold()` of the written sidecar equals the authored `DerivedGold`
  by content — recomputed annotation ids match (not fingerprint bytes).
- **Literal round-trip (first-class, change 5b):** over real `list_acim_sources()` text,
  `load_gold_claims` of the written `.jsonl` returns the authored literal claims, anchored.
- **Literal line shape is byte-identical (change 2):** the written `.jsonl` line equals the one
  chosen serializer's output byte-for-byte (`ClaimLine`-superset + `source_id`), not merely
  "loads without error".
- **Mid-bundle partial-write (change 3):** a valid-then-invalid bundle leaves **both** files
  absent on disk.
- Each failure case above raises the **named** exception type and writes nothing.
- The tool never emits a derived entry whose span wasn't validated, nor a sidecar that
  `check_gold` would reject.
- `literal_status`/`derived_status` on the written sidecar are `AUTHORED`.
- Oracle run unchanged (narrow guard per Baseline); full suite + pyright green; no-dict +
  empty-`__init__` hold.

## Known-trap regression checks

- **No-dict rule:** the tool's drafted-input shape and any return type are typed
  (dataclass/pydantic), never a bare `dict` — asserted by pyright + reviewer.
- **Loader/writer agreement (0038 finding 3/4):** the write path calls the **shared**
  `check_gold` (`domain/derivation/validation.py`), not a re-implemented check, so writer and
  scorer can't disagree. A foreign-source and a duplicate-bundle test lock this in.
- **Presence-tagged identity (0038 finding 2):** round-trip equality is asserted by recomputed
  annotation id, not fingerprint bytes — consistent with how 0039 proved its oracle.

## Definition of done

- [ ] Acceptance criteria met, shown by the declared tests.
- [ ] Evidence proves the outcome (validator's reasoning, not just a green run).
- [ ] All listed failure cases exercised.
- [ ] `.venv/bin/pyright` clean; `tests/` green; oracle unchanged.
- [ ] no-`dict` and empty-`__init__` hold.
- [ ] Final pass `REVIEW: clean` + `VALIDATION: pass`. One implement / one fix / one re-review.
- [ ] Commit left to the user (no-self-commit).

## Remaining limitations

- **No interactive `input()` loop in this slice.** The tool exposes a typed, testable
  write/validate API (`write_gold(...)`); the human-driven draft-then-adjudicate CLI front-end
  that calls it — the `python -m ...author --source t3-1-5` entrypoint with prompts and the
  reveal phase — is built next, on top of this proven core, so the judgement-heavy part isn't
  entangled with the slice's automated evidence. (0040 §Sequencing anticipated this split.)
- **No real `t3-1-5` gold authored** — produced in the follow-on interactive session.
- Reserved report split untouched; Stage 2 deriver deferred.
