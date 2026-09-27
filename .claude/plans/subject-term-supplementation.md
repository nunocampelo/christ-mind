# Increment B1 — subject-term supplementation for concept questions

## Context

The black-box eval (now with the C abstention-quality dimension) shows the agent
**prematurely abstaining** on direct concept questions whose answer is in the corpus.
`ego-definition-023` ("What is the ego?") abstained ("touches the ego only glancingly…
they don't give us a definition") — while 25 "the ego is…" claims exist. Diagnosed
precisely:

- The failure is **not** retrieval quality and **not** absence: `find_claims("ego")` returns
  the definitional "the ego is a man-made attempt to perceive himself" at **rank 0** (three
  ego-definitions in the top 3).
- The failure is **query formulation**: the mapper maps "What is the ego?" to *situational
  themes* (the run cited "foolish journey", "separation", "fear"), and the orchestrator's
  seed batch searches only those — it never searches the question's own subject, `"ego"`. So
  the definition is reachable but never queried.

This is **the same class #12 fixed for "the Course"**: the question's subject-noun is the
effective retrieval term, but the mapper emits contents/themes instead. B1 generalizes #12's
seed-supplement idea from a fixed referent to the **question's own subject**.

**Scope note — B is deliberately split.** B1 (this increment) = subject-term supplement,
fixes the tractable `ego`-style case. **B2 (separate, deferred)** = high-frequency-subject
disambiguation: `find_claims("God")` matches 200+ claims and the direct "God's Thoughts"
targets sink below the top 12 — a *ranking-depth* problem, not query coverage, that belongs
with #11 ranking work and may need embeddings. Do **not** pull B2 or embeddings into B1.
Crucially, **the God case remaining imperfect after B1 is the expected, informative result** —
it empirically confirms the split (ego = coverage, God = ranking-depth).

## Approach

**Insertion point: the orchestrator seed batch** — exactly where #12's `meta_query_terms`
already supplements (`orchestrator.py`, the `_dedupe(concepts + meta_query_terms(...))` line).
B1 adds a sibling supplement from a new detector. Reasons are #12's, unchanged: the mapper is
the expensive lever (`MAP_VERSION` + gold relabel), the decision prompt is the wrong lever
(anti-thrash guidance), the seed batch is deterministic and already merges a list.

### The subject detector

A new pure module `apps/agent/src/mind_of_christ_agent/domain/concept_question.py`, sibling to
`meta_question.py`:

```python
def concept_query_terms(text: str) -> list[str]:   # [] or ["<subject>"]
```

- Fires on **bare-subject definitional questions**: "what is/are X", "what's X",
  "describe X", "define X" — capturing X (article stripped, punctuation trimmed). Prototype
  verified: extracts `ego` / `salvation` / `guilt` / `Holy Spirit` correctly.
- Does **not** fire on: how/application questions ("how can I forgive my mother"), life
  situations, relationship questions ("how are love and fear related"), or content-*about*
  questions ("what does the Course say about forgiveness" — a separate topic after a
  referent, not a bare subject). Prototype verified silent on all of these.
- **Guard: only supplement if the extracted subject actually matches claims.** The detector
  (or the orchestrator wiring) checks the term yields ≥1 `find_claims` hit before adding it —
  so a subject the corpus doesn't contain injects nothing (no noise, no off-target query).
  This keeps B1 from degrading the `insufficient`/`absent` cases.
- Overlap with #12 is fine and handled by dedup: "What is the Course?" is caught by *both*
  `meta_query_terms` (→"course") and this (→"course"); the existing `_dedupe` collapses them.

### Orchestrator wiring

Extend the existing supplement line to include the new terms, deduped:
```python
queries = _dedupe(concepts + meta_query_terms(request.situation) + concept_query_terms(request.situation))
```
`searched_terms` and the status text already derive from the final deduped list (#12 work).
No other orchestrator change.

## Files

- `apps/agent/src/mind_of_christ_agent/domain/concept_question.py` (new) —
  `concept_query_terms(text) -> list[str]`, the bare-subject definitional detector + subject
  extraction + corpus-match guard. Pure/deterministic, mirroring `meta_question.py`.
- `apps/agent/src/mind_of_christ_agent/domain/orchestrator.py` — one line: add
  `concept_query_terms(request.situation)` to the deduped seed `queries`.
- `apps/agent/tests/test_concept_question.py` (new) — the contract: fires on "what is the
  ego / salvation / guilt", "describe the Holy Spirit" → the extracted subject; silent on
  how/application/relationship/content-about/life-situation questions; returns `[]` when the
  extracted subject matches no claims (the guard).
- `apps/agent/tests/test_orchestrator.py` — a case asserting "What is the ego?" adds `ego` to
  the seed `queries`; confirm non-concept questions' args are unchanged; confirm dedup when a
  subject coincides with a mapped concept or with #12's term.

**Untouched:** `map_situation`/`MAP_VERSION`/mapping gold, the decision prompt, `find_claims`/
ranking, the eval (`ego-definition-023` already exists and encodes the expectation). No
black-box gold change.

## Verification

1. `.venv/bin/python -m pytest tests apps/agent/tests apps/mcp-server/tests -q` — new +
   existing green (esp. the `test_orchestrator.py` seed-arg assertions).
2. `.venv/bin/pyright` — clean.
3. **Mechanism check (no LLM):** `concept_query_terms("What is the ego?") == ["ego"]`;
   `== []` for "How can I forgive my mother?", "How are love and fear related?", "What does
   the Course say about forgiveness?", and for a bare subject the corpus lacks.
4. **Black-box run (evidence, per the C dimension):** with the stack up,
   `python -m evaluation.blackbox.run --live --record`. The hypothesis, measured by C:
   **`ego-definition-023`'s `premature_abstention` should improve** (the definition now enters
   the seed → the agent has it to cite) while **`mind-of-god-004b` may well remain a
   `premature_abstention` fail** — and that persistence is the *expected* confirmation that
   God is a B2 ranking-depth problem, not a B1 coverage problem. Per the #10 noise floor,
   read this as a directional signal across a couple of runs, and watch that no
   previously-answering case regresses (the subject supplement + corpus-match guard should
   add signal without noise).

## Out of scope

- **B2 — high-frequency-subject disambiguation** (the God case): separate, belongs with #11
  ranking; may need embeddings. B1 remaining imperfect on God is the intended result.
- Embeddings / semantic expansion (still no *absence* miss justifies them).
- Mapper / `MAP_VERSION` / mapping-gold changes.
- Promoting C's `premature_abstention` to gating (its own validate-then-gate follow-up).
