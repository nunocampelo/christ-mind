# Slice contract: interactive fidelity-authoring front-end

The user-demonstrable front-end on top of the `write_gold` core from
[`0041`](0041_fidelity-authoring-tool-slice-contract.md) (committed `353ad53`). Where 0041
was an internal/library slice, **this slice is independently user-testable**: the evidence of
record is a command the user runs and drives.

## Outcome

Running `python -m evaluation.claims.fidelity.author --source t3-1-5` loads the drafted
entries I (the assistant) prepared, walks the user through **each entry one at a time** —
showing the entry and the exact source span it anchors to — lets the user **accept / skip /
quit**, shows the already-extracted literal claims as a reference, and on finish writes the
accepted entries as validated gold via the existing `write_gold`. A bad span or malformed
accepted set is still rejected loudly (0041's guarantees are preserved, not bypassed).

## User-demonstrable test (named first, per SLICE_TEMPLATE § Evidence)

- **Command the user runs:** `.venv/bin/python -m evaluation.claims.fidelity.author --source t3-1-5`
  (reading drafts from `evaluation/claims/fidelity/drafts/t3-1-5.draft.json`, which I author).
  The user sees each entry + its anchored span, types `a`/`s`/`q`, and at the end sees the
  written file paths or a loud rejection. This is the surface the user exercises directly —
  not a test file.
- A `--dry-run` flag shows the adjudication + validation **without writing** (so the user can
  rehearse safely).

## Layers touched

- **Evaluation** (`evaluation/claims/fidelity/author.py`, edit) — add the front-end **on top
  of** `write_gold`, split into:
  - a **pure, testable** `adjudicate(drafts, decisions) -> AdjudicationResult` with **no I/O**:
    - **Entry identity + order (change 3):** it walks entries in a **stable deterministic
      order** — `shared` first, then each variant's entries in declared order — and binds each
      decision to an entry by that entry's recomputed `annotation_id` (literal candidates walked
      after, keyed by their `(subject, predicate, object, evidence)` identity). The
      `AdjudicationResult` carries the accepted `DerivedGold` (status flipped to **`AUTHORED`**,
      change 1), the accepted literal `CandidateClaim`s, and a per-entry record for
      `adjudication_history`.
    - **Accepted subset re-validated (change 3):** the accepted gold is rebuilt and run through
      `check_gold` *inside* `adjudicate`, so a skip that breaks a `describes`-link target or a
      variant bundle is rejected loudly, not written. (Accepting a variant entry while skipping
      its shared sibling, etc.)
    - **Literal adjudication (change 4):** literal candidates are adjudicated per-entry too
      (accept/skip each), not all-or-nothing.
    - **Zero accepted (change 5, user-decided):** if nothing is accepted, `adjudicate` returns a
      result flagged "nothing to write" — the layer stays **UNAUTHORED**, no empty-but-AUTHORED
      gold is fabricated. Authoring an intentional empty negative-target gold (0038 finding 6)
      is deliberately **not** supported by this tool.
  - a thin `main(argv)` / `input()`+`print()` shell that reads the drafts file, renders each
    entry with its anchored span, collects keystrokes, and calls `adjudicate` then `write_gold`.
    The shell is the only part that touches the TTY, kept minimal (mirrors `run.py`'s `main`
    shape). **Anchor parity (change 7):** the render-time span preview and `write_gold`'s
    write-time validation both anchor through the **same** `list_acim_sources()` map (0041
    change 5), so the preview can never show a green span the write then rejects for an
    anchoring reason — a rejection at write can only come from the accepted *set* being
    invalid, never from a divergent anchor path.
- **Drafts fixture** (`evaluation/claims/fidelity/drafts/t3-1-5.draft.json`, new) — my drafted
  entries for `t3-1-5`. **On-disk shape (change 4):** a composite envelope
  `{"derived": <DerivedGoldFile object>, "literal": [<candidate records>]}` — the two halves
  `write_gold` needs. The `derived` half is parsed by `DerivedGoldFile.model_validate`, the
  `literal` records each by `parse_candidate` (`extract_claims.py:45`). This composite envelope
  is the *one* new shape (declared here, not a bespoke per-entry format); each half still reuses
  the existing model/parser. **A draft is a fully-valid, fully-anchored candidate set, not loose
  scratch (change 2):** `DerivedGoldFile` runs the complete `check_gold` suite + describes-link
  + per-kind validators *at load* (`serialization.py:243-297`), so a draft with a dangling
  `describes`, foreign source, duplicate, or missing per-kind field **fails at load with the
  named error** — "draft" means "pre-validated set the user only accepts/skips," not an
  in-progress file. **Status (change 1):** the `derived` half is stored `UNAUTHORED`;
  `adjudicate` is what flips the *accepted* gold to `AUTHORED` (`write_gold`/`from_gold` copy
  status verbatim — `serialization.py:270` — they do not flip it).
- **Tests** (`tests/test_fidelity_author.py`, edit) — `adjudicate` unit tests driving scripted
  decisions; a shell test feeding stdin and asserting files written / `--dry-run` writes
  nothing.

No change to `write_gold`'s core logic (reused as-is), no `domain`/`application` change, no new
`Claim` field, no LLM/deriver, no corpus re-extraction. The **real doctrinal gold is still not
committed by this slice** — the drafts fixture is illustrative input the user adjudicates; a
genuine authored `t3-1-5.derived.json` is produced only when the user actually runs the tool
and accepts entries, which is the point of the slice (and left to the user, like a commit).

## Baseline (recorded BEFORE implementation)

- **BASELINE_SHA:** `353ad53` (clean tree — `git stash create` printed nothing, so HEAD).
- **Pre-existing dirty set:** empty (no tracked-dirty, no untracked). Everything this slice
  touches is in scope.
- **Scratch dir:** `/tmp/slice-0042-1791319166/` — holds `BASELINE_SHA`, empty
  `tracked_dirty.txt`/`untracked.txt`.
- **Baseline eval artifact:** not an eval-delta slice; proof is the user-run command +
  targeted tests. The fidelity oracle must stay green as a regression guard.

## Change manifest (vs BASELINE_SHA 353ad53)

- **Tracked edits:**
  - `evaluation/claims/fidelity/author.py` — add `Decision`/`DraftFile`/`AdjudicationResult`,
    `load_draft`, pure `adjudicate`, `_render_entry`, `_run_interactive` shell, `main`;
    refactored validation into shared `_validate_and_render` so `write_gold` core logic is
    unchanged and `--dry-run` validates on the same path.
  - `tests/test_fidelity_author.py` — 17 new tests (adjudicate accept/skip/zero/default/literal,
    per-layer-independent status, stranded-describes-link + bad-span-through-adjudicate
    rejection, draft missing/malformed/committed round-trip, shell quit-derived/quit-literal/
    accept-all/unknown-key-skip, main unknown-source).
  - **Review fix:** per-layer status set independently (derived vs literal), not from one flag;
    `adjudicate` docstring corrected (validation is caller-side, not in-adjudicate).
- **New / untracked files:**
  - `evaluation/claims/fidelity/drafts/t3-1-5.draft.json` — the drafted entries fixture
    (composite `{derived, literal}` envelope, UNAUTHORED).
  - `.claude/plans/0042_fidelity-authoring-interactive-frontend-slice.md` — this contract.

## Evidence (declared BEFORE implementation)

- **Type:** user-run command (primary) + targeted tests (the pure `adjudicate` + the shell).
- **Reproduce with:**
  - `.venv/bin/python -m evaluation.claims.fidelity.author --source t3-1-5 --dry-run` — the
    user watches each entry + span render and the final validated result, nothing written.
  - `.venv/bin/python -m evaluation.claims.fidelity.author --source t3-1-5` — same, then writes
    the accepted gold; prints the two paths.
  - `.venv/bin/python -m pytest tests/test_fidelity_author.py -q`
  - `.venv/bin/python -m pytest tests -q`; `.venv/bin/pyright`;
    `.venv/bin/python -m evaluation.claims.fidelity.run --oracle` (unchanged).
- **Test suites:** root `tests/` only (evaluation/ + tests/; no app adapter).
- **Expected behavior:** accepting all valid entries writes a gold that round-trips (0041's
  guarantee); `--dry-run` writes nothing; skipping an entry excludes it from the written gold.
- **Relevant failure cases (must be exercised):**
  - Unknown `--source` (not in `list_acim_sources()`) → loud named error, nothing written.
  - **Missing/malformed drafts file (change 6):** `--source t3-1-5` is a real source but
    `drafts/t3-1-5.draft.json` is absent or invalid JSON → loud named error, **not** a silent
    fall-back to an empty draft (which would masquerade as "accept zero"). Fail-loud.
  - A **malformed draft** (dangling `describes`, foreign source, duplicate, missing per-kind
    field) → fails at **load** via `DerivedGoldFile`'s validators with the named error (change 2).
  - A draft entry whose span is bad → surfaced at render time (preview fails with the named
    `EvidenceNotFoundError`/`AmbiguousEvidenceError`); if accepted, `write_gold` still rejects
    the whole set, nothing written — the front-end does not swallow or bypass the core.
  - **Skip that breaks the bundle (change 3):** skipping a `describes`-link target while
    accepting its describer → `check_gold` in `adjudicate` rejects loudly, nothing written.
  - `q` (quit) before finishing → nothing written.
  - Accepting **zero** entries → nothing written, layer stays UNAUTHORED (change 5).

## Acceptance criteria

- `adjudicate` with scripted decisions returns exactly the accepted entries; skip excludes;
  quit truncates; the accepted set is what `write_gold` receives; accepted gold is `AUTHORED`
  while the draft on disk stays `UNAUTHORED`.
- The user-run command renders each entry with its correct anchored span and honors a/s/q.
- `--dry-run` performs full adjudication + validation and writes **nothing**.
- A bad/accepted span still produces a loud rejection with nothing written (core not bypassed).
- A skip that breaks a `describes`-link or variant bundle → loud rejection, nothing written.
- Missing/malformed/unknown-source draft → named error, nothing written (fail-loud, no empty
  fall-back).
- Zero accepted → nothing written, layer UNAUTHORED.
- Oracle unchanged; full suite + pyright green; no-dict + empty-`__init__` hold.

## Known-trap regression checks

- **No-dict:** `adjudicate` returns a typed `AdjudicationResult` (dataclass/pydantic), not a
  `dict`; decisions are a typed enum/sequence, not stringly-typed dicts.
- **Core not bypassed (the 0041→0042 seam):** a test proves an accepted bad-span entry still
  raises through `write_gold` and leaves nothing written — the front-end must not re-implement
  or skip validation.
- **Preview/write anchor parity (change 7):** a test (or shared helper) ensures the render-time
  span and write-time span come from the same `list_acim_sources()` anchor path — guards the
  "two anchoring paths mask each other" trap (cf. the entity_relation two-bugs finding).
- **Empty-but-authored fabrication:** accepting zero entries must not write an authored-empty
  gold (the "unauthored vs authored-empty" distinction, 0038 finding 6); user chose
  write-nothing/stay-UNAUTHORED.

## Definition of done

- [ ] User can run the command and drive it; the rendered spans and a/s/q behavior are correct.
- [ ] Evidence proves the outcome (validator **runs the user command** + the tests, per the
      hardened slice-validator rule).
- [ ] All failure cases exercised.
- [ ] `pyright` clean; `tests/` green; oracle unchanged; no-dict + empty-`__init__` hold.
- [ ] Final pass `REVIEW: clean` + `VALIDATION: pass`. One implement / one fix / one re-review.
- [ ] Commit left to the user (no-self-commit).

## Remaining limitations

- The reveal phase shows the already-extracted literal claims (`list_claims` for the passage)
  as read-only reference; it does **not** run a live extractor. Prototype cross-check (0034
  §Stage 1b, `t3-1-5` only) is out of scope for this slice unless trivial.
- Still authors only `t3-1-5`; the other 4 dev passages are the follow-up (0040 §Follow-up).
- Draft authoring is mine; the tool never generates entries — it only renders, validates, and
  persists what the user accepts.
