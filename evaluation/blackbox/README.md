# Black-box evaluation harness

A regression suite for the **product**, not the architecture. It treats the agent as a
black box — `question → answer + sources` — and knows nothing of `map_situation`,
`find_claims`, prompts, or the MCP internals. Retrieval can be rewritten later and this
suite still measures whether the *experience* got better or worse. (Design and rationale:
`.claude/plans/black-box-eval-harness.md`.)

## The one boundary that matters

```
question ─▶ A2A ─▶ agent ─▶ real MCP ─▶ corpus ─▶ answer + sources ─▶ evaluators ─▶ PASS/FAIL
```

The evaluator only ever sees the black-box output. It reaches the agent through its **real
public A2A interface** (`client.py`), so a change to tool schemas, MCP serialization, or the
A2A artifact shape can break a run — that is the point.

## Two tiers

- **Offline unit tier** (`pytest`, no network, CI-safe): the gold loader, the `Evaluator`
  seam and `combine`, the deterministic checks, the LLM-judge parser, and the A2A response
  parser — all on hand-built or scripted inputs. Fast and deterministic.
- **Live run** (`python -m evaluation.blackbox.run --live`): asks the real agent the gold
  questions and scores the answers. There is **no offline full run** — a product eval can't
  score answers the product can't generate. This is an integration/evaluation run, not a
  unit test.

## The evaluator seam

`evaluator.py` defines `Evaluator` (`evaluate(case, response) -> list[CriterionResult]`) and
`combine`, which turns many criteria into one verdict:

- **Gating vs advisory is per-criterion.** A case fails iff a *gating* criterion failed.
  Advisory criteria (graded judge scores) are recorded but never flip the verdict.
- **`not_evaluated` is a third state, distinct from `pass`** — it matters while the judges
  are unvalidated.
- **Initially this is a structural-integrity gate, not a product-quality gate.** Only the
  deterministic criteria gate; the LLM judge is advisory until validated against human
  judgment on these fixtures. Promotion advisory→gating is a small code change but requires
  that validation first.

Evaluators:

- `deterministic.py` — **gating**, offline, no LLM. `citation_integrity` (no fabricated
  markers, cited sources exist in the corpus, no duplicates), `non_empty`, and
  `required_source_present` (only when a case names `must_include_source_ids`, else
  `not_evaluated`). An invented citation fails here, unconditionally.
- `llm_judge.py` — **advisory**, wired to the same proxy the agent uses. Scores
  `answers_question`, `semantic_grounding`, `synthesis_fidelity`, `epistemic_boundary`,
  `interpretation_marked` 0–1. A parse-failed or unreachable judge yields `not_evaluated`,
  never a spurious fail. **The judge is given only the question, answer, actual cited
  evidence, and the behaviour rubric — never the gold `must_include_*` ids**, so it is never
  told what the answer was "supposed to" cite.

A `SystemOneEvaluator` (Laya/Jev) or a `DeepEvalEvaluator` would be one more `Evaluator`
impl behind this seam; nothing else changes.

## The fixtures (`gold/`)

`cases.jsonl` (dev) and `cases_holdout.jsonl` (held out — untouched while tuning). Each case
is behavioral, not an answer key:

- `corpus_reality`: `sufficient` / `insufficient` / `absent` — has-enough / has-some-but-not-
  enough / not-present. Maps onto the future A/B diagnostic (`sufficient`→A✓B✓,
  `insufficient`→A✓B✗, `absent`→A✗).
- `expected_behavior` / `prohibited_behavior`: tokens from the closed vocabulary in
  `gold.py` (`BEHAVIOR_DEFINITIONS`), each with a one-line definition the judge prompt uses.
  An unknown token fails the loader loudly.
- `must_include_source_ids` / `must_include_claim_ids`: **required** evidence — the only
  thing `required_source_present` gates on. Kept sparse and used mainly for
  retrieval-target cases; synthesis/ambiguous/absent cases leave them empty.
- `may_include_*`: acceptable-but-not-required evidence; informs the judge/diagnostic, never
  gates.

All committed anchors are verified to exist in `corpus.jsonl`.

## Running it

Offline unit tests (no proxy, no stack):

```bash
.venv/bin/python -m pytest tests/test_blackbox_*.py -q
.venv/bin/pyright evaluation/blackbox
```

A live run (auto-spawns whatever isn't already up, tears down only what it started):

```bash
.venv/bin/python -m evaluation.blackbox.run --live --record
.venv/bin/python -m evaluation.blackbox.run --live --holdout          # score the holdout
.venv/bin/python -m evaluation.blackbox.run --live \
    --evaluators evaluation.blackbox.deterministic:make_deterministic,evaluation.blackbox.llm_judge:make_llm_judge
```

Without `--live` the CLI errors clearly (it cannot generate answers offline). A `--record`
run writes `runs/<run_id>.jsonl` — a header (agent URL, corpus run id, gold hash, gating
score) plus one line per case — to be committed.

### What a live run brings up (`harness.py`)

Detects each dependency, starts only those that are down, and cleans up only what it
started (a reused service is left alone):

| Dependency | Detect | Start if down | Cleanup |
| ---------- | ------ | ------------- | ------- |
| Anthropic proxy | `GET ANTHROPIC_BASE_URL` (default `:6656`) | `cproxy start` | left running (external, holds real creds) |
| Postgres | connect to the `postgres` admin db | `docker compose -f apps/a2a-server/docker-compose.yml up -d` | **left running** (shared infra; opt in with `stop_postgres_if_started=True`) |
| Eval DB `christ_mind_eval` | connect | `CREATE DATABASE` | left in place |
| Migrations | — | `alembic … upgrade head` (idempotent) | — |
| A2A server | agent-card 200 | `python -m mind_of_christ_a2a.main` subprocess | terminate only if we started it |

Notes:
- **Separate eval database.** Derived from `DATABASE_URL` by swapping the db name to
  `christ_mind_eval`, so the dev DB and its real conversation history stay untouched. The
  eval writes throwaway task/conversation rows it never reads (the corpus is bundled JSONL).
- **`AGENT_PUBLIC_URL`** is set to the eval server's own URL, *not* the repo `.env`'s
  frontend-dev value, so the agent card advertises the correct `/a2a` endpoint.
- The proxy can be started but never torn down (it is external and shared).
- **Postgres is never stopped by surprise.** Liveness is probed against the always-present
  `postgres` admin database (not the eval db, which may not exist yet), so a running server
  is correctly detected and left alone. Even when the harness starts Postgres itself, it
  leaves it running on teardown by default — stopping shared infra is disruptive. Pass
  `stop_postgres_if_started=True` only for a deliberate clean slate.

## Files

```
gold.py           BlackBoxCase + load_cases; BEHAVIOR_DEFINITIONS; corpus-reality enum
client.py         A2AAgentClient.ask() over the real A2A interface -> BlackBoxResponse
harness.py        live_stack(): detect/spawn/reuse/cleanup the four dependencies
evaluator.py      Evaluator protocol, CriterionResult/CaseResult, combine(), BlackBoxResponse
deterministic.py  DeterministicEvaluator (gating)
llm_judge.py      LLMEvaluator (advisory, via the proxy)
score.py          BlackBoxReport (gating pass rate, per-intent, advisory means)
run_format.py     on-disk header + per-case line (pydantic)
run.py            the --live CLI
gold/             cases.jsonl, cases_holdout.jsonl
runs/             committed run records
```

## Dependencies

Reuses the venv the repo already has: the agent's DTOs (`AgentAnswer`/`CitedClaim`) and A2A
types, plus `httpx`, `asyncpg`, and the a2a-sdk — all already installed for `apps/a2a-server`
and `apps/agent`. **No new dependency, no DeepEval.** Running the harness requires
`apps/agent` and `apps/a2a-server` installed in the venv (they are), and — for a live run —
Docker (for the Postgres path) and `cproxy` on PATH (for the proxy).

## Status

Offline tier is complete and green (unit tests + pyright). The live tier
(`client.py`/`harness.py`/`run.py`) is built and imports/type-checks clean; it has not yet
been executed end-to-end against the running stack — the first `--live --record` run
produces the committed baseline. The A/B/C failure-attribution diagnostic and validating the
advisory judges against human labels are later slices of increment #10 (see the plan).
