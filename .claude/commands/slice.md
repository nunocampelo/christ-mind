---
description: Drive one vertical slice from a one-line outcome through verified, demonstrated implementation — critique, implement, independent review, evidence.
argument-hint: <one-line outcome, in your own words>
---

You are the **lead** for a single vertical slice. The user gave you an outcome:

> $ARGUMENTS

Own it end to end. The user reviews **behavior and evidence first**, with a concise diff
summary available on request — they should not have to hunt through a large diff to find
problems. Read `CLAUDE.md` and `.claude/plans/SLICE_TEMPLATE.md` before anything else.

Run this loop. Do not skip the critique or the validation step.

## 0. Record the baseline — before touching anything

Capture a real **content snapshot** of the working tree, not just filenames — a status line
is unchanged when you edit an already-dirty file, so status alone can't separate your slice
from pre-existing edits. Capture two things, under the session scratch dir:

- **Tracked edits → a baseline commit object:** run `git stash create` and record the SHA
  it prints (`BASELINE_SHA`). This is a real commit capturing all staged + unstaged tracked
  edits at this instant; it does **not** touch your working tree. Do not `git diff` it now —
  right after creation the tree equals it, so a diff would be empty. You compare against it
  **after** implementing: `git diff <BASELINE_SHA> -- <path>` then shows exactly your
  slice's change to a tracked file, with any pre-existing edits already baked into the
  baseline. (If `git stash create` prints nothing, there were no tracked edits — use `HEAD`
  as `BASELINE_SHA`.)
- **Pre-existing dirty set → recorded now, not inferred later:** capture the list of files
  that were *already* dirty at baseline, because this can only be computed at capture time:
  - tracked-but-dirty: `git diff --name-only HEAD <BASELINE_SHA>` (the files whose baseline
    content already differs from HEAD);
  - already-untracked: `git ls-files --others --exclude-standard` (this lists individual
    files inside untracked *directories*, which `git status --porcelain=v1` collapses to a
    single entry and would miss).
  Together these are the **out-of-scope** set.
- **Untracked files → copies:** copy each file from the `git ls-files --others
  --exclude-standard` list into the scratch dir. A manifest file that is *not* in the
  pre-existing dirty set is genuinely new/changed by this slice.

Everything in that set is **pre-existing work, out of scope for this slice**. The rule for
this slice: **do not modify a file that was already dirty at baseline** — if the outcome
genuinely needs to touch one, stop and escalate to the user, because its pre-existing edits
and your slice's edits can't be cleanly separated for review. The reviewer compares the
final tree against `BASELINE_SHA` (tracked) and the untracked copies, never against
HEAD/index. Hand the reviewer three things: `BASELINE_SHA`, the scratch-dir path, and the
**pre-existing dirty set** (so it checks scope by lookup, not by re-deriving it).

For an eval slice, note (or produce) the baseline run artifact in **the harness's own
`runs/` directory** (e.g. `evaluation/claims/runs/`, `evaluation/blackbox/runs/`, or the
fidelity harness's output dir) before implementing — declare which in the contract.

## 1. Draft the slice contract

Fill in the SLICE_TEMPLATE shape for this outcome. Verticality means **complete observable
behavior, touching only the layers the outcome needs** — not a tour of all four. Declare the
evidence *now*, before implementing, following the evidence rule in the template
(eval+expected-delta for retrieval/extraction/ranking; observable tool interaction for
user-facing tool changes; targeted tests for specific invariants — and always relevant
failure cases, never happy-path-only).

For a non-trivial slice, write it to `.claude/plans/NNNN_descriptive-kebab-name.md` (next
number, descriptive name — see CLAUDE.md § Plans). For a small one, keep it inline.

## 2. Critique the contract (plan-critic subagent) — before any code

Spawn the **plan-critic** subagent with the contract. It checks the slice against the user's
principles and confirms the declared evidence can actually establish the outcome. If it
returns **revise**, apply the required changes and re-send once. If it escalates a material
product decision or a conflicting requirement, **stop and ask the user** (AskUserQuestion) —
do not resolve product intent yourself. Bounded: one critique + one re-check, then proceed
or escalate. Do not loop.

## 3. Implement

Implement only once the contract is **ready**. Respect every CLAUDE.md rule (DDD layering,
no-`dict` returns, empty `__init__`, modern typing, sparse comments). Keep the change as
small as the outcome allows. As you go, record the slice's **change manifest** in the
contract: tracked edits and new/untracked files, each listed by path — this is the exact
scope the reviewer gets. Derive it by diffing against the step-0 baseline, not from a bare
`git diff` (which omits untracked files).

## 4. Independent review + validation — in parallel, both read-only

In one message, spawn both — neither edits code or tests, so the thing under review can't
change mid-review. **This includes you, the lead:** while the parallel pass is running, do
not patch-and-restore any repo file to check a counterfactual (e.g. reverting the fix to
confirm a test bites). Even a transient revert can be observed by a concurrent agent. Use an
isolated copy outside the repo or in-memory substitution for any such check.
- the **diff-reviewer** subagent, handed the **change manifest** (not the whole working
  tree) — it reviews only this slice's files for correctness, regressions, and the repo's
  rules, and reports findings;
- the **slice-validator** subagent on the declared evidence — it reproduces the command,
  exercises the failure cases, judges whether the evidence *proves the outcome* (not just
  that it runs), checks the gates (pyright + every declared test suite + no-dict +
  empty-init), and **recommends** (does not write) regression checks for any gap.

Escalate to the user only unresolved correctness questions or conflicting requirements.

## 4a. Apply all fixes together, then a single final pass

Make the code's final state in one batch so the final review sees exactly what ships:
resolve the diff-reviewer's routine findings **and** add the validator's recommended
regression checks worth keeping (the validator is read-only, so you add them — this is how
each past correction becomes a standing check). Update the manifest.

Then run the **one allowed re-review**: diff-reviewer and slice-validator on this final
state. Do not loop beyond this.

## 4b. Completion gate — do not present a slice as done without it

A slice is **done** only when the final pass returns **`REVIEW: clean`** *and*
**`VALIDATION: pass`** (gates included: pyright + every declared suite + no-dict +
empty-init). If either still reports a defect after the one re-review (the budget is
exhausted), **do not present it as complete.** Present it as **explicitly incomplete**:
state the unresolved findings, which gate failed, and what remains — and escalate to the
user rather than papering over it. "Escalated" findings in the contract's done-definition
mean a *material product decision the user must make*, never an unaddressed correctness
defect.

## 5. Present the slice for the user's review

Lead with what the user actually judges — behavior, then evidence — then the summary:

1. **What changed** — one short paragraph.
2. **Reproduce the evidence** — the exact command(s).
3. **The evidence itself** — the metric/transcript/test output, and the validator's
   one-paragraph reasoning on *why it proves the outcome*, including the failure cases.
4. **New regression checks** — any the validator added, and the correction each one encodes.
5. **Concise diff summary** — the change manifest with `file:line` pointers; the full diff
   is there if the user wants it, but don't paste it wholesale.
6. **Remaining limitations** — plainly stated.

Then stop. The user's review is about whether the behavior meets their intent — the
technical defects should already be resolved. Leave the git commit to the user.
