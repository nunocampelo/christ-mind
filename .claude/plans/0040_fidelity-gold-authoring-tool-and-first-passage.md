# Stage 1b: interactive fidelity-gold authoring + dev-split gold

## Context

The fidelity benchmark scaffold (plans 0034, 0036–0039) is **built and verified** — schema,
scorer, runner, and the six 0038 integrity findings all landed and are committed clean at
`5dfd024`. But every one of the nine derived-gold sidecars under
`evaluation/claims/fidelity/gold/` is an **empty placeholder** (`shared: []`,
`literal_status/derived_status: "unauthored"`). The dev split reports `0/5` authored, so the
harness currently measures **nothing** — a Stage-2 two-pass extractor would have no gold to
score against.

This plan executes **Stage 1b**, which 0034 already specified: an interactive authoring tool
(`evaluation/claims/fidelity/author.py`), and the first authored gold. **This slice lands the
tool + the single passage `t3-1-5`** (the prototype-shaped one) — proving the staged workflow
end-to-end before investing interactive-authoring time across all five. The other four dev
passages (`t3-1-6`, `t3-4-4`, `t1-1-3`, `t1-1-56`) and all four reserved report passages stay
unauthored, authored in a quick follow-up slice once the tool is proven.

**Working model (agreed):** draft-then-adjudicate. For the passage I draft the full set of
literal + derived entries from the text, then walk the user through them for accept/revise.
The gold is doctrinal interpretation at the target fidelity the
`scripts/proto_forgiveness_condition.py` prototype defined — the user's call is the source of
truth, so the tool *assists* judgement and *never generates* a committed entry.

This is run through `/slice` like 0039, with its own slice contract.

**Sequencing (agreed) — and scope split:** the actual `/slice` run is scoped by
[`0041_fidelity-authoring-tool-slice-contract.md`](0041_fidelity-authoring-tool-slice-contract.md),
which **supersedes this doc's scope**: the slice delivers only the tool's **typed, testable
write/validate core (`write_gold`) + its tests + the serialization write path** — NOT the
interactive `input()` CLI front-end, and NOT the real authored `t3-1-5` gold. The §Files,
§Scope, and §Verification below describe the *eventual* Stage-1b deliverable; where they
mention the `t3-1-5` sidecar/`.jsonl` or a dev-`1/5` run artifact as slice outputs, defer to
0041 — those real gold files are produced in the **separate human-in-the-loop authoring
session** afterward (draft-then-adjudicate), by running the proven tool, and are untouched by
the slice. The interactive front-end is the follow-up on top of the slice's core.

## Scope

**In:** the authoring tool; literal `.jsonl` + derived `.derived.json` gold for **`t3-1-5`
only**, authored interactively (draft-then-adjudicate); tests for the tool.

**Explicitly deferred:** the other 4 dev passages + 4 report passages (follow-up slice);
Stage 2 two-pass extractor (`src/application/derivation/derive_graph.py`, `GraphDeriver`), any
LLM/deriver wiring, the reserved report split, corpus re-extraction, `PROMPT_VERSION` bump,
graph projection changes, no new `Claim` field. A green oracle is still not benchmark
performance.

## Approach

### 1. Evidence-span validator (already exists — reuse as-is)

`src/application/extraction/spans.py:25` **already provides**
`validate_span(source, quote) -> tuple[int, int]`, raising distinctly on missing
(`EvidenceNotFoundError`) vs ambiguous (`AmbiguousEvidenceError`) — exactly what the tool
needs to tell the author which failure occurred. **No new file, no `anchor_claim` refactor.**
The tool imports and calls it directly.

### 2. The authoring tool — `evaluation/claims/fidelity/author.py`

`python -m evaluation.claims.fidelity.author --source <id>`, mirroring `run.py`'s argparse/
`main()` shape (`GOLD_DIR`/`RUNS_DIR` = `Path(__file__).parent / ...`, `StrEnum`, `main(argv)`
tail). Source access uses **`list_acim_sources()` + a local `{s.id: s}` map**
(`sources_acim.py:101`), matching every ACIM runner — **not** `source_for_id`, which is backed
by the generic `list_sources()`, not the ACIM corpus. No existing interactive-prompt helper
exists, so the `input()` loop is the one genuinely new piece.

Draft-then-adjudicate flow for the one passage:

- **Draft.** The tool prints the full `Source.text`. I propose literal `Claim`s and derived
  entries (`OCCURRENCE` / `RESOLVED_REFERENCE` / `REQUIREMENT` / `DESCRIPTION` / `CONDITION`),
  each with an **exact supporting span** validated by `validate_span` (so a bad quote is
  rejected before it enters gold, with the missing-vs-ambiguous distinction surfaced to the
  user). Entries may be marked `unresolved` or grouped into coherent **variants**.
- **Adjudicate.** The user accepts/revises each entry; the extracted literal `Claim`s and, for
  `t3-1-5`, the prototype's rendering are available as reference. Revisions are appended to the
  sidecar's `adjudication_history` (field already on `DerivedGold`).
- **Write.** The tool writes the derived sidecar via
  `DerivedGoldFile.from_gold(gold).model_dump_json(indent=2)` + `write_text` (the write path
  doesn't exist in the repo yet — `run.py` only reads sidecars; mirror the `RunRecord` write at
  `run.py:274`), and the literal `.jsonl` in the `ClaimLine` shape `load_gold_claims` reads.
  It flips `literal_status`/`derived_status` to `AUTHORED`. `check_gold` runs inside
  `from_gold`, so a malformed bundle fails loudly at save. The tool **never commits an entry
  the user didn't accept**.

### 3. Author `t3-1-5` (the deliverable)

`t3-1-5` is the prototype-shaped passage: condition + resolved reference + requirement
reframing. Authoring it reproduces, as adjudicated gold, the target fidelity
`proto_forgiveness_condition.py` established — the natural first passage because the prototype
already worked out its reading. Counterexample passages (object-less-correct-as-is,
plain-assertion-no-conditions, symmetric contrast, multi-reference) are distributed across the
remaining four dev passages in the **follow-up** slice.

## Files

- **New** `evaluation/claims/fidelity/author.py` — the interactive tool.
- **New** `tests/test_fidelity_author.py` — staging invariant (initial annotations saved
  before reveal; `adjudication_history` recorded on revision), the tool's handling of
  `validate_span`'s missing/ambiguous errors, round-trip of an authored sidecar through
  `from_gold`/`to_gold`, and that the tool never writes an entry the author didn't enter.
- **Authored gold** `evaluation/claims/fidelity/gold/t3-1-5.derived.json` (flip to authored,
  real entries) + the matching literal `t3-1-5` `.jsonl` in the `ClaimLine` shape.
- Run artifact under `evaluation/claims/fidelity/runs/` showing dev now `1/5` authored.

**Reused unchanged:** `src/application/extraction/spans.py` (`validate_span` +
`EvidenceNotFoundError`/`AmbiguousEvidenceError`), `score_fidelity.py`, `run.py`,
`serialization.py` (`DerivedGoldFile`), `validation.py` (`check_gold`), `gold.py`
(`load_gold_claims`), `domain/derivation/*`, `domain/claims/*` (`ClaimLine` in
`claims/serialization.py`). The `proto_forgiveness_condition.py` prototype stays the reference
target. No `anchor_claim` refactor, no new `Claim` field.

## Verification

```bash
.venv/bin/python -m evaluation.claims.fidelity.author --source t3-1-5   # interactive draft-then-adjudicate
.venv/bin/python -m pytest tests/test_fidelity_author.py -q
.venv/bin/python -m pytest tests -q                                     # full suite green
.venv/bin/pyright                                                       # zero errors
.venv/bin/python -m evaluation.claims.fidelity.run --oracle             # still perfect
.venv/bin/python -m evaluation.claims.fidelity.run                      # dev now reports 1/5 authored
```

- The real proof is **the authored `t3-1-5` gold loads, validates (`check_gold`), and
  round-trips** `from_gold`/`to_gold` with recomputed ids intact — plus the tool-behavior
  tests (never writes an unaccepted entry; surfaces missing-vs-ambiguous span errors; records
  `adjudication_history` on revision).
- The reserved report split (`--report`) is **not run** during this slice.
- `/slice` done-gate: diff-reviewer `REVIEW: clean` + slice-validator `VALIDATION: pass`
  (pyright + declared suites + no-dict + empty-`__init__`). One implement / one fix / one
  re-review budget. Commit stays the user's action (no-self-commit).

## Follow-up (next slice, not this one)

Author the remaining 4 dev passages (`t3-1-6`, `t3-4-4`, `t1-1-3`, `t1-1-56`) through the
proven tool, deliberately placing the 0034 counterexamples — object-less-correct-as-is,
plain-assertion-no-conditions, genuine symmetric contrast, multi-reference — so the dev split
reaches `5/5` and can catch over-interpretation, not just under-interpretation. The 4 reserved
report passages are authored only when a Stage-2 deriver exists to score against them.
