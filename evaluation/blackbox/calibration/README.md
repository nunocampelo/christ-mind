# Judge calibration

Validate the LLM judge (`evaluation/blackbox/llm_judge.py`) against human-approved verdicts
before any criterion graduates from advisory to gating. The saturated 0.90–1.00 grounding run
showed agreement on easy passes proves nothing without **known failures** to test detection —
so this harness is built around controls, not just real answers.

Everything here is a one-off diagnostic, not part of the pytest suite.

Item 3 validation is complete; see [FINDINGS.md](FINDINGS.md) for the corrected tune
run, evidence-delivery check, and recorded decision. All criteria remain advisory;
grounding/fidelity do not qualify for graduation. The development holdout remains
unjudged.

## Artifacts

- `judging.py` — freeze/re-judge/dump machinery shared with `capture_flagged.py`.
- `fixtures.py` — the `Fixture` model (frozen answer + cited paragraphs + per-criterion human
  verdict `pass | fail | not_applicable` + reason) and its JSONL (de)serialization.
- `draft.py` — ask real cases once, freeze, and emit **draft** fixtures with judge-proposed
  verdicts and `approved_by=""`. A labour-saver; never the ground truth.
- `run.py` — re-judge each frozen fixture N times and report, per criterion: false positives,
  false negatives, parse failures, and score stdev — split `tune` vs `holdout` separately.
- `fixtures/` — committed fixture files. `results/` — committed calibration runs.

## Workflow

1. **Draft from real answers** (needs the live stack: DATABASE_URL, Docker, cproxy):

   ```
   .venv/bin/python -m evaluation.blackbox.calibration.draft \
     --cases id1,id2,...,id10 --out evaluation/blackbox/calibration/fixtures/base.draft.jsonl
   ```

   Pick 8–10 cases spanning corpus realities (`sufficient`/`insufficient`/`absent`).

2. **Review and approve.** For every drafted fixture, check each assertion against its cited
   paragraph (`response.cited_claims[*].evidence_context`), correct the verdict, write an
   evidence-based reason, and set `approved_by`. A real answer may carry a `fail` — do not
   rubber-stamp the draft.

3. **Derive controls by minimal edits** of the approved real fixtures. Each control changes
   exactly one thing, records `derivation` (`derived_from` + `edit`), and names in its verdict
   the single criterion it should trip:

   | control | edit | should fail |
   |---|---|---|
   | wrong-marker | swap a citation marker to an unrelated supplied paragraph | `semantic_grounding` |
   | reversed-polarity | flip a supported assertion's polarity | `synthesis_fidelity` |
   | unsupported-attribute | add an attribute no paragraph carries | `semantic_grounding` |
   | unjustified-abstention | replace a supported answer with abstention on a `sufficient` corpus | `premature_abstention` |
   | grounded-but-irrelevant | replace the direct answer with on-corpus prose that dodges the question | `answers_question` |

   Keep valid controls too (all criteria `pass`): paragraph-supported wording **outside** the
   extracted clause (the legitimate 0.90–1.00 case), an appropriate clarification request, and a
   justified abstention on an `absent`/`insufficient` corpus.

   The wrong-marker control is the regression test for the marker-scope fix: after that fix the
   judge must fail it even though another supplied paragraph supports the statement.

4. **Split and freeze.** Target 16–20 fixtures. Mark a small subset `holdout`; judge it only
   *after* any rubric/prompt tuning so its numbers aren't read off fixtures the wording was tuned
   against. Save as `fixtures/<name>.jsonl`.

5. **Calibrate** (no live stack needed — the judge only completes against the fixtures):

   ```
   .venv/bin/python -m evaluation.blackbox.calibration.run \
     --fixtures evaluation/blackbox/calibration/fixtures/<name>.jsonl --repeats 5
   # holdout, only once the rubric is frozen:
   .venv/bin/python -m evaluation.blackbox.calibration.run \
     --fixtures evaluation/blackbox/calibration/fixtures/<name>.jsonl --holdout
   ```

   The run **rejects any fixture lacking `approved_by`** (a draft's verdicts come from the
   judge under test — scoring against them is circular) and **rejects a control in a different
   split than its baseline** (leakage). It evaluates only the requested split, defaulting to
   `tune`; `--holdout` is explicit so holdout numbers aren't exposed mid-tuning.

   The result pins the resolved judge model, prompt version/hash (`llm_judge.PROMPT_VERSION`,
   `prompt_hash()`), the `pass_threshold` joined against, and the **SHA-256 of the fixtures
   file** — so editing a label or paragraph produces a different hash and old results are never
   silently reattributed. Per-criterion stats report FP/FN/parse-failures, `agreement_rate`,
   `verdict_flips` (fixtures whose judge status changed across repeats), and
   `mean_within_fixture_stdev` (stability computed **within** each fixture, never pooled across
   fixtures — different fixtures legitimately get different scores). Every individual trial
   outcome is preserved in the result for inspection.

## Graduation (later, not here)

A criterion graduates to gating only when calibration shows it reliable on the `holdout` split:
low false-positive/false-negative rates, no parse failures, low verdict-flip and within-fixture
stdev. Document the threshold and failure policy, then flip that criterion's `kind` from
`"advisory"` to `"gating"` in `llm_judge.py` — `evaluator.combine()` picks it up automatically.
