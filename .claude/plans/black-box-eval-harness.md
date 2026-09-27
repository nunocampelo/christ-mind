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
failure. Concretely, when embeddings land you don't infer improvement from aggregate answer
quality — the harness shows *which cases and which behavioral criteria* changed, on the same
fixtures before and after:

```
overall     17/20 → 18/20
by category   purpose 2/4 → 4/4 · directness 3/4 → 3/4 · grounding 5/5 → 5/5
              application 4/4 → 4/4 · epistemic 3/3 → 3/3
```

The same-cases before/after view is the point: a total that ticks up while a category
regresses is a warning, not a win.

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

**Initially this is a structural-integrity gate, not yet a product-quality gate.** Only the
deterministic gating criteria (citation integrity, non-empty, required-source-present) can
fail a case at first; the behavioral judges (grounding, synthesis fidelity, epistemic
boundary) are advisory until validated against human judgments on these fixtures. So a case
can pass on integrity while scoring low on synthesis — deliberate during calibration, and
stated plainly rather than hidden. Promotion advisory→gating is *mechanically* a config
change but *evidentially* requires validation on held-out human-labelled cases before it
flips.

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

**A/B/C is a likelihood classification with a routing hint, not a single-root-cause verdict.**
The three can co-occur (A=no and B=no and C=no together), and B in particular can stem from
retrieval, corpus coverage, *or* evidence selection. So the diagnostic emits per-dimension
likelihoods plus a routing weight, and the roadmap reads the **pattern across many failures**
— never one case deciding "this is #11":

```
BLACK-BOX  ✗ god-description-001 — epistemic boundary failed
DIAGNOSTIC A evidence availability   likely-sufficient
           B evidence adequacy       insufficient
           C synthesis overreach     likely
ROUTING    retrieval: low   evidence-selection: medium   synthesis: high
```

```
BLACK-BOX  ✗ purpose-of-course-002 — answer missing central teaching
DIAGNOSTIC A evidence availability   insufficient   (candidates exist in corpus: yes)
           B evidence adequacy       n/a
           C synthesis overreach     unlikely
ROUTING    retrieval: high   evidence-selection: low   synthesis: low
```

Without this, every bad answer tempts a "fix retrieval" reflex; A/B/C is what stops us
spending #12 effort on what is really a #11-or-prompt problem.

## The judge stack: three layers behind an own `Evaluator` seam

**Harness decision (revised from an earlier draft that named DeepEval as the harness):**
the harness is **hand-rolled**, mirroring the existing `evaluation/mapping/` suite
(pydantic only, framework-free, no new dependency), because the repo pins exactly two
runtime deps and its three eval suites use zero frameworks — DeepEval would be a heavy
transitive tree and a second evaluation paradigm at the very point we're establishing a
durable gate. The durable asset is *our own* `Evaluator` abstraction; DeepEval is "not part
of the core architecture yet" and can slot in later as one more `Evaluator` impl
(`DeepEvalEvaluator`) without touching fixtures, criteria, the agent client, or reporting.
Once we have 30–50 cases it's worth running the same corpus through DeepEval as an
*experiment* to compare its judgments against ours — an experiment, not a dependency.

**When that `DeepEvalEvaluator` is written:** DeepEval's `GEval` can be pointed at the same
local proxy the agent uses (via a `DeepEvalBaseLLM` subclass), so it needs no separate LLM
key. A useful pattern to adopt is "GEval-below-threshold → deterministic fallback" — which
is the same shape as our gating/advisory split (a deterministic floor under an advisory
judge). Our `DeterministicEvaluator` already *is* that floor, which is confirmation the
split is sound.

Three judge layers sit behind the seam:

1. **Deterministic checks** — cheap, 100% reproducible, and authoritative for the
   categorical failures. Because we own the corpus, these are exact: sources exist, every
   source id resolves, no duplicate ids, no fabricated citation markers, answer non-empty.
   An invented/unresolvable citation fails here, unconditionally. **Gating.**
2. **LLM judge** — for the genuinely hard-to-formalize criteria: *does the answer faithfully
   and usefully synthesize the supplied passages while preserving the Course's conceptual
   relationships?* Criteria are tied to **behaviors**, never "score this 1–10" — a vague
   scalar produces "sounds good," not a usable signal. **Advisory** until validated.
3. **System-1 judge** — bounded, typed decisions returned as calibrated probabilities, which
   is the shape this domain actually wants. Not `overall_quality = 0.73` but:
   `answers_question`, `supported_by_sources`, `directness`, `interpretation_marked`,
   `sufficient_evidence` — each a separate 0–1. For the God case that reads e.g.
   `answered_directly ≈ 0.31, evidence_sufficient ≈ 0.27, indirect_evidence_present ≈ 0.91`,
   which is far more actionable than one number. **Advisory** (a future `Evaluator` impl).

**Gating vs advisory is per-criterion, not per-evaluator.** A case's PASS/FAIL comes from
gating criteria only; advisory criteria keep their raw scores and never flip the verdict.
`not_evaluated` is a distinct state from `pass` (it matters while the judges are
unvalidated). Promoting a criterion advisory→gating later, once it correlates with human
judgment, is a one-line change.

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

## Implementation

Builds `evaluation/blackbox/`, mirroring `evaluation/mapping/`'s file split and adding what
a product eval needs that a mapper eval doesn't: an **agent client that speaks the real A2A
interface**, the evaluator seam, and a dependency orchestrator. Named `blackbox`, not
`retrieval` — it evaluates the product, not a retrieval function.

### The boundary is the agent's real public interface (revised)

The black-box client drives the agent through **A2A → agent → real MCP → corpus**, not an
in-process orchestrator double. The evaluator still sees only `question → answer + sources`;
it knows nothing of A2A, MCP, `Orchestrator`, or `_to_claim_result`. This is more faithful
to a product regression suite: a change to tool schemas, MCP serialization, `_to_claim_result`,
or the A2A artifact shape *can* break a black-box test — which is the point. It also
dissolves the earlier `_to_claim_result` coupling worry: the real MCP server owns that path,
and the harness never imports it.

**Confirmed against the code:** a blocking A2A `SendMessage` returns both the answer prose
(`Task.status.message` / the `answer` artifact) and the structured sources — the `evidence`
artifact is `AgentAnswer.model_dump_json()` carrying `cited_claims` (kept distinct from
`inferred_chains`). So `ask(question) -> BlackBoxResponse` gets answer + sources in one call.
`apps/a2a-server/tests/test_a2a_endpoint.py:102-141` is the request/response template
(JSON-RPC `SendMessage`, header `A2A-Version: 1.0`, parse `evidence` via
`AgentAnswer.model_validate`). No A2A client exists in the repo yet — this writes the first.

### Two tiers, each honest about what it needs

- **Offline unit tier** (`pytest`, no network, in CI): gold loading, the evaluator seam and
  `combine`, the deterministic checks (on hand-built responses), the LLM-judge *parser* (on a
  scripted reply), the A2A client's request-build / response-parse (against
  `test_a2a_endpoint.py`'s recorded shape). Fast, deterministic.
- **Live integration tier** (`python -m evaluation.blackbox.run --live`): stands up the real
  stack and runs the ~22 fixtures through it. There is **no offline black-box run** — a
  product eval can't score answers the product can't generate. This is an
  integration/evaluation run, not an ordinary unit test.

### Dependency orchestration — auto-spawn what's down, reuse what's up

`--live` brings up four dependencies, starting only those not already running and tearing
down **only what it started** (a reused service is left alone):

| Dependency | Detect | Start if down | Cleanup |
| ---------- | ------ | ------------- | ------- |
| Anthropic proxy | `GET ANTHROPIC_BASE_URL` (default `:6656`) | `cproxy start` | leave running |
| Postgres | connect `DATABASE_URL` | `docker compose -f apps/a2a-server/docker-compose.yml up -d` (needs Docker) | `down` only if we upped it |
| Eval database | connect to the eval DB | `CREATE DATABASE christ_mind_eval` if absent | left in place |
| Migrations | — | `alembic ... upgrade head` against the eval DB (idempotent) | n/a |
| A2A server | `GET /.well-known/agent-card.json` | subprocess `python -m mind_of_christ_a2a.main`, poll card until 200 | terminate only if we started it |

**Separate eval database (same instance).** The eval writes throwaway task/conversation
rows the eval never reads (the corpus is bundled JSONL, not in PG). The harness derives an
eval DB name (`christ_mind_eval`) from the configured `DATABASE_URL` by swapping the database
segment, creates it if absent, migrates it, and points the spawned A2A server at it — so the
dev `christ_mind` DB and its real conversation history stay untouched. Isolating eval data in
its own DB also keeps it inspectable for the A/B/C diagnostic later.

**Env trap (from prior burns):** the harness sets `AGENT_PUBLIC_URL` to *its own* server URL
(e.g. `http://127.0.0.1:8000`) for the spawned server — it must not inherit the repo `.env`'s
frontend-dev `http://localhost:5173`, or the agent card advertises the wrong `/a2a` URL.
A clear failure if the proxy can't be started (it needs `cproxy` on PATH); Docker likewise
for the Postgres path.

### Files

```
evaluation/blackbox/
  __init__.py       # empty (repo convention)
  gold.py           # BlackBoxCase (frozen) + load_cases; loud error; behaviour tokens
                    #   validated vs a closed BEHAVIOR_VOCABULARY. Evidence anchors split
                    #   into must_include / may_include (see below).
  client.py         # A2AAgentClient: ask(question) -> BlackBoxResponse over real A2A.
                    #   No imports from application internals or apps/mcp-server.
  harness.py        # dependency orchestrator: detect/spawn/reuse/cleanup the 4 deps.
  evaluator.py      # CriterionResult / CaseResult / Evaluator Protocol + combine():
                    #   status = fail iff any GATING criterion failed; advisory never flips.
                    #   not_evaluated is distinct from pass.
  deterministic.py  # DeterministicEvaluator (gating): citation_integrity, non_empty,
                    #   required_source_present. (Semantic grounding is NOT here — see #2.)
  llm_judge.py      # LLMEvaluator (advisory): answers_question, semantic_grounding,
                    #   synthesis_fidelity, epistemic_boundary, interpretation_marked
  score.py          # BlackBoxReport: pass_rate, gating_pass_rate, per-CATEGORY + per-criterion
  run.py            # run(...) + argparse main (--evaluators, --holdout, --record, --live)
  run_format.py     # pydantic BlackBoxHeader (agent_url, corpus_run_id, gold_sha256,
                    #   ScoreLine) + CaseLine (per-criterion results)
  gold/
    cases.jsonl          # ~18 dev fixtures
    cases_holdout.jsonl  # ~5 held-out; UNTOUCHED during evaluator/prompt tuning
    README.md            # the anchoring notes (like evaluation/claims/gold/README.md)
  runs/             # committed run records
```

### Criterion split — integrity (deterministic/gating) vs grounding (semantic/advisory)

Deterministic checks establish only what the corpus makes objective; "does this passage
*support* the claim" is a semantic judgment and lives with the LLM judge:

```
Deterministic / GATING          Semantic / ADVISORY (until validated)
  citation_integrity              answers_question
    (syntax valid, source_id       semantic_grounding   ← moved here, was mislabelled
     exists, resolves, no          synthesis_fidelity
     fabricated marker, no         epistemic_boundary
     duplicate ids)                interpretation_marked
  non_empty
  required_source_present
    (only when the case names
     must_include sources; else
     not_evaluated)
```

**The gate today is a structural-integrity gate, not yet a product-quality gate** — most
behavioral properties are advisory during calibration, so a case can pass on integrity while
scoring low on synthesis. That is deliberate and stated, not a weakness to hide. Promotion of
a criterion advisory→gating is *mechanically* a config change but *evidentially* requires
validation on held-out human judgments before it flips.

### Fixture model — anchors are not an answer key (#5)

A case separates required from acceptable evidence, so the harness never becomes a hidden
exact-passage matcher:

```json
{"id": "...", "question": "...", "intent": "purpose", "corpus_reality": "adequate",
 "expected_behavior": [...], "prohibited_behavior": [...],
 "must_include_source_ids": ["t1-0-1"],
 "may_include_source_ids": ["t1-0-2", "t2-0-16"],
 "must_include_claim_ids": [...], "may_include_claim_ids": [...]}
```

`required_source_present` gates only on `must_include_*`; `may_include_*` informs the judge
and the A/B/C diagnostic but never gates. Partial/outside cases legitimately have empty
`must_include`, so their `required_source_present` is `not_evaluated`.

### Tests (root `tests/`, offline tier)

`test_blackbox_gold.py` (load + malformed + vocab + must/may split),
`test_blackbox_deterministic.py` (fabrication→fail, unknown source→fail, empty→fail,
must-include hit→pass, no-must-include→not_evaluated; real DTOs, no dict literals),
`test_blackbox_evaluator.py` (combine: one gating fail⇒fail; advisory-only / not_evaluated⇒pass),
`test_blackbox_client.py` (request build + response parse against the recorded A2A shape;
no socket), `test_blackbox_llm_judge.py` (scripted `Complete`; malformed reply→not_evaluated).
The `harness.py` orchestration is exercised by the `--live` path, not unit-tested (it's I/O).

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

## Definition of done

**This slice (the harness):**
- `evaluation/blackbox/` behind an own `Evaluator` seam, with ~18 dev + ~5 held-out
  behavioral fixtures spanning the categories, including direct-unavailable / false-premise /
  outside-corpus cases; held-out untouched during tuning.
- `A2AAgentClient.ask(question) -> BlackBoxResponse` over the real A2A interface (answer +
  structured `cited_claims`), importing nothing from `application` internals or
  `apps/mcp-server`.
- Dependency orchestrator: detect/spawn/reuse/cleanup the proxy (`cproxy start`), Postgres
  (docker-compose), the eval DB + migrations, and the A2A server — starting only what's
  down, tearing down only what it started, using a separate `christ_mind_eval` DB.
- Deterministic gating criteria (citation_integrity, non_empty, required_source_present) +
  wired advisory LLM judge (answers_question, semantic_grounding, synthesis_fidelity,
  epistemic_boundary, interpretation_marked). System-1 is a future `Evaluator` impl.
- `combine` enforces gating-only PASS/FAIL with `not_evaluated` distinct from `pass`.
- Offline unit tier green in CI; `--live` runs the fixtures through the real stack.

**Verification:** `.venv/bin/python -m pytest tests -q` (offline tier + existing suite green);
`.venv/bin/pyright` clean; `python -m evaluation.blackbox.run --live --record` (with the
stack auto-spawned) writes a committed baseline `runs/<id>.jsonl` and prints the
per-category pass table.

**Later #10 slices (not this one):**
- The A/B/C diagnostic as a *separate* tool over pipeline traces, one-directional invariant
  (verdict → diagnostic, never the reverse) enforced; emits per-dimension likelihoods +
  routing weights.
- A documented promote-from-production path for growing the fixture set.
- Validating the advisory judges against human labels, then promoting criteria to gating.
- The measured basis for choosing #11 (ranking vs synthesis) / #12 (embeddings) / #13
  (dossiers) — from the failure pattern across many cases, not one.
