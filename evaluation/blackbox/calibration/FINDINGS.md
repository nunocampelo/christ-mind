# Item 3 — judge validation (2026-10-02)

Decision: validation does not authorize gating. Do **not** graduate
`semantic_grounding` or `synthesis_fidelity`. `premature_abstention` and
`answers_question` are the closest candidates, pending later holdout validation and an
explicit threshold and unavailable-judge policy. All criteria remain advisory.

The original tune run, `results/20261001T223814Z.jsonl`, used rubric 1.2
(`9fd5b0278b99dc5b`) at threshold 0.6. It passed the wrong-marker God control at mean
grounding 0.84 despite the explicit marker-scope rule. Its aggregate counts are
superseded by the corrected-label rerun below; the original artifact remains intact.

## Evidence delivery check

Exercised `LLMEvaluator.evaluate` with a capturing completion function on the tune
wrong-marker control, using the normal fixture loader and case conversion. The exact
1.2 system prompt and all 12 nonempty, full `evidence_context` paragraphs reached
the completion boundary, paired with their claim IDs. No clause fallback occurred.
The proxy adapter forwards this user string directly as the Messages API user content.

The assertion "God is the Giver of life" carries `3420d0187622a6e6`, whose paragraph
states "Only the Oneness of knowledge is conflictless" and does not establish God as
Giver of life. The supporting paragraph is also supplied under `cdad6eaa77d2a85e`.
The control therefore tests the intended distinction: support elsewhere in the input
does not license the attached marker. Empty evidence context is ruled out for this
tune control. This establishes a grading failure with the evidence supplied, but does
not establish that stronger wording alone will fix it.

## Label and provenance corrections

At the user's direction, `ctrl-premature-abstention-015 / semantic_grounding` is now
`not_applicable`: the flat abstention makes no substantive sourced assertion.
`ctrl-irrelevant-salvation-015 / epistemic_boundary` and `/ synthesis_fidelity` are
now `not_applicable`: this control targets `answers_question`, without independently
approved expectations for those two dimensions. Other verdicts are preserved.

The header retains `draft_judge_prompt_version: 1.1` and adds
`approved_judge_prompt_version: 1.2` plus the label-revision rationale. New results
pin the revised fixtures hash. All seven development-holdout rows were preserved
byte-for-byte and were not judged. Their joined-row SHA-256 (newline terminated) is
`c158cba04c82f47996a2ef5ac83fb4d4aa31e04a3ac3746ad5a65ddf0722c4ea`.

## Follow-on decision

Use a separate grounding diagnostic to assess assertions against their attached
markers and record reasons, then tune on this split. Do not change the rubric during
this corrected-label rerun. Evaluate the development holdout only after the rubric
is frozen; its previously inspected answers do not constitute independent validation.

## Corrected tune rerun

Completed in `results/20261002T051802Z.jsonl`: 12 frozen tune fixtures, five repeats
each, unchanged model and rubric 1.2. Fixtures SHA-256:
`0d9a674c476ec680f320f6e905a47b84bfd8de04a786f2f977033e7d36a78bbc`.

| Criterion | Trials | Agree | FP | FN | Unavailable/unparsed | Verdict flips |
|---|---:|---:|---:|---:|---:|---:|
| answers_question | 60 | 55 | 0 | 0 | 5 | 2 |
| epistemic_boundary | 55 | 50 | 0 | 0 | 5 | 2 |
| interpretation_marked | 60 | 50 | 5 | 0 | 5 | 2 |
| premature_abstention | 30 | 30 | 0 | 0 | 0 | 0 |
| semantic_grounding | 55 | 30 | 20 | 0 | 5 | 2 |
| synthesis_fidelity | 55 | 37 | 12 | 1 | 5 | 3 |

The wrong-marker control again passed grounding on every scored repeat:
0.85, 0.80, 0.85 (mean 0.833); two repeats were `not_evaluated`. Three unsupported-
attribute repeats were also `not_evaluated`. The harness calls these `parse_failure`,
but does not retain enough detail to distinguish provider failures from parsing
failures. Thus the drop from 24 to 20 grounding FPs is **not** evidence of improved
detection: failed judge calls removed opportunities to detect or miss bad answers.
The corrected labels remove the manufactured grounding FN and the disputed
irrelevant-answer fidelity/boundary comparisons.

Item 3 is closed as validation, with no criterion promoted. The run supports the
decision above, while exposing judge availability as another graduation concern.
Verification: 13 calibration fixture/harness tests passed; pyright reported zero
errors. The sandbox-blocked first attempt was interrupted without a result artifact;
only the completed proxy-access run is recorded here.

## Rubric 1.3 — code-side grounding floor (2026-10-02)

The 1.2 finding was that the judge detects a mis-cited marker per-assertion but then
returns the *average* grounded fraction (~0.833), clearing 0.6, so wrong-marker
controls pass. 1.3 takes aggregation out of the model: the judge returns one element
per substantive assertion as a **verbatim span** of the answer plus a
`supported_by_its_markers` bool, and Python computes the verdict — grounding fails iff
any element is unsupported, and an element whose span carries no marker is forced
ungrounded in code regardless of the returned bool.

Anchoring was reworked mid-pass. 1.3's first form asked the model for `char_start`/
`char_end` offsets and required `answer[start:end] == assertion`. The live judge could
not satisfy it: it copies the assertion text verbatim (9/9 exact substrings on both
god-004 fixtures) but miscounts offsets by a few characters every call, so the floor
was rejected as `parse_failure` on **50 of 55** scored repeats (artifact
`results/20261002T060346Z.jsonl`, preserved as evidence) and never ran. The fix drops
offsets from the contract: Python recovers each span by locating the verbatim
`assertion` substring, resolving a repeated span only when the full non-overlapping
marker partition yields exactly one assignment (several valid assignments →
`incomplete_coverage`, never a guessed pick). Markers are still read authoritatively
from the recovered span.

Result in `results/20261002T062115Z.jsonl`: 12 frozen tune fixtures, five repeats each,
unchanged model, rubric **1.3** (hash `275a9cc5683db397`). Fixtures SHA-256:
`0d9a674c476ec680f320f6e905a47b84bfd8de04a786f2f977033e7d36a78bbc`.

| Criterion | Trials | Agree | FP | FN | provider_fail | parse_fail | incomplete | unscored | Verdict flips |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| answers_question | 60 | 60 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| epistemic_boundary | 55 | 55 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| interpretation_marked | 60 | 55 | 5 | 0 | 0 | 0 | 0 | 0 | 0 |
| premature_abstention | 30 | 30 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| semantic_grounding | 55 | 31 | 3 | 16 | 0 | 0 | 0 | 5 | 4 |
| synthesis_fidelity | 55 | 35 | 15 | 5 | 0 | 0 | 0 | 0 | 0 |

The floor now **runs** — grounding `parse_fail` 50 → 0. Against the 1.2 corrected rerun
(grounding FP 20, FN 0, with 5 confounded `not_evaluated`), grounding FP falls **20 → 3**
and this time the drop is real, not an artifact of failed calls removing detection
opportunities. The acceptance holds on the controls:

- `ctrl-wrong-marker-god-004` **fails** every repeat (0.889 ×4, 0.8 ×1), and the failing
  element is the mis-cited `[3420d0187622a6e6]` clause — targeted, not indiscriminate.
- `ctrl-unsupported-attribute-god-004` **fails** every repeat (0.9), on the unsupported
  attribute clause.

But grounding FN jumped **0 → 16**, and `real-god-description-004` — the real positive
the acceptance requires to pass — **fails 4 of 5** (passes 1). The 16 FN split into two
distinct causes, neither a floor-logic error:

1. **Clarification/abstention over-extraction (5 FN).** `real-help-me-016` is a
   clarification request citing nothing (human: pass). The rubric says to skip
   meta/connective sentences, but the judge extracts "nothing specific has been gathered
   yet for me to draw on" as a substantive assertion; with no marker it is forced
   ungrounded → score 0.0. The sibling `ctrl-clarification-016` ("Yes. What would you
   like help with?") correctly routes to the no-markers `not_evaluated`/`unscored` path
   (5/5) — the difference is purely what the judge chose to extract.
2. **Uncited-assertion floor × judge extraction variance (11 FN).**
   `real-god-description-004`, `real-love-fear-relation-010`, `real-mind-of-god-004b`
   flip across repeats (grounding `flips 4`); scores like 0.9/0.889/0.857 mean a single
   extra assertion was forced false on some repeats. The floor's "any uncited substantive
   assertion ⇒ fail" is stricter than the human notion of grounding, which tolerates an
   uncited supporting clause, and the judge extracts a different assertion set each run.

So the fix is sound and the lever worked where it was aimed (controls fail, targeted at
the right clause), but grounding is **not gate-ready**: the FN are driven by (a) the
model's inconsistent decision of what counts as a substantive/extractable assertion and
(b) the floor being stricter on uncited clauses than the human label. Both are rubric/
label questions, not floor bugs — resolving them must not loosen the floor itself (that
would reopen the citation-integrity hole). `semantic_grounding` stays advisory.
`synthesis_fidelity` is unchanged by this work (FP 15) as expected — the per-marker floor
does not touch its holistic judgment.

Holdout untouched: the 7 holdout fixtures are byte-for-byte unchanged and unjudged;
their joined-row SHA-256 (newline terminated) is still
`c158cba04c82f47996a2ef5ac83fb4d4aa31e04a3ac3746ad5a65ddf0722c4ea`. Verification: 366
tests pass, pyright reports zero errors. No commit — changes staged.
