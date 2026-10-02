# Increment C — abstention-quality dimension for the black-box eval

## Context

The black-box eval currently cannot see **premature abstention** — the agent declining ("this
isn't in what I have", "touches only the edges") when the corpus *does* contain a sufficiently
direct answer. Run 6 proved the hole concretely: `highlight-chapter-one-024` **passed gating**
while scoring `answers_question: 0.2` — the agent claimed it had "nothing from the first
chapter" when chapter 1 is ~a fifth of the corpus (825 claims). It passed because the case has
no `must_include_*` anchor (so `required_evidence_present` is `not_evaluated`), the deterministic
checks pass, and the only dissent — the advisory judge — doesn't gate. The same false-abstention
pattern showed in `ego-definition-023` ("they don't give a direct account of what the ego
actually is" — while 25 "the ego is…" claims exist) and `mind-of-god-004b`.

Worse, the existing `epistemic_boundary` judge criterion scores abstention the **wrong
direction**: an agent that abstains scores *high* (it "acknowledged the gap"), so the current
judge actively *rewards* the failure. C adds a dimension that is aware of whether the gap is
*real* (via `corpus_reality`), making premature abstention a measured, visible signal.

This is a measurement-system increment (deepening what the harness can see), the prerequisite
for honestly evaluating the retrieval-side fixes B (concept-phrasing) and D (structural). It
does **not** change the agent.

## Decisions (locked)

- **Detection via the judge, not phrase-matching.** The agent's abstention wording is
  deliberately open-ended (`_BOUNDARY_VOICE`/`_INSUFFICIENT` in the agent prompt tell it to vary
  phrasing and avoid formulaic search-language), so a deterministic phrase-matcher would miss
  the very paraphrases the prompt encourages — false negatives exactly where C matters.
- **Advisory now, gate after validation.** `premature_abstention` starts **advisory** —
  recorded, scored, visible — consistent with the judge's founding principle ("LLM signals stay
  advisory until validated against human judgment on these fixtures", `llm_judge.py:1-7`). It
  graduates to gating in a later step once its abstention calls are checked against human
  judgment. C's value now is making abstention *measurable*; gating is a deliberate follow-on.
- **Fold into `LLMEvaluator`.** Evaluators can't read each other's outputs (each gets only
  `case`+`response`), so the corpus_reality↔abstention join must live where both are available:
  the judge evaluator, which has the `abstained` signal (its own call) and `case.corpus_reality`
  (the label). One file changed, no seam change; rides `combine`/`score.py`/`run_format.py`
  unchanged.

## Approach — all in `evaluation/blackbox/llm_judge.py`

1. **Judge emits an `abstained` signal.** Add `abstained` to the judge's returned JSON,
   described in `SYSTEM_PROMPT` as: *does the answer decline to answer / say the material isn't
   present / limit itself to peripheral material rather than answering the question?* Encode it
   as a **0.0/1.0 float, not a boolean** — `_parse_scores` (`llm_judge.py:81-91`) silently drops
   JSON booleans (`not isinstance(value, bool)` guard). The judge is scoring "did it abstain",
   not "should it have" — it stays a pure observation; the policy join is separate (below).

2. **`case.corpus_reality` stays evaluator-side — do NOT send it to the judge.** The judge's
   job is a *pure observation* ("did the answer abstain?"), not a verdict ("was it right to?").
   Sending `corpus_reality` would risk collapsing the former into the latter — and the whole
   design is to derive "premature" from two *independent* signals (the judge's `abstained` and
   the fixture's `corpus_reality`). So `_user_prompt` is left unchanged; the judge never sees
   the label.

3. **Emit a `premature_abstention` advisory criterion.** In `LLMEvaluator.evaluate`, after
   parsing scores, compute one extra `CriterionResult` — the policy join of the two independent
   signals:
   - `not_evaluated` when `case.corpus_reality != "sufficient"`, full stop. (Narrowly scoped:
     the criterion measures *one* thing — abstaining when the corpus can answer. It makes no
     claim about whether abstention was well-expressed in the `absent`/`insufficient` cases;
     those are simply out of this criterion's scope. Mirrors `_required_evidence_present`'s
     not-applicable pattern.)
   - Otherwise **advisory**, `score = abstained` (1.0 = fully abstained = worst),
     `status = "fail" if abstained >= _PASS_THRESHOLD else "pass"`, `detail` naming the
     premature abstention. Judge unreachable/unparseable/`abstained` missing → `not_evaluated`
     (never a spurious signal), consistent with the existing degrade path (`llm_judge.py:59-60`).

4. **Revise the module docstring.** It currently says "always advisory". That stays *true* for
   now (premature_abstention is advisory), but note it is the criterion *intended* to gate once
   validated — so the docstring should say the judge's criteria are advisory *pending
   validation*, with `premature_abstention` the first candidate for promotion, rather than
   "never gate" absolutely.

No change to `evaluator.py` (a new advisory criterion rides `combine` untouched), `score.py`
(`advisory_means()` picks it up by name automatically), `run_format.py` (`CaseLine` serializes
all criteria verbatim), or `run.py`.

## Files

- `evaluation/blackbox/llm_judge.py` — add `abstained` to `SYSTEM_PROMPT` + `_CRITERIA`-adjacent
  handling; emit the `premature_abstention` advisory criterion in `evaluate`; revise docstring.
- `tests/test_blackbox_llm_judge.py` — the criterion's contract with a **scripted** `Complete`
  (no live LLM), the full truth table:

  | corpus_reality | abstained | premature_abstention |
  | -------------- | --------- | -------------------- |
  | sufficient | 1.0 | advisory **fail** (score 1.0) |
  | sufficient | 0.0 | advisory **pass** |
  | absent | 1.0 | **not_evaluated** |
  | insufficient | 1.0 | **not_evaluated** |
  | sufficient | missing / malformed reply | **not_evaluated** |

  The last row is the load-bearing one: a judge failure degrades to "we don't know," **never**
  to "the agent abstained." Reuse the existing scripted-reply fixtures; assert the *other*
  advisory criteria still parse alongside `abstained` (additive, non-breaking).

## Verification

1. `.venv/bin/python -m pytest tests apps/agent/tests apps/mcp-server/tests -q` — new + existing
   green (the existing judge tests must still pass; `abstained` is additive).
2. `.venv/bin/pyright` — clean.
3. **Contract check (no live LLM):** a scripted judge returning `{"abstained": 1.0, ...}` on a
   `sufficient` case yields a `premature_abstention` advisory `fail`; the same on an `absent`
   case yields `not_evaluated`.
4. **Black-box run (evidence):** with the stack up, `python -m evaluation.blackbox.run --live
   --record`. Expect `highlight-chapter-one-024`, and any run where the agent prematurely
   abstains on `mind-of-god-004b`/`ego-definition-023`, to now carry a `premature_abstention`
   advisory **fail** — the failure the harness was previously blind to is now recorded and
   visible in the run's per-criterion output and `advisory_means()`. Gating totals are
   unchanged (advisory doesn't gate yet); the point is the signal now exists to measure B/D
   against and to validate before promotion.

## Out of scope

- **Gating on `premature_abstention`** — deferred until its calls are validated against human
  judgment (the deliberate advisory→gating graduation). That validation, and promoting the
  criterion, is a distinct follow-on.
- **Fixing the abstention** (retrieval-side) — that's B (concept-phrasing query expansion) and
  D (structural queries); C only *measures* it.
- **A second LLM call / separate AbstentionEvaluator** — folded into the existing judge call, no
  extra cost.
- Any agent-prompt change.
