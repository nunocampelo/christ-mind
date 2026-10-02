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
