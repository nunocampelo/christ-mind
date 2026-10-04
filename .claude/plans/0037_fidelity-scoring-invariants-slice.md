# Slice: reliable fidelity matching and gold validation

## Outcome

Fidelity scoring maximizes correct pairs then total alignments, respects reference support,
and rejects invalid gold source IDs and mentions without rejecting invalid predictions.

## Layers touched

Only evaluation/scoring and root tests; no extraction, app, or domain behavior changes.

## Baseline

- BASELINE_SHA: `c3abed1dc630c70776e21b443928a6951b6cbfc9` (`git stash create` empty).
- Scratch: `/private/tmp/fidelity-slice-xliuv68h`; `baseline.json` and untracked copies.
- Pre-existing dirty set: `.claude/plans/0036_fidelity-scorer-matching-and-gold-validation.md`.
  Do not modify it. This contract independently records this execution.
- Evidence is deterministic scorer invariants, not extraction accuracy or an eval delta.
  Oracle output in `evaluation/claims/fidelity/runs/` is a supplementary sanity artifact;
  the gold remains unauthored. No reserved-report tuning.
- Supplementary baseline oracle: `evaluation/claims/fidelity/runs/20261004T133804Z.txt`.
  The externally created `20261004T133739Z.txt` artifact is out of scope.

## Change manifest

- Tracked: `evaluation/claims/fidelity/score_fidelity.py`, `tests/test_fidelity_score.py`.
- New: this contract; oracle evidence artifacts under the fidelity harness `runs/`.

## Evidence and acceptance

- Independently enumerate small bipartite assignments and compare the scorer's weighted
  matching objective `(correct pairs, total pairs)` against the exhaustive optimum.
- Exercise wrong-only rerouting and reassigning equally-correct partners to improve total
  matching; permute same-span entries and check stable diagnostics/correspondence.
- Wrong reference support gives no full credit and counts as unsupported for exhaustive
  gold; referent and abstention diagnostics remain independent of support.
- Reject mismatched shared and variant gold source IDs, including unchosen variants.
- Missing, empty, or repeated gold mentions raise `GoldAnchorError`; invalid predicted
  mentions get no referent credit and do not raise. Replace the old ambiguous-gold test.
- Preserve shared-span self-prediction, descriptions mapped through non-description
  correspondence, condition presence, and coherent variant selection regressions.
- Reproduce: `.venv/bin/python -m pytest tests/test_fidelity_score.py -q`,
  `.venv/bin/python -m pytest tests -q`, `.venv/bin/pyright`,
  `.venv/bin/python -m evaluation.claims.fidelity.run --oracle`.
- Suites: root `tests/` (no app adapters touched). No dict returns or init changes.

## Definition of done

Contract critique ready; independent final `REVIEW: clean` and `VALIDATION: pass`, all
declared checks green. One correction batch and one re-review maximum. Leave commit to user.

## Limitations

Matching optimizes per kind, descriptions after their targets; no joint cross-kind graph
optimization. This proves scorer mechanics, not extraction quality or authored-gold coverage.

## Execution

- Plan critic: ready; no product decisions or approval required.
- Initial verification: 44 scorer tests, 447 root tests, pyright clean, oracle passed.
- Matching uses polynomial rectangular assignment; correct-edge weight exceeds every
  possible total-pair gain. Small graph tests independently enumerate valid assignments.
- New checks cover wrong-only rerouting, equally-correct partner reassignment, support
  mismatches for resolved/unresolved references, all gold entry locations, and invalid
  mentions with valid-gold/invalid-prediction distinction.

- Independent first review: `REVIEW: clean`; validation: `VALIDATION: pass`.
- Validator independently checked 21,303 ternary graphs, 36 shared-span ordering cases;
  no failures. Its supplementary oracle artifact is `20261004T134218Z.txt`, byte-identical
  to baseline. Promoted its suggested exhaustive 3-by-3 check and rectangular 1-by-4/4-by-1
  cases into the persistent assignment tests for the final pass.
- Artifact manifest: `evaluation/claims/fidelity/runs/20261004T133804Z.txt`,
  `evaluation/claims/fidelity/runs/20261004T134105Z.txt`,
  `evaluation/claims/fidelity/runs/20261004T134218Z.txt`; any final validator oracle artifact
  is also evidence. Externally updated plan0036 remains outside this slice.
- Final pass: `REVIEW: clean`, `VALIDATION: pass`; 47 scorer tests, 450 root tests,
  pyright reports zero errors/warnings. Final oracle artifact:
  `evaluation/claims/fidelity/runs/20261004T134440Z.txt` (byte-identical to baseline).
- Acceptance criteria and completion gates met. Gold remains unauthored; no commit made.
