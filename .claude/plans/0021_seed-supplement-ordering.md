# Increment — front-load definitional supplements in the seed batch

## Context

#12 (meta-question) and B1 (concept-question) supplement the orchestrator's seed query list
with the subject the question is actually about ("course", "ego"). Two confirmation runs +
ground-truth extraction from `conversation_messages` (question → agent `message_json` with
`cited_claims`) showed the supplement was **wasted by ordering**:

- The orchestrator built the list as `concepts + supplements` (supplements *last*).
  `find_claims_batch` interleaves round-robin *in query order*, so a supplement seated last
  lands its top result near the `global_limit=12` cut.
- Ground truth: `ego` (11 mapped concepts) and `course-about` (12 concepts) did **not** cite
  their definitions — the concept count filled the 12-slot budget before the last-seated
  supplement contributed. `salvation` (def ranks shallow) and `atonement` cited theirs fine.
- Not synthesis: the agent reliably cites definitions when they rank shallow.

Fix: **seed supplements first**, so their (definitional) top result lands in the round-robin's
first slots. Proven deterministically: ego's `t3-5-3` and course's `t1-0-1` both move from
position 10 (cut) → position 0.

## Change (implemented)

`apps/agent/.../domain/orchestrator.py` — reorder the deduped seed list to supplements-first:
```python
queries = _dedupe(
    meta_query_terms(request.situation)
    + concept_query_terms(request.situation)
    + concepts
)
```
- `find_claims_batch` untouched (its round-robin balance is correct; this only orders input).
- No-op when there's no supplement (life situations): order unchanged.
- Dedup behaviour change: a supplement coinciding with a mapped concept now wins the dedup
  (its spelling is kept) — same normalized term, harmless; covered by test.

Tests updated in `apps/agent/tests/test_orchestrator.py` for the new order (supplement first):
meta ("course" first), concept ("ego" first), and the dedup case (supplement spelling wins).

## Scope boundary — what this does NOT fix

`God` ("how does God think?"): its definition `t3-6-9` ranks **18** for the subject "God"
(301 matches) — front-loading "God" wouldn't surface it. That is **B2 (high-frequency-subject
ranking-depth)**, deferred, and its persistence after this fix is the expected confirmation of
the split: `ego`/`course-about` = ordering (fixed here), `God` = ranking-depth (B2).

## Verification

1. `pytest tests apps/agent/tests apps/mcp-server/tests -q` — 342 green. ✓
2. `pyright` — clean. ✓
3. Mechanism (no LLM): at the real 11-concept seed shape, `ego`'s `t3-5-3` is now position 0
   (was 10). ✓
4. Black-box `--live --record`: expect `ego-definition-023` and `course-about-006` to cite
   their definition (`required_evidence_present` satisfiable, `premature_abstention` drops for
   ego); `mind-of-god-004b` may still fail (B2). Read across a couple runs per the noise floor;
   watch for regressions (front-loading only displaces a *later* round-robin slot, and only
   when a supplement fires).

## Out of scope

B2 (God ranking-depth); any `find_claims_batch` change; promoting C's `premature_abstention`
to gating.
