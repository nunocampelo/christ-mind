# Slice contract template

A **slice** is the unit of review in the `/slice` workflow. It delivers one piece of
observable behavior and ends in evidence you can look at — never just a diff. Copy this
shape into a `.claude/plans/NNNN_descriptive-kebab-name.md` file (next number in creation
order; see CLAUDE.md § Plans) for a non-trivial slice, or inline it for a small one.

A slice is complete behavior, **not** a tour of every layer. Touch only the layers the
outcome needs.

---

## Outcome

One sentence, in the user's words: what should be true after this slice that isn't now.

## Layers touched

Only the ones this outcome actually needs (domain / application / infrastructure / app
adapter). Justify each. If you're touching a layer "to be complete," cut it.

## Baseline (recorded BEFORE implementation)

So review and validation target *this slice*, not whatever was already in the tree:

- **Working-tree content snapshot before I start:** a `BASELINE_SHA` from `git stash create`
  (captures all tracked staged + unstaged edits as a commit object; compared against *after*
  implementation, never diffed at creation when it would be empty) plus copies of the
  then-untracked files (enumerated with `git ls-files --others --exclude-standard`, which
  reaches files inside untracked directories that `git status --porcelain=v1` collapses) —
  not just `git status`, which is unchanged when an already-dirty file is edited.
- **Pre-existing dirty set:** recorded at capture time — tracked-but-dirty from
  `git diff --name-only HEAD <BASELINE_SHA>`, plus the already-untracked list above. This is
  the **out-of-scope** set and must be computed now (it can't be re-derived from the tree
  afterward). The slice does not modify anything in it (escalate if the outcome needs to).
- **Baseline eval artifact** (eval slices only): name the **harness** and the run file the
  delta is measured against, in that harness's own `runs/` directory — claims
  `evaluation/claims/runs/`, black-box `evaluation/blackbox/runs/`, or the fidelity harness
  under `evaluation/claims/fidelity/`. If none exists, this slice's first step is to produce
  one under unchanged conditions.

## Change manifest (filled in as I implement)

The explicit list of files this slice touches, so the reviewer sees exactly the slice and
not unrelated in-flight work. `git diff` omits untracked files, so new files are listed
separately:

- **Tracked edits:** `path` — one line each.
- **New / untracked files:** `path` — one line each.

## Evidence (declared BEFORE implementation)

The plan-critic verifies this can establish the outcome before any code is written.

- **Type:** eval run | observable MCP tool interaction | targeted tests — pick what the
  outcome demands, per CLAUDE.md:
  - retrieval / extraction / ranking → a black-box or claims eval run;
  - user-facing tool change → an observable tool interaction (inspector transcript or a
    test against the `server.py` wrapper) showing the typed pydantic result;
  - always → targeted tests for the specific invariants/regressions at stake.
- **Reproduce with:** the exact command (e.g.
  `.venv/bin/python -m pytest apps/mcp-server/tests -q`, or the eval `run` invocation, or
  the stdio server + inspector call).
- **Test suites to run:** name every suite the touched layers cover — root `tests/` and/or
  `apps/mcp-server/tests`, `apps/agent/tests`, `apps/a2a-server/tests`. `pytest tests -q`
  alone misses the app suites; a tool change must run its adapter's suite too.
- **Expected behavior:** what the evidence should show on the happy path.
- **Relevant failure cases:** the inputs that *should* be rejected / return `[]` / raise —
  and what correct handling looks like. (Happy-path-only evidence is not accepted.)
- **Eval comparison contract** (eval slices only):
  - **Harness + artifact dir/format:** which harness produces the evidence and where it
    writes (e.g. fidelity harness → `evaluation/claims/fidelity/...`), so the validator runs
    and writes in the right place.
  - **Baseline artifact:** path to the run the delta is measured against (see Baseline).
  - **Comparable conditions:** same extractor / dataset / config as the baseline; state
    them. Never tune on holdout; add `--holdout` only to report a final result, per
    CLAUDE.md.
  - **Expected delta + direction + rationale:** the number you expect to move, which way,
    and *why that delta proves the outcome* rather than noise.
  - **Tolerance:** the band within which a result counts as "no change" — so a
    behavior-preserving slice can legitimately declare "flat within tolerance," and a
    stochastic wiggle isn't read as a regression.

## Acceptance criteria

Checkable statements. "19/21 with mind-of-god-004b flipping fail→pass, and it is both
retrieved AND cited" — not "retrieval is better."

## Known-trap regression checks

If the outcome touches a previously-caught failure mode (two bugs masking a channel; gold-ID
drift; citation fabrication; polarity dropped across a hop; eval-DB confusion), name the
check that guards against it. Each past correction should become a standing check here.

## Definition of done

- [ ] Acceptance criteria met, shown by the declared evidence.
- [ ] Evidence actually proves the outcome (validator's reasoning, not just a green run).
- [ ] Relevant failure cases exercised.
- [ ] `.venv/bin/pyright` clean; every declared test suite passing via
      `.venv/bin/python -m pytest <suite> -q` (not just root `tests/`).
- [ ] no-`dict`-return and empty-`__init__` rules hold for everything touched.
- [ ] Final pass returns **`REVIEW: clean`** and **`VALIDATION: pass`** on the shipped
      state. A correctness defect is never "done" — if the re-review budget is exhausted
      with findings open, the slice is **incomplete** and presented as such, not done.
      Escalation is only for a *material product decision the user must make*.
- [ ] Remaining limitations stated plainly.

## Remaining limitations

What this slice deliberately does not do, and anything the next slice should pick up.
