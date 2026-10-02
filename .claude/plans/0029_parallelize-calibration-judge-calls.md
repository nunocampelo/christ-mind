# Parallelize the calibration judge calls

> **Status: IMPLEMENTED** (not committed). Changes landed in `run.py` + the test module;
> `pytest tests/test_blackbox_calibration_run.py` (16 passed) and full-repo `pyright`
> (0 errors) are green. Still owed: a live wall-clock/end-to-end smoke run against a reachable
> judge model (`--fixtures …/calibration.jsonl --repeats 5`, 60 tune calls, vs `--concurrency 1`).
> See "Implementation notes" at the end for what differed from the plan.

## Context

A calibration run (`evaluation/blackbox/calibration/run.py`) takes several minutes even
though it needs no live stack (no Docker/Postgres/agent). The cost is the **judge** itself:
`_evaluate` makes `fixtures × repeats` LLM completions, each a heavy call — large input
(question + full answer + every cited claim's whole source paragraph) and a verbose
structured `semantic_grounding` output array. Today these run **strictly serially** (nested
`for fixture … for _ in range(repeats)`), so wall-clock is roughly `calls × (several seconds)`
back-to-back.

Workload for the default tune pass of the committed fixtures (`fixtures/calibration.jsonl`):
**12 tune fixtures × 5 repeats = 60 judge calls** (the 7 holdout fixtures stay unjudged
unless `--holdout` is passed). Each `judge.evaluate(...)` is exactly one LLM completion
(`llm_judge.py` builds one prompt and parses all criteria from the single reply).

Each trial is independent — `_evaluate` only accumulates counters and appends to `trials` —
so the calls can run concurrently with no change to what is measured. The judge's `Complete`
is **synchronous and I/O-bound** (`infrastructure/llm/anthropic_proxy.py`, a blocking
`client.messages.create`), so a bounded **thread pool** is the right tool; no need to thread
`async` through `LLMEvaluator`.

Goal: collapse the run from minutes to tens of seconds, with aggregation that is
**deterministic given identical trial results** (see the qualification below), and a CLI knob
to throttle.

### What "deterministic" does and does not promise

Ordering and aggregation are deterministic **given the same set of trial results**: the fold
runs on the main thread in fixture→repeat order, so `trials[]` ordering and every counter are
reproduced exactly regardless of which thread finished first. It does **not** promise an
identical report run-to-run:

- the judge is stochastic, so scores and pass/fail verdicts legitimately vary;
- failure counts, the `run_id`/`created_at` timestamps, and the recorded `concurrency` value
  differ by construction;
- concurrency can itself affect provider availability (more in-flight calls → more chance of
  a rate-limit/`provider_failure`), so parallel execution is **not** guaranteed to leave the
  measured failure rates unchanged versus serial.

So the claim is "same aggregation of the same trials," not "byte-identical output file."

## Approach

Rework only `_evaluate` in `evaluation/blackbox/calibration/run.py` to dispatch the judge
calls through a `concurrent.futures.ThreadPoolExecutor`, then fold results **in original
fixture→repeat order**. Nothing else in the file (report shape, provenance header, CLI
output) changes except adding one CLI flag and argument validation.

### 1. Dispatch concurrently via ordered `executor.map`, fold on the main thread

Split the current single loop into two phases, using `executor.map` so results arrive in
**submission order** without any future→slot bookkeeping:

- **Build the work list** in loop order, precomputing each fixture's case once:
  `tasks = [(fixture, case) for fixture in fixtures for _ in range(repeats)]`
  (compute `case = fixture.case.to_case()` per fixture, reused across its repeats).
- **Submit** with `executor.map(lambda t: judge.evaluate(t[1].?, t[0].response), tasks)` —
  concretely, a small named worker `fn(task) -> list[CriterionResult]` that calls
  `judge.evaluate(case, fixture.response)`. `executor.map` runs them concurrently but
  **yields results in submission order**, so iterating the returned generator paired with
  `tasks` gives `(fixture, results)` in the original fixture→repeat order.
- **Fold** by iterating `zip(tasks, results)` on the main thread, running the existing
  accumulation logic unchanged (`judged`/`agree`/`fp`/`fn`, the failure buckets
  `provider_fail`/`parse_fail`/`incomplete`/`unscored`, `per_fixture_status`,
  `per_fixture_scores`, and `trials.append(...)` carrying `failure_reason`). This reproduces
  the serial accumulation exactly.

The per-criterion stats computation (flips / within-fixture stdev) and the `CriterionStats`
construction are untouched — they read the accumulated structures, now populated in
deterministic order.

Only `judge.evaluate(...)` runs on worker threads; the human-verdict join and all counter
updates stay on the main thread during the fold, so no shared mutable state is touched
concurrently.

> Note: `executor.map` yields in order but still **waits for each result as it goes**; an
> exception raised while producing an item surfaces when the fold reaches it. See §4.

### 2. Error semantics unchanged

`LLMEvaluator.evaluate` already catches provider and parse failures internally and returns
`not_evaluated` results (never raises) — so a flaky judge call surfaces as a
`provider_failure`/`parse_failure` row exactly as today, not as a pool exception, and the
existing failure-bucket accounting is preserved verbatim in the fold. Any *unexpected*
exception (a real bug) must still propagate and fail the run loudly, per CLAUDE.md's
"catch the narrowest exception, don't swallow `Exception`" rule — do not wrap the worker body
in a broad try/except.

### 3. Validate positive arguments early

Reject non-positive knobs **before** constructing the judge or submitting any call, with a
clear `SystemExit` (matching the file's existing `raise SystemExit(...)` style for the
no-fixtures and leakage cases):

- `--concurrency < 1` → error.
- `--repeats < 1` → error (today a `0`/negative value would silently produce an empty run).

Do this in `main` right after parsing args.

### 4. Exception cleanup on unexpected failure

A `ThreadPoolExecutor` used as a context manager calls `shutdown(wait=True)` on exit, so if an
unexpected exception escapes the fold the interpreter would otherwise **block until every
already-submitted call finishes**. To fail fast, on an escaping exception call
`executor.shutdown(cancel_futures=True)` (Python 3.9+; the venv is 3.14) to drop
not-yet-started work. Acknowledge the limit in a one-line comment: **calls already in flight
cannot be cancelled** and will run to completion — `cancel_futures` only clears the queue.
Structure as an explicit `ThreadPoolExecutor(max_workers=concurrency)` with a
`try/finally` (or `with` + re-raise) that performs the cancelling shutdown, rather than
relying on the plain context-manager exit.

### 5. Thread safety is an explicit prerequisite

The generic `Evaluator` protocol (`evaluator.py`) does **not** promise concurrent safety —
parallel evaluation is only correct with a thread-safe judge. For the real judge
(`LLMEvaluator`), `evaluate` is stateless aside from the shared `anthropic.Anthropic` client,
which is backed by `httpx.Client` (installed: `anthropic==1.8.0`, `httpx==0.28.1`) and is
documented safe to share across threads for concurrent requests. Document this as a
precondition in a module/function comment: *parallel evaluation assumes `judge.evaluate` is
safe to call concurrently; the stock `LLMEvaluator` is (stateless + thread-safe httpx
client), a stateful fake judge is not — run such a judge at `--concurrency 1`.*

### 6. Signature + imports

- `_evaluate(judge, fixtures, repeats)` → `_evaluate(judge, fixtures, repeats, concurrency=1)`.
  Defaulting `concurrency=1` preserves any existing/other callers (notably the new unit
  tests that drive `_evaluate` directly) and keeps the serial path the explicit baseline.
  Return type unchanged.
- `main` passes `args.concurrency`.
- Add `from concurrent.futures import ThreadPoolExecutor` to the imports.

### 7. `--concurrency` CLI flag + header provenance

Add near `--repeats`:

```python
parser.add_argument(
    "--concurrency", type=int, default=8,
    help="max concurrent judge calls (1 = serial)",
)
```

Record it in the result header dict as `"concurrency": args.concurrency`, so a committed
`results/*.jsonl` says how it was produced — matching the file's habit of pinning run
parameters (`repeats`, `pass_threshold`, `fixtures_sha256`).

## Tests (deterministic, offline — the real proof of equivalence)

Live stochastic runs **cannot** prove the parallel fold aggregates like the serial one.
Add deterministic unit tests driving `_evaluate` with a fake judge — put them where the
existing calibration/blackbox unit tests live (e.g. `tests/test_blackbox_*`; confirm the
exact module during implementation and follow its fixture style). The no-`dict` policy
applies — build real `CriterionResult`/`Fixture` objects, not dict literals.

1. **Serial vs parallel equivalence under out-of-order completion.** A **thread-safe** fake
   judge that returns a *fixed, pre-scripted* `list[CriterionResult]` per fixture (so trial
   results are identical regardless of thread timing) but sleeps a per-fixture-varying amount
   so completions would finish out of submission order. Run `_evaluate` at `concurrency=1`
   and at `concurrency>1`; assert the two `SplitReport`s (criteria stats **and** the ordered
   `trials` list) are **equal**. This is the core guarantee.
2. **Failure buckets.** Scripted results covering each `not_evaluated` `failure_reason`
   (`provider_failure`, `parse_failure`, `incomplete_coverage`, and the `None`/unscored case),
   plus `not_applicable` human verdicts (skipped) — assert each lands in the right counter and
   `agreement_rate`.
3. **Unexpected-exception propagation.** A fake judge whose `evaluate` raises an unexpected
   error (not an `AnthropicProxyError`) — assert `_evaluate` re-raises rather than
   swallowing, at both `concurrency=1` and `>1`.
4. **Existing stateful `_FakeJudge` tests run at `concurrency=1`.** The default
   `concurrency=1` on `_evaluate` means current tests that use a stateful/ordered fake keep
   passing unchanged; only the new equivalence test opts into real concurrency with a
   thread-safe fake.

## Critical files

- `evaluation/blackbox/calibration/run.py` — `_evaluate` body + signature, `main` argparse +
  validation + call site + header dict, one import.
- `tests/test_blackbox_*` (exact module confirmed during implementation) — new deterministic
  equivalence / failure-bucket / exception-propagation tests.

No change to `llm_judge.py`, `anthropic_proxy.py`, `fixtures.py`, the result pydantic models
(`TrialOutcome`/`CriterionStats`/`SplitReport`), or any fixture/result file on disk.

## Typing / style

- Modern native typing (`list[X]`, `dict[K, V]`, `X | None`); match the file.
- Comments sparse per CLAUDE.md — one line each on: why the fold is a separate main-thread
  pass, the in-flight-cancellation limit (§4), and the thread-safety precondition (§5).
  Nothing restating executor mechanics.
- `.venv/bin/pyright` from repo root — fix every error by tightening annotations (the worker
  signature and the `executor.map` result iterator want explicit types).

## Verification

1. **Unit tests:** `.venv/bin/python -m pytest tests/test_blackbox_* -q` — the equivalence,
   failure-bucket, and exception tests pass. These are the real correctness proof.
2. **Type-check:** `.venv/bin/pyright` — clean.
3. **Live smoke (needs a reachable judge model via the proxy):** run the default tune pass
   and confirm it completes, writes `results/<run_id>.jsonl`, and prints populated
   per-criterion lines:
   `.venv/bin/python -m evaluation.blackbox.calibration.run --fixtures evaluation/blackbox/calibration/fixtures/calibration.jsonl --repeats 5`
   (60 calls). Then `--concurrency 1` for the serial baseline. Expect the parallel run to be
   substantially faster; expect scores/verdicts to differ (stochastic) — that is not a
   regression.
4. **Arg validation:** `--concurrency 0` and `--repeats 0` each exit with a clear message
   before any judge call.
5. **Header provenance:** the written result header carries `"concurrency"`.

## Out of scope

- Not changing `--repeats` default or the stability math — concurrency is the free win;
  `repeats` is a measurement knob (see memory: judge-calibration-harness).
- Not judging the holdout split — stays unjudged unless `--holdout` is explicit.
- Not touching the judge model (`_resolve_model`) — a correctness knob, not a speed one.
- Not parallelizing `capture_flagged.py` or the main black-box `run.py` (separate harnesses;
  the latter is gated on the live stack, a different bottleneck).

## Implementation notes (what actually landed)

- **Test module** was `tests/test_blackbox_calibration_run.py` (confirmed), which already
  held `_FakeJudge` (stateful, cycles scores) and `_UnavailableJudge` (failure-bucket
  coverage). The pre-existing failure-bucket / FP-FN / stability / `not_applicable` /
  reject-gate tests already cover §Tests points 2 and 4, so no new tests were needed there —
  they run at the new `concurrency=1` default unchanged.
- **New tests added:** `_StaticJudge` (thread-safe, fixed per-id score + per-id sleep) driving
  `test_parallel_matches_serial_under_out_of_order_completion` (serial vs `concurrency=4`
  `SplitReport` equality — the core guarantee), and `_RaisingJudge` driving
  `test_unexpected_exception_propagates` (parametrized `concurrency` 1 and 4).
- **`_evaluate`** uses ordered `executor.map(judge_one, tasks)` where `tasks` is the
  fixture list flattened over repeats and `judge_one` calls `judge.evaluate` with a
  per-fixture `case` precomputed once. Explicit `ThreadPoolExecutor` with `try/except
  BaseException: executor.shutdown(cancel_futures=True); raise`, then a normal
  `executor.shutdown()` on the success path.
- **Extra import:** `CriterionResult` added to the `evaluation.blackbox.evaluator` import for
  the `judge_one` return annotation (beyond the planned `ThreadPoolExecutor` import).
- Pre-existing uncommitted changes to `llm_judge.py` + its test were left untouched; no
  commit made.
