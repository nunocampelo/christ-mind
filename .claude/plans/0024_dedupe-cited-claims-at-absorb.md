# Dedupe `cited_claims` at absorb time

## Context

The last black-box eval run (`evaluation/blackbox/runs/20260929T071508Z.jsonl`, 21 cases,
16 pass) failed 5 cases. When you asked for a "citation deterministic guard", the
implicit target was fabricated evidence — but the run's failure split tells a
different story:

- **3 of 5 failures** (`forgive-mother-013`, `mind-definition-025`,
  `knowledge-definition-026`) tripped the existing `citation_integrity` gate with
  `duplicate cited claim_id(s)`. Not fabrication — the agent's `cited_claims` list
  literally contained the same `claim_id` more than once.
- The remaining 2 failures (`mind-of-god-004b`, `course-about-006`) were
  `required_evidence_present` misses — a retrieval/ranking gap, not a citation
  guard problem.
- **Zero** failures were `unknown_ids` (fabricated ids) or would have been caught
  by an evidence-vs-`Source.text` re-anchor check.

The root cause of the duplicates is `apps/agent/src/mind_of_christ_agent/domain/
orchestrator.py:308-321`: `_absorb` appends every `_to_cited_claim(item)` it sees.
The orchestrator seeds one batch `find_claims` at
`orchestrator.py:126-129` and the ReAct loop can then call `find_claims` /
`find_claims_for_entity` / `find_sources` again for overlapping terms — the same
`claim_id` surfaces twice and both land in `cited_claims`. The repeat-search guard
at `orchestrator.py:166-176` catches only exact term repeats; it does not stop a
term reworded through `_normalize_term` collision or a different retrieval tool
that legitimately overlaps.

The fix is small and lands where the data enters: dedupe by `claim_id` inside
`_absorb`, keeping the first occurrence. This unblocks the 3 duplicate-failing
cases without touching the retrieval-miss cases (those need ranking work, which is
already flagged as roadmap #10 follow-up per `blackbox-baseline-finding` memory).

An evidence-vs-`Source.text` re-anchor guard is deferred: it defends against a
failure mode not yet observed in eval and adds a corpus scan to every turn. Worth
building later once the duplicate-and-ranking wins land, not now.

## Change

**One file, three-ish lines of real logic.**

### `apps/agent/src/mind_of_christ_agent/domain/orchestrator.py`

In `_absorb` (currently at lines 308–331), track which `claim_id`s already sit in
the shared `cited_claims` list and skip appends for ids that are already there.
Apply the same rule inside `chain_claims` links: an `InferredChain` should also
not repeat a `CitedClaim` already in `cited_claims`, for the same reason (a
chained-link is still a Course-attributed claim and citing it twice is the same
defect).

Concretely:

- Compute `seen: set[str] = {c.claim_id for c in cited_claims}` at the top of
  `_absorb`.
- In the `_CITED_TOOLS` branch: append only when `claim.claim_id not in seen`,
  and update `seen`.
- In the `chain_claims` branch: filter each chain's `links` through the same
  `seen` (chain links are stored in `inferred_chains`, not `cited_claims`; the
  dedupe target is preventing a link from *also* implying a duplicate cite when
  the model marker references it). Keep the chain even if empty after filtering,
  so the trace of what the tool returned is preserved — this matches how
  `_diagnose_citations` treats chain links as intentionally not-part-of the
  citation set (see the docstring at `orchestrator.py:236-238`).
  - Sub-decision: on reflection, chain links are *not* added to `cited_claims`
    today (see `orchestrator.py:322-331`), so a marker citing a chain-link id
    already shows up in `unknown_ids` — no change needed here. **Scope the
    dedupe strictly to the `_CITED_TOOLS` branch.**
- No new imports, no new module, no DTO change.

The rule is: **`cited_claims` is a set-by-id, ordered by first appearance**. Same
invariant `_diagnose_citations` already assumes when it builds
`gathered = {c.claim_id for c in cited_claims}` (`orchestrator.py:240`) —
we're just making the list obey what the set-based diagnostics already treats it
as.

### Comment worth adding

One sentence at the top of `_absorb`, no more, explaining the invariant — "first
appearance wins; a later `find_claims` returning the same `claim_id` is dropped,
so `cited_claims` stays set-by-id". This is the kind of non-obvious *why* the
existing style guide (`CLAUDE.md` § Style) endorses: a reader looking at a bare
`if claim.claim_id in seen: continue` would ask which occurrence to keep.

## Tests

### `apps/agent/tests/test_orchestrator.py`

Line 514 currently *asserts* the duplicate behavior:

```python
assert [c.claim_id for c in orchestrator.last_answer.cited_claims] == ["c1", "c1"]
```

Change to `["c1"]` and update the test's docstring/comment so it reads as the new
invariant, not a corrected typo. The test was correct about what the code did; the
code was wrong about what it should do.

### New test in the same file

Add one focused test — `test_absorb_dedupes_cited_claims_by_id` — that runs the
orchestrator through a script where two different tool calls (e.g. `find_claims`
followed by `find_claims_for_entity`) each return the same `claim_id`, and
asserts:

- `cited_claims` has exactly one entry for that id.
- The `citation_diagnostics` produced for a `[claim_id]` marker in the answer
  prose treats the claim as gathered (empty `unknown_ids`).
- Ordering: first occurrence is retained (assert on the first tool call's
  `_claim_result()` fields, not a later one's).

Mirrors the existing test pattern at `apps/agent/tests/test_orchestrator.py:363
(test_cited_claims_and_inferred_chains_stay_distinct)` — module-level fixtures,
`_FakeMcpClient` for the seam, `_scripted_stream` for the LLM, no MCP transport
in the loop.

### `tests/test_blackbox_deterministic.py`

The current deterministic evaluator's `duplicated` check remains as a
belt-and-braces guard against future regressions in the absorb layer. Its
existing tests can stay untouched — nothing about the evaluator's contract
changed. Do not weaken or delete that check as part of this PR.

### Black-box eval re-run

After the change lands, re-run the black-box harness against the same 21-case
gold set. Expect:

- The 3 duplicate-failing cases (`forgive-mother-013`, `mind-definition-025`,
  `knowledge-definition-026`) to pass on `citation_integrity`.
- The 2 retrieval-miss cases to still fail on `required_evidence_present` (they
  are not what this change addresses).
- Pass rate to move from 16/21 to 19/21.

Command per `CLAUDE.md § Commands`:

```
.venv/bin/python -m evaluation.blackbox.run  # producer script exact args as run.py's CLI
```

Actual invocation: check `evaluation/blackbox/run.py` for the current CLI shape
before running (not enumerated here to avoid stale flags).

## Verification checklist

1. `.venv/bin/pyright` — clean.
2. `.venv/bin/python -m pytest tests apps/agent/tests apps/a2a-server/tests -q`
   — all pass, including the modified line-514 assertion and the new dedupe
   test.
3. Re-run black-box eval; commit the resulting
   `evaluation/blackbox/runs/<timestamp>.jsonl` per the run-artifact convention.
4. Inspect the new run's failed-case list; the failure set should shrink to the
   two retrieval-miss cases only.

## What this deliberately does *not* do

- No new `src/application/citations/` use case.
- No re-anchor of `evidence` against `Source.text`.
- No change to `CitationDiagnostics`, `AgentAnswer`, or any DTO on the a2a wire.
- No change to the black-box deterministic evaluator itself — its
  `duplicated` check stays as a downstream guard, redundant with the new absorb
  invariant, and that redundancy is intentional (belt-and-braces at a layer
  boundary).

Deferred: if a future run surfaces cases where a `CitedClaim`'s `evidence` does
not actually appear in its `Source.text`, revisit the re-anchor guard. Track under
the same investigation thread as retrieval-miss (`blackbox-baseline-finding`).
