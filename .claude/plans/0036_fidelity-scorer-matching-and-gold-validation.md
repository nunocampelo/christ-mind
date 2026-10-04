# Slice: fidelity scorer — maximum matching + gold validation fixes

## Outcome

The fidelity scorer (`evaluation/claims/fidelity/score_fidelity.py`) stops under-counting
aligned pairs and stops crediting invalid readings: (1) matching maximizes correct pairs
first then **total** aligned pairs; (2) a reference's literal/interpreted `support` is part
of full correctness; (3) every **gold** entry's `source_id` is validated; (4) an invalid
**gold** mention (absent or non-unique in its evidence) is rejected as invalid gold (raises),
while an invalid **predicted** mention stays a scoring miss.

## Layers touched

- **evaluation** (`evaluation/claims/fidelity/score_fidelity.py`) — the scorer; this is the
  only production module the outcome needs. No domain/application/infrastructure change: the
  derived-gold model and serialization validators are already correct for this slice.
- **tests** (`tests/test_fidelity_score.py`) — regression tests for each of the four.

No other layer is touched: the four issues are all internal to the scorer's matching and
validation logic.

## Baseline (recorded BEFORE implementation)

- Working tree was **clean** at start: `git stash create` printed nothing, so
  `BASELINE_SHA = HEAD = c3abed1dc630c70776e21b443928a6951b6cbfc9`.
- **Pre-existing dirty set: empty** (no tracked-dirty, no untracked). Everything is in scope
  because nothing was already in flight.
- Not an eval-delta slice: the evidence is targeted tests + the oracle sanity run, not a
  score delta against a prior run artifact (gold is unauthored, so there is no real score).

## Change manifest (filled in as I implement)

- **Tracked edits:** `evaluation/claims/fidelity/score_fidelity.py`,
  `tests/test_fidelity_score.py` (incl. **rewriting** one existing test — see below).
- **New / untracked files:** none expected.

### Note: an existing test is inverted by design (not just additions)

`test_ambiguous_gold_mention_gets_no_credit` (currently asserts an ambiguous **gold** mention
→ `referent_matches == 0`) encodes the *old* "silent miss on invalid gold" behavior that
issue 4 now makes **raise**. It is **rewritten** to `pytest.raises(GoldAnchorError)`. So the
"existing tests stay green" claim is corrected: one assertion is intentionally inverted; the
rewritten test is the standing guard for the new behavior.

## Evidence (declared BEFORE implementation)

- **Type:** targeted tests (the four issues are specific scorer invariants) + the oracle
  self-prediction sanity run (must still pass).
- **Reproduce with:**
  - `.venv/bin/python -m pytest tests -q` (full root suite — the only suite the touched
    layer covers; no app adapter involved)
  - `.venv/bin/python -m pytest tests/test_fidelity_score.py tests/test_fidelity_serialization.py tests/test_fidelity_identity.py tests/test_spans.py -q`
  - `.venv/bin/python -m evaluation.claims.fidelity.run --oracle` (exit 0)
  - `.venv/bin/pyright`
- **Test suites to run:** root `tests/` only. No `apps/*` adapter touches this module.
- **Expected behavior (happy path):** a self-prediction still scores every applicable
  dimension perfectly (oracle); existing 426 tests stay green.
- **Relevant failure cases (the four):**
  1. **Two present-but-wrong conditions on different spans, both predicted** → BEFORE: only
     1 presence TP (the second-stage greedy `augment` fills only still-unmatched gold slots
     and never reroutes, so it strands one *wrong* pair). AFTER: both align → presence TP =
     2, each recorded wrong on its differing field (0 `fully_correct`, 2 unsupported). The
     test asserts **both** presence TP 1→2 **and** `fully_correct == 0` — so the fix cannot
     be satisfied by inflating presence at the cost of a correct pair. This exercises the
     *any_edge* (second) matching stage specifically, distinct from the existing
     `test_matching_is_maximum_not_greedy`, which uses field-*correct* occurrences already
     maximized by the *correct_edge* (first) stage.
     - **Objective rationale:** maximize correct pairs first, then total. Locking a maximum
       correct set first means a wrong pair can never displace a correct reading some other
       assignment would have scored (TP preserved); only then does maximizing total aligned
       pairs recover presence credit. Hence correct-first, not total-first.
  2. **A reference changed interpreted→literal** vs gold interpreted → BEFORE: `fully_correct
     = 1`, 0 unsupported. AFTER: not fully correct (support differs) → `fully_correct = 0`,
     counted as unsupported; `referent_matches`/`abstention` stay support-independent by
     construction (computed inline in `_score_reference`, not via the core match). One edit
     point: `_reference_match` (since `_reference_core` delegates to it).
  3. **A gold entry naming another source** → raises before scoring. **Surface:** this guards
     *programmatically constructed* `DerivedGold` (oracle fixtures, future Stage-2 deriver
     output), NOT on-disk gold — `DerivedGoldFile.to_gold()` forces every entry's `source_id`
     to the container id, so a loaded file structurally can't hit it. Defense-in-depth for
     the in-memory path, which is exactly what the oracle and the deriver produce.
  4. **A gold reference whose mention is absent / repeated in its evidence** → raises
     `GoldAnchorError` (invalid gold). The uniqueness check lives in `_anchor_gold`, gated on
     `entry.kind is RESOLVED_REFERENCE and entry.mention is not None`, reusing the exact
     find/second-find logic of `_mention_span` so gold and scorer agree on "unique". A
     **predicted** mention that is absent/ambiguous stays a scoring miss (no raise) — asserted
     in the same test — consistent with the `_anchor_gold` raises / `_anchor_prediction`
     sets `(-1,-1)` asymmetry.

## Acceptance criteria

- Two aligned-but-wrong conditions on distinct spans → `condition.presence.true_positives
  == 2` regardless of prediction order.
- Reference support mismatch → `reference.fully_correct == 0` and that pair counts toward
  `unsupported` (exhaustive gold); abstention/referent diagnostics remain support-independent
  in meaning.
- A gold entry with a mismatched `source_id` raises `ValueError` before scoring.
- A gold reference with an absent/repeated mention raises `GoldAnchorError` (invalid gold);
  a predicted reference with an absent/repeated mention does **not** raise and simply earns
  no referent credit.
- Oracle still exits 0; existing 426 tests still pass; pyright clean.

## Known-trap regression checks

- **Greedy-fill under-count** (this slice's #1): the two-present-but-wrong-conditions test is
  the standing guard — it is exactly the maximum-vs-greedy distinction prior rounds kept
  circling.
- **Interpretation masquerading as literal** (prior round's status fix, now extended to
  references): the reference support test guards the last kind that omitted it.
- **Invalid gold scored as model failure** (prior round established `_anchor_gold` raising;
  this extends the same principle to source id + mention validity): the two gold-validation
  tests guard it.

## Definition of done

- [ ] Acceptance criteria met, shown by the declared tests.
- [ ] Evidence proves the outcome (validator reasoning), failure cases exercised.
- [ ] `pyright` clean; `pytest tests -q` green.
- [ ] no-`dict`-return and empty-`__init__` rules hold (no new return types; no `__init__`
      touched).
- [ ] Final pass `REVIEW: clean` + `VALIDATION: pass`.

## Remaining limitations

- Gold passages stay **unauthored** — this slice is still scorer plumbing, not a real score.
- Maximum *total* matching is computed per kind by augmenting-path search; it does not do
  weighted matching across kinds (kinds are independent, so none is needed).
