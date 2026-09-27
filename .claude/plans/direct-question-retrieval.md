# Increment #12 — direct-question retrieval for questions about the Course itself

## Context

The black-box eval (#10) surfaced a failure that is neither ranking (#11, done) nor
retrieval-absence (#12-embeddings): `course-about-006` ("What is the Course all about?")
gating-fails because the required thesis claim `t1-0-1` never enters the candidate set. The
mechanism, confirmed against the corpus:

- `t1-0-1` holds the thesis ("This is a course in miracles"; "the course aims at removing
  the blocks to the awareness of love's Presence") — and it ranks **rank-0** for the query
  `"course"` (verified). So retrieval + #11 ranking already surface it *if it is searched*.
- But `map_situation` maps the question to its *contents* (forgiveness, love, Atonement…) and
  structurally cannot emit `"course"` — because here the subject the user asks about **is the
  corpus itself**, not a concept within it. The orchestrator's seed batch searches only the
  mapped concepts, so `"course"` is never queried and `t1-0-1` never competes.

This is a **query-formulation gap**, not a retrieval-quality gap. The fix: for a question
*about the Course itself*, supplement the mapped concepts with a direct query derived from
the question. Framed per the standing guardrail — **not** "always add the user's literal
words" (a noisy second retrieval path), but a **narrowly-gated** supplement.

## Approach

**Insertion point: the orchestrator seed batch** (`orchestrator.py:103-117`) — decided
against the two alternatives on evidence:
- *Mapper* is expensive and wrong-shaped: any change to what it emits forces a `MAP_VERSION`
  bump + mapping-gold relabel (the mapping gold has zero meta cases; its set-overlap metric
  would *penalize* an extra literal term on the situational cases). "What is the Course
  about" isn't a life *situation*, so it isn't the mapper's job.
- *Decision prompt* is the wrong lever: making the ReAct loop search "course" as a follow-up
  means loosening the hard-won anti-thrash guidance that `test_prompt.py` and the
  orchestrator repeat-guard exist to hold.

The seed batch is deterministic, is already the sole query-construction site, and already
merges a list into `{"queries": [...]}` — supplementing it touches nothing versioned.

### The detector contract

**A meta-question is one whose subject is the Course itself — the Course is the *object of
inquiry*, not a source of guidance for some other question.** That boundary is the whole
contract:

- **Fires** (Course is the object): "What is the Course all about?", "What is the Course?",
  "What does the Course teach?" (general), "What is the purpose/aim of the Course?", "What is
  A Course in Miracles about?".
- **Does NOT fire**: content questions even when they name the Course ("What does the Course
  say about forgiveness?", "What is the Course's position on forgiveness?", "How are love and
  fear related?" — these map to *contents* and already work); applying the Course to a
  situation ("How can the Course help me with fear?"); and — critically — `outside_corpus`
  questions ("What is Workbook Lesson 1?", "Who transcribed the Course?"), where a supplemental
  "course" search would pollute an answer that must cleanly decline (the §5-leak regression
  class, verified).

Because "What is the Course's position on forgiveness?" must NOT fire while "What is the
Course?" must, the detector is a **small family of explicit framing patterns** (the Course as
subject of an *is/about/purpose/teach* question), **not** a generic `contains("course") &&
contains("what is")` heuristic — the latter would wrongly catch content questions. Start
heuristic, measured against the black-box eval; escalate to an LLM classifier only if the
patterns prove the ceiling.

### The supplemental query — detection and referent-mapping are separate

Detection recognizes several corpus-referents ("the Course", "this teaching", "A Course in
Miracles"); extraction maps *all* of them to the single **canonical retrieval term that
actually works**: `"course"`. Confirmed experimentally — `"course"` yields `t1-0-1` at rank
0, while `"teaching"` does not surface it at all. So `"this teaching"` fires detection but
still yields `["course"]`, never `["teaching"]`. This keeps the extractor from drifting into
a generic keyword puller.

One combined function expresses the invariant cleanly:
```python
def meta_query_terms(text: str) -> list[str]:   # [] when not meta, ["course"] when meta
```
so the orchestrator is just:
```python
queries = list(concepts)
queries.extend(meta_query_terms(request.situation))
queries = _dedupe(queries)          # a mapped "course" must not be searched twice
```
The `searched_terms` set and the "Calling find_claims for N…" status text are computed from
the **final deduped list**, not the pre-supplement one.

## Files

- `apps/agent/src/mind_of_christ_agent/domain/meta_question.py` (new) — `meta_query_terms(text)
  -> list[str]` (`[]` when not meta, `["course"]` when meta), pure and deterministic: the
  explicit framing-pattern family + referent→`"course"` canonicalization. An internal
  `is_meta_question` predicate is fine to expose for tests, but the orchestrator uses the one
  combined function; no separate extraction abstraction until multiple extraction cases exist.
- `apps/agent/src/mind_of_christ_agent/domain/orchestrator.py` — in `run_stream`, after
  `concepts` (line 83) and before the seed call (103-110): `queries = _dedupe(list(concepts) +
  meta_query_terms(request.situation))`; drive the status text and `searched_terms` from that
  final deduped list.
- `apps/agent/tests/test_meta_question.py` (new) — the contract: fires on Course-as-object
  questions (about/is/purpose/teach); does **not** fire on content questions naming the Course
  ("Course's position on forgiveness"), applying-to-situation questions, life situations, or
  the two `outside_corpus` questions; always yields `["course"]` (incl. from "this teaching"),
  never `["teaching"]`.
- `apps/agent/tests/test_orchestrator.py` — the seed-batch argument assertions pin exact
  `find_claims` args (`test_run_stream_seeds_mapped_concepts_then_answers` ~:109,
  `test_run_stream_seeds_all_mapped_concepts_in_one_batch` ~:142). Establish three things:
  **non-meta → exact existing queries** (unchanged); **meta → mapped concepts + "course"**;
  **a mapped "course" is not searched twice** (dedup invariant).

**Untouched:** `map_situation`, `MAP_VERSION`, the mapping gold/eval, the decision prompt,
`find_claims`/ranking. No black-box gold change — `course-about-006` already encodes the
expectation (`must_include_source_ids: ["t1-0-1"]`); it's the case that should flip to PASS.

## Verification

1. `.venv/bin/python -m pytest tests apps/agent/tests apps/mcp-server/tests -q` — new +
   existing green (esp. the updated `test_orchestrator.py` seed assertions and the new
   `test_meta_question.py`).
2. `.venv/bin/pyright` — clean.
3. **Mechanism check (no LLM):** `meta_query_terms("What is the Course all about?") ==
   ["course"]`; `== []` for a life situation, "what is forgiveness", "What is the Course's
   position on forgiveness?", "who transcribed the Course", "what is Workbook Lesson 1".
4. **Black-box run (evidence, framed modestly):** with the stack up,
   `python -m evaluation.blackbox.run --live --record`. The load-bearing signals, in order of
   certainty: (a) **deterministic** — `t1-0-1` now enters `course-about-006`'s candidate set,
   so `required_source_present` becomes *satisfiable* (this is certain and the real proof the
   formulation gap is closed); (b) the case *can* now PASS — but generation/citation may still
   independently fail it, so a single run passing/failing is not the acceptance test (per the
   #10 noise floor); (c) **the critical regression guard** — the `outside_corpus` cases still
   decline cleanly (the detector did not fire on them). Confirm (a) and (c) firmly; observe
   whether the score moves without treating one run as conclusive.

## Out of scope

Embeddings (#12-proper — still unjustified; the eval shows mapping/formulation gaps, not
absence). LLM-based meta-classification (only if the heuristic proves insufficient). Any
mapper/`MAP_VERSION`/mapping-gold change. The `[88]` citation-fidelity hardening (separate
focused increment). A general question-type/intent taxonomy (this is the one narrow
meta-vs-situational distinction the evidence justifies, nothing broader).
