# Review of the 5 judge-flagged answers (plan item 2) — revised

## Post-contract re-judgement (run `20261001T210515Z`, model claude-4.8-opus)

After the citation-scope decision (a marker licenses the claim's **source paragraph**, not
just the clause — support, not proximity), the answer prompts and the LLM judge were updated
to state and grade against that contract, and `capture_flagged.py` was re-run. The scope-audit
question stays the same, but the judge now sees each claim's full `evidence_context`.

Result — the earlier flagging was an artifact of grading against the clause the agent was never
limited to. With the judge seeing the paragraph:

| case | semantic_grounding (mean, range) | synthesis_fidelity (mean, range) |
|---|---|---|
| god-description-004 | 0.93, [0.90, 0.95] | 0.86, [0.85, 0.90] |
| miracle-worker-role-008 | 1.00, [1.00, 1.00] | 1.00, [1.00, 1.00] |
| atonement-definition-022 | 0.96, [0.95, 1.00] | 0.91, [0.90, 0.95] |
| ego-definition-023 | 1.00, [1.00, 1.00] | 0.97, [0.95, 1.00] |
| mind-definition-025 | 1.00, [1.00, 1.00] | 0.95, [0.95, 0.95] |

Every case now scores **well above 0.6** on both grounding criteria (stdev ≤ 0.024). The three
that previously sat on or under the cutoff — god-004 (was 0.60), atonement-022 (was 0.62),
mind-025 (was 0.38) — are now 0.93, 0.96, 1.00. The judge remains stable on a frozen answer;
what moved is *what it grades against*.

Scope-audit buckets across the 5 cases (new frozen answers, so totals differ from the prior
run): **clause_supported 21, passage_supported_outside_claim 36, no_source_support 0.** The 2
prior `no_source_support` (the atonement-022 two-marker audit artifact) did not recur. Under the
decided contract the 36 passage-outside-claim assertions are **valid** — paragraph-supported,
preserving attribution and polarity — not fabrication. No hard defect in any of the five.

**Conclusion:** the decided paragraph-licenses contract resolves the "18 cases" question — graded
against the paragraph the marker actually licenses, the passage-outside-claim assertions are
grounded. The grounding check **stays advisory** (item 3 calibration against pass AND fail
examples is still owed); this run only confirms the contract change is coherent and that these
five hold no fabrication.

---

## Pre-contract review (retained for the before/after contrast)

Data: `review/flagged-20261001T204223Z.jsonl`, from `capture_flagged.py` (header carries
run_id / model / agent_url / judge_repeats). Design, corrected after review:

- Each case asked **once** and the answer + full evidence **frozen**; the suite judge then
  re-run **5×** on that frozen answer. Score spread therefore measures judge variability
  alone — not answer regeneration. (The first attempt regenerated answers between judgments
  and conflated the two; its file was discarded.)
- Each cited claim saved with its full `evidence_context` (the source paragraph the agent was
  shown) and offsets — not just the short clause. A separate **scope audit** sees the passage
  and sorts each marked assertion into three buckets (below).

## Finding A — the judge is stable on a frozen answer; the 0.6 threshold is not safe to gate

Re-judging the frozen answers, every criterion on every case has **stdev ≤ 0.05**. The earlier
0.2→0.85 swing I reported was the *answer* changing between runs, not judge noise — retracted.

But stability ≠ gateable, because borderline means sit **on** the 0.6 cutoff:

| case | semantic_grounding (mean, range) | synthesis_fidelity (mean, range) |
|---|---|---|
| god-description-004 | 0.60, [0.60, 0.60] | 0.67, [0.65, 0.70] |
| miracle-worker-role-008 | 0.84, [0.80, 0.85] | 0.85, [0.85, 0.85] |
| atonement-definition-022 | 0.62, [0.60, 0.70] | 0.72, [0.70, 0.75] |
| ego-definition-023 | 0.73, [0.70, 0.80] | 0.72, [0.70, 0.75] |
| mind-definition-025 | 0.38, [0.30, 0.40] | 0.38, [0.30, 0.40] |

god-004 (0.60) and atonement-022 (0.62, range crossing 0.60) sit right at the cutoff — they
flip pass/fail run-to-run even with a stable judge. miracle-008 and ego-023 are clearly above;
mind-025 clearly below. So **a straight ≥0.6 scalar gate would flap on borderline cases.** Note
too: three of these cases scored *above* 0.6 this run — the recorded run's "5 flagged" set does
not reproduce as a stable 5.

## Finding B — the dominant pattern is citation SCOPE, not fabrication

Scope-audit bucket totals across the 5 cases (each marked assertion classified once per marker):

- **clause_supported: 25** — assertion is in the cited claim's own clause.
- **passage_supported_outside_claim: 18** — assertion is NOT in the clause but IS in that
  claim's source paragraph (true to the source, broader than the claim the marker names).
- **no_source_support: 2** — and both are an **audit artifact, not fabrication**: a single
  two-marker sentence in atonement-022 ("Correction belongs only at the level of the mind, and
  it is a matter of your will" `[07f1f3225efe96ba][74587a488f61f27f]`) was decomposed and each
  half cross-checked against *both* markers; each half matched its correct marker
  (clause/passage-supported) and mismatched the other (scored no_source_support). The content
  is in the sources.

So, correcting the earlier verdict: **no clean fabrication was found in any of the 5 cases.**
The statements I previously called "invented" — "the mind is naturally abstract" (mind-025, in
`t4-7-1`), "the maximal service one individual can render another" (miracle-008, in `t1-1-18`),
"retains its creative potential"/"tyrannous control" (`t1-1-66`), Atonement-as-principle /
healing-as-release-from-fear (atonement-022, in `t2-2-1`) — are all present in the source
paragraphs the agent received. The earlier verdict rested on a clause-only view the agent never
had.

## The real open question (decide before any gate)

The agent's answer prompt (`domain/prompt.py:205-213`) shows the whole PASSAGE but states the
cited **claim** (not the passage) is the licence: "it is context for reading the claims, never
a licence to broaden them." The 18 `passage_supported_outside_claim` assertions are the system
drawing on the shown passage while attaching a narrower claim's marker. Whether that is a defect
depends on an undecided policy:

**Does a citation marker authorize the claim's span, or its containing passage?**

- If **claim span**: those 18 are a real citation-scope defect — fix in the answer prompt
  (require the marked claim to support the assertion; cite the passage explicitly if drawing on
  it) or by surfacing passage-level citation as a first-class thing.
- If **containing passage**: those 18 are fine, and the prompt's current wording is the thing
  that's wrong (it forbids what we actually want). Only genuine `no_source_support` would be a
  defect — of which this review found none.

This must be decided explicitly. Until then the grounding check stays **advisory**.

## What this does and does not establish

- Does NOT establish a synthesis/grounding *defect*: the dominant pattern is scope, which is
  undecided policy, and no fabrication was found.
- Does NOT establish retrieval is adequate per-assertion. `required_evidence_present` passing +
  `unused_claim_ids` only show the gold-required claims were present and some gathered claims
  went uncited; neither proves a suitable claim was supplied for *every* assertion. The
  `passage_supported_outside_claim` cases are consistent with "the supporting content was in the
  passage but not as its own retrieved claim" — i.e. a possible *claim-granularity/retrieval*
  gap, not only an answer-prompt gap. Left open.

## For items 3 and 4

- **Item 3 (judge → gating):** do not gate the raw ≥0.6 scalar (borderline flap). Calibrate
  against frozen pass AND fail examples (this file is the start). If anything gates, prefer a
  per-assertion check tied to the **decided** scope policy, not the scalar. Consider folding a
  reasoning field into the judge so runs are self-reviewable (the suite judge returns only
  numbers today).
- **Item 4 / answer prompt:** blocked on the scope decision above. Do not loosen the citation
  licence as a reflex (would mask real fabrication if any later appears); do not tighten the
  prompt to forbid passage use until we've decided passage use is actually wrong.

## Caveat

One live ask per case (answers frozen, then judged 5×). The judge-variability numbers are solid
for *this* frozen answer; a different answer would need its own frozen re-judging. The scope
audit is itself one LLM pass and should be spot-checked by hand (the atonement-022 artifact
above is an example of why). Re-run `capture_flagged.py` to refresh.
