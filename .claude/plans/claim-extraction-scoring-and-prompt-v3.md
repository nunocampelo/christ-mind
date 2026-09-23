# Claim extraction: scoring fixes and prompt v3

Run 1: `evaluation/runs/20260923T002530Z.jsonl`, prompt v2, dev split, via
`infrastructure.llm.anthropic_proxy`.

## Where run 1 landed

| Matching                                                       | Matched | P    | R    |
| -------------------------------------------------------------- | ------- | ---- | ---- |
| Exact (current scorer)                                         | 26      | 0.30 | 0.31 |
| + ignore articles, quote style, punctuation                    | 38      | 0.44 | 0.46 |
| + phrase containment, overlapping evidence, same predicate     | 54      | 0.62 | 0.65 |

The two lower rows are one-off estimates from a scratch script, not the scorer.

What already works: 0 rejected candidates (every quote exact), polarity right on
every negation, mode and attribution right on almost every matched claim, and 4.8
claims per passage against the gold set's 4.6.

Most of the gap is surface wording the scorer treats as a miss. The rest is a
small set of real errors, listed in step 3, and predicate choices where the gold
set and the model reasonably disagree, listed in step 4.

## Steps

Each step is its own commit, and each one either changes how scores are measured
or changes the scores themselves, never both at once. That way every change in the
numbers can be traced to its cause.

### 1. Scorer: normalise wording, add a relaxed tier

`evaluation/claims/score.py`

- `_normalize` for all tiers:
  - lowercase;
  - fold curly quotes and apostrophes (`’ ‘ “ ”`) to straight;
  - strip punctuation (`. , ? ! "`);
  - drop leading determiners (`the a an this that their his its`).
- Keep quantifiers (`all`, `no`) and modifiers (`particularly`, `Himself`). Dropping
  them is a judgment about meaning, not formatting, and a matched claim would then
  hide it.
- Add a `relaxed` `ClaimScore` to `ScoreReport`. A predicted and a gold claim match
  if:
  - they have the same source and predicate;
  - their evidence spans overlap;
  - for subject and object alike, one normalised phrase contains the other;
  - both objects are null, or neither is.
- Pair claims one-to-one, strict matches first, reusing `_pair_loose_matches`'
  approach, so one broad prediction can't match three gold claims.
- Report exact, strict and relaxed side by side. Relaxed is the headline number for
  tuning; strict is the one that must eventually rise.
- Tests:
  - article and quote differences now match exactly;
  - containment matches only when the evidence overlaps;
  - one prediction can't satisfy two gold claims;
  - a reversed `causes` does not match under relaxed.
- Re-score run 1 with the new scorer (no new model call) and record the numbers
  here. That re-scored run 1 is the baseline from now on.

### 2. Near-miss report as a real tool

`evaluation/claims/near_miss.py`: `python -m evaluation.claims.near_miss <run file>`

- For each unmatched gold claim, show the predicted claim from the same source whose
  evidence overlaps it most, and which fields differ (subject, predicate, object,
  polarity, mode, attribution).
- End with a tally by differing field. This is the scratch script from run 1's
  analysis, made permanent. It's how steps 3 and 4 get checked on every run.
- Also list predictions that overlap no gold evidence at all. Those are either
  extra claims or gaps in the gold set, and deciding which needs a person to look.

### 3. Prompt v3: fix the real errors

`src/application/extraction/prompt.py`, bump `PROMPT_VERSION` to `"3"`

Run 1 errors, each needing a worked example rather than a restated rule, since the
rule was already there:

- **`causes` direction reversed (3 of 3 inverted forms):**
  - "interpretation arose out of misprojections" → subject `combined misprojections…`
  - "unwillingness arose from escape value" → subject `escape value`
  - "I was NOT punished because YOU were bad" → subject `your being bad`, `negated`

  Add an explicit instruction: for `causes`, the subject is the cause. "X arose
  from Y", "X because Y" and "X is the result of Y" all put Y first.
- **Relative clause swapped subject and object:** "a point which many very sincere
  Christians have misunderstood" → subject `many very sincere Christians`.
- **Double negative reproduced:** "No-one who is free of the scarcity-error could
  POSSIBLY make this mistake" → subject `one who is free of the scarcity-error`,
  `negated`. Add this sentence itself as the example.
- **`makes` on an ordinary "make":** limit `makes`/`creates` to the Course's sense
  (making by the ego or perception vs. creating by spirit). "Make a mistake" is
  `other`.
- **Embedded propositions not extracted:** "reawaken the awareness that the Spirit,
  not the body, is the altar" should also give `Spirit is altar of truth` and `body
  is not altar of truth`. New rule: a "that X" clause after
  awareness/belief/recognition/idea is extracted as its own claim(s). Its
  attribution comes from the frame: a "fallacious belief that X" makes X `others`.
- **Housekeeping:**
  - make the "did NOT cause" example's verb_phrase match the gold set ("did NOT
    cause", not "caused");
  - rewrap the over-long line in the negation rule.

Success: in step 2's report, none of these five error types appears on the dev
split.

### 4. Settle predicate conventions (decisions for the maintainer)

Each of these is a convention, not a fact about the text. Whichever way each one
goes, the gold set and the prompt change together in one commit.

| Text                                   | Gold now    | Model (run 1) | Recommendation |
| -------------------------------------- | ----------- | ------------- | -------------- |
| "are natural expressions of"           | `expresses` | `is`          | keep `expresses`: it's the predicate's purpose |
| "Miracles are healing"                 | `causes`    | `is`          | switch gold to `is`; the "effect adjective → causes" rule is too clever |
| "release the future"                   | `other`     | `causes`      | keep `other`; "release" isn't causation |
| "love is received through prayer"      | `other`     | `requires`    | keep `other`; a channel isn't a precondition |

Also decide **where the verb ends**: "Prayer | is the medium of | miracles" vs.
"prayer | is | medium of miracles". Recommendation: for copulas (`is`, `are`), the
verb is just the copula and the whole noun phrase is the object. That matches most
of the gold set, and relaxed matching tolerates the rest.

### 5. Run v3 twice, then decide

- Two dev runs with identical settings. The difference between them is the noise
  floor: don't act on a change smaller than it.
- Record both runs' exact, strict and relaxed scores in the results log below.
- Next step depends on the result:
  - **Relaxed R ≥ ~0.8 and no step 3 error types:** run the holdout once and record
    it. Then extend gold labelling to more passages, prioritising ones with
    `ego` attribution, since there are none yet.
  - **Otherwise:** iterate on the prompt against dev only, one change per run.

## Not in this plan

- Entity resolution ("miracle" vs "miracles"). Relaxed matching covers what's
  needed for scoring; resolving entities is its own increment.
- A second provider. It's worth comparing once v3 is stable. Nothing in the runner
  needs to change for it.
- Growing the predicate list. `other` is still about a third of gold claims, but
  change it only once step 2's report shows which `other` verbs recur across more
  passages than T1.1 and T3.2.

## Results log

| Run | Prompt | Split | Exact P/R | Strict P/R | Relaxed P/R | Notes |
| --- | ------ | ----- | --------- | ---------- | ----------- | ----- |
| 20260923T002530Z | v2 | dev | 0.30 / 0.31 | 0.29 / 0.30 | — | before step 1 |
