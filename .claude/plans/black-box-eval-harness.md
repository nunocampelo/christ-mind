# Increment #10 — black-box evaluation harness

The detailed plan for the roadmap's next increment. Its predecessor (#9, situation→
concept mapping) is done, so per the roadmap's rule this scope is fixed by #9's results
and by what the shipped agent/web stack exposed: uneven answers whose failures we cannot
currently *attribute*.

This increment builds a regression suite for **the product**, not for today's
architecture. The agent is a black box; the evaluator sees only `question → answer +
sources` and knows nothing of `map_situation`, `find_claims`, concepts, repositories,
prompts, or model choice. That boundary is the whole point: six months from now the entire
retrieval implementation can be replaced and the same suite still tells us whether the
*experience* got better or worse.

## Why a black-box harness comes before any retrieval change

The tempting reading of the agent's uneven answers is "retrieval can't find the right text
— add embeddings." That is a guess, and the codebase shows why it's likely wrong:

- **There is no query-relevance ranking today.** `find_claims`/`find_claims_batch`
  (`src/application/retrieval/find_claims.py`) return substring matches in *corpus order*,
  sliced to a limit; `find_sources` too. The claims the agent sees are the first matches in
  the file, round-robined across mapped concepts — not the most relevant.
- **The epistemic boundary is entirely prompt prose.** The "these passages don't yet give
  us enough to describe X" / "this is an interpretation, not something the Course states"
  behavior lives only in the agent prompt (`_INSUFFICIENT`, `_BOUNDARY_VOICE` in
  `apps/agent/.../domain/prompt.py`), backed by a non-rejecting citation audit
  (`_diagnose_citations`).

So a bad answer could be a retrieval miss, an evidence-selection miss, or a synthesis
overreach — and **nothing measures which**. Building embeddings before we can attribute
failures means never knowing whether they helped. The harness makes the failures visible
first; retrieval/ranking/embeddings/dossiers come *after*, each justified by measured
failure. Concretely, when embeddings land you don't have to trust that they helped — you
read `before: 17/20 → after: 16/20` and inspect which cases moved.

## Architecture: a hard boundary between the gate and the diagnostic

```
                    ┌─────────────────────┐
   question ───────▶│   agent (black box) │──────▶ answer + sources/citations
                    └─────────────────────┘
                               │
                    ┌──────────▼──────────┐
                    │   Black-box suite   │   the CI regression gate
                    │      PASS / FAIL    │   (source of truth)
                    └──────────┬──────────┘
                               │  on FAIL only
                    ┌──────────▼──────────┐
                    │  Diagnostic (A/B/C) │   explains a failure; reads inside
                    │  reads traces       │   the pipeline; never changes the verdict
                    └─────────────────────┘
```

**The invariant, enforced in code and in review:** the black-box result is PASS/FAIL and is
the source of truth; the diagnostic layer can *explain* a failure but can never rescue,
weaken, or redefine it. The dataflow is one-directional — black-box verdict → (on failure)
diagnostic — never diagnostic → verdict.

### The black-box suite is the contract

Knows nothing about internals. For each fixture it asks only: *given this user question,
did the system produce an acceptable, source-grounded answer?* Tested across four
dimensions:

1. **Source grounding** — cited passages are actually relevant; every substantive claim has
   supporting evidence; the answer introduces no claim the cited material doesn't support.
2. **Answer behavior** — the answer does the right *kind* of thing for the question (a
   PURPOSE question synthesizes central teaching rather than enumerating retrieved concepts;
   a DESCRIBE question distinguishes direct description from relational/indirect evidence; an
   APPLICATION question may interpret but marks the interpretation as its own).
3. **Epistemic boundaries** — a first-class category. For questions the corpus can't answer,
   GOOD = "the passages provided don't give enough to answer that directly"; BAD = "the
   Course teaches that X…". Evaluate the *behavior*, not exact wording.
4. **Citation quality** — every citation resolves to a real source; the source supports the
   nearby claim; no fabricated reference; nothing cited merely to look grounded.

**The gate is categorical, not an aggregate score.** Some failures fail outright regardless
of how good the rest of the answer reads — an invented citation is a fail even in an
otherwise excellent answer. So the gate is e.g. "20/20, with any explicitly quarantined
flaky case listed," never `mean_score >= 0.80`.

### The diagnostic (A/B/C) is deliberately invasive

Used to *investigate* a failure — primarily against production traces, and also against a
failing evaluation case during development. It reads inside the pipeline (retrieved-vs-cited
claims, which the existing `_diagnose_citations` already computes) and answers three
questions, a sharper decomposition than "retrieval vs synthesis":

- **A — evidence availability.** Did the system retrieve the evidence needed to answer? A
  "no" here is a *retrieval/ranking/recall* problem (the case that would justify #12
  embeddings).
- **B — evidence adequacy.** Was the retrieved evidence actually *sufficient* to support the
  answer? This is the God example exactly — lots of related material, not enough for a
  direct description. A *selection / epistemic-sufficiency* problem.
- **C — answer fidelity.** Given the available evidence, did synthesis stay within what the
  evidence supports? Catches overreach, conflation, bad interpretation, misplaced citations
  — a *synthesis/prompt* problem.

A worked failure:

```
BLACK-BOX  ✗ god-description-001 — epistemic boundary failed
DIAGNOSTIC A evidence retrieved?  yes
           B evidence sufficient? no
           C synthesis overstated it? yes
LIKELY FIX synthesis / evidence-boundary handling  (NOT retrieval)
```

versus:

```
BLACK-BOX  ✗ purpose-of-course-002 — answer missing central teaching
DIAGNOSTIC A evidence retrieved?  no
           (candidate passages existed in corpus? yes)
LIKELY FIX retrieval / ranking
```

Without this, every bad answer tempts a "fix retrieval" reflex; A/B/C is what stops us
spending #12 effort on what is really a #11-or-prompt problem.

## The judge stack: three layers (harness = DeepEval)

DeepEval is the harness — it's pytest-native evaluation infrastructure with custom metrics,
CI, caching, and traces, so we get real regression tests rather than another bespoke
subsystem. Three layers under it:

1. **Deterministic checks** — cheap, 100% reproducible, and authoritative for the
   categorical failures. Because we own the corpus, these are exact: sources exist, every
   source id resolves, reference metadata valid, no duplicate ids, citation format valid,
   answer non-empty, required boundary structure present. An invented/unresolvable citation
   fails here, unconditionally.
2. **LLM judge** — DeepEval G-Eval / custom metrics for the genuinely hard-to-formalize
   criteria: *does the answer faithfully and usefully synthesize the supplied passages while
   preserving the Course's conceptual relationships?* Criteria are tied to **behaviors**,
   never "score this 1–10" — a vague scalar produces "sounds good," not a usable signal.
3. **System-1 judge** — bounded, typed decisions returned as calibrated probabilities, which
   is the shape this domain actually wants. Not `overall_quality = 0.73` but:
   `answers_question`, `supported_by_sources`, `directness`, `interpretation_marked`,
   `sufficient_evidence` — each a separate 0–1. For the God case that reads e.g.
   `answered_directly ≈ 0.31, evidence_sufficient ≈ 0.27, indirect_evidence_present ≈ 0.91`,
   which is far more actionable than one number.

**Verified, as of 2026-09:** DeepEval has `llm` (default), `hybrid` (LLM extracts/reasons,
Jev decides), and `system_one` (Jev runs the whole metric, no LLM key needed) eval modes;
Jev is TypeSafe AI's System-1 model (bounded yes/no / rating / choose-one with calibrated
probabilities). Laya (`convaiinnovations/laya`, HF) is an open-weight Apache-2.0 System-1
decision model (421M English checkpoint, ModernBERT-large, ~33 ms single-question, "never
generates text, nothing to parse, nothing to hallucinate") — a candidate local System-1
judge. Both check out as described.

**Caveat carried into the plan (do not skip):** a System-1 model's published benchmarks
establish *general* decision performance, not performance on ACIM source-grounding and
epistemic-boundary judgments. Before trusting Laya or Jev as a gate input, run the initial
fixtures through human judgment alongside Laya, Jev, and a strong LLM judge, and compare
disagreements. Adopt a System-1 judge for a given criterion only where it correlates with
the human calls on *this* domain. Until then it's advisory, not gating.

The judge (LLM or System-1) receives only the black-box output (question, answer, sources)
plus the fixture's evaluation criteria — **never internal traces**. Traces are the
diagnostic layer's input, not the judge's.

## The fixtures

Black-box, behavioral, and deliberately *not* prescribing an exact expected answer — we test
"given this question, does the system behave correctly?", not "did it produce this text?"

```yaml
id: god-description-001
question: "Can you describe God?"
evaluation:
  intent: direct_description
  expected_behavior:
    - distinguish_direct_from_indirect_evidence
    - acknowledge_insufficient_evidence_when_appropriate
  prohibited_behavior:
    - present_associations_as_definitions
    - invent_unsupported_attributes
```

**Start with ~20, not 500.** The three existing example questions are already three
excellent fixtures. Deliberately span:

- direct answer available
- direct answer *un*available (feeds the epistemic-boundary category)
- broad synthesis ("what is the Course all about?")
- specific factual question
- relationship between concepts ("how are love and fear related?")
- application to life ("how can I help my friend?")
- ambiguous question
- question containing a false premise
- question asking for something outside the corpus

**Growth loop — the strongest fixture corpus is real usage, not a designed benchmark:**

```
production traces → human review → promote notable interactions into the regression suite
```

The suite runs after every meaningful change — retrieval, prompts, source formatting, model.

## Development loop this enables

```
make change → run black-box suite
                 ├─ PASS → merge
                 └─ FAIL → run A/B/C diagnostic on the failing trace
                             → identify likely layer (A retrieval / B selection / C synthesis)
                             → fix → re-run suite
```

## Relationship to retrieval work (now downstream, and gated)

The mode-aware retrieval design from the earlier draft of this increment (question modes
selecting per-intent ranking strategies that extend `ranking.py`) is **not** part of #10.
It becomes a *candidate fix* that the harness justifies — it lands only if the A/B/C
diagnostic shows failures dominated by **A** (evidence not retrieved) or ranking-shaped
**B**. Deferred, each with an explicit trigger:

- **#11 — claim ranking / retrieval improvements** (incl. the mode→ranking design): gated on
  A/B/C showing misses dominated by retrieval/ranking, not synthesis. If the harness shows
  most failures are **C**, #11 is a synthesis-prompt change instead, and ranking waits.
- **#12 — embeddings + persistent index (Postgres/pgvector)**: gated on **A** persisting
  after #11 — the answering passage exists in the corpus but lexical/concept retrieval
  demonstrably can't surface it. The in-memory `list_claims()` tuple is fine at current
  scale; #10 adds no scale pressure.
- **#13 — concept / entity dossiers**: gated on repeated describe/exploration failures where
  per-concept *aggregation* is the bottleneck (scattered claims, no consolidated view),
  which shows up as **B** the ranking can't fix.

## Definition of done for #10

- A DeepEval-based black-box suite runnable in CI, with ~20 behavioral fixtures spanning the
  categories above, including direct-unavailable / false-premise / outside-corpus cases.
- Layer 1 (deterministic) authoritative for categorical failures (citation resolves, no
  fabrication, etc.); layer 2 (LLM judge) for synthesis fidelity; layer 3 (System-1) present
  but advisory until validated against human judgment on these fixtures.
- The A/B/C diagnostic implemented as a *separate* tool over pipeline traces, with the
  one-directional invariant (verdict → diagnostic, never the reverse) enforced.
- The judge receives only black-box outputs + fixture criteria, never traces.
- A documented promote-from-production path for growing the fixture set.
- The suite gives a measured basis for choosing #11 (ranking vs synthesis), #12 (embeddings),
  or #13 (dossiers) — from the A/B/C split on real failures, not from guessing.
