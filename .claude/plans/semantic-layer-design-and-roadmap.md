# Semantic layer: design decisions and roadmap

The long-running design for turning the ACIM corpus into structured,
source-anchored claims an agent can reason over. It records *why* the pieces
look the way they do, and the order they're built in. Detailed plans for
individual increments live alongside this file. Increments #7 (claims in retrieval,
`claims-in-retrieval.md`), #8 (deterministic claim chaining,
`synthesis-and-interpretation.md`), and #9 (situation→concept mapping,
`situation-concept-mapping.md`) are complete. #9 was the roadmap's last *pre-planned*
step; the shipped agent/web stack since then surfaced the concrete need that drives the
next increment — **#10, a black-box evaluation harness** (`black-box-eval-harness.md`).
The remaining work (ranking, embeddings + a database, concept dossiers) stays deferred,
but now with explicit triggers: #10's A/B/C failure-mode split (evidence availability /
adequacy / answer fidelity) decides whether the next step is ranking, synthesis-prompt
work, embeddings, or dossiers, rather than guessing.

## Origin

The starting point was an external proposal: extract ideas, concepts, beliefs,
etc. into a knowledge graph, with claims, provenance, concept dossiers, pgvector
embeddings and graph-guided retrieval for the agent. Its core direction was kept.
Several parts were changed or deferred, and the reasons are below so they aren't
re-argued later.

## Principles

- **Three representations, never collapsed into one.** The source text is what the
  Course says. Claims are how the text relates things. Embeddings, later, find
  what's relevant. Each answers a different question.
- **Claims, not facts.** The unit of extraction is a claim anchored to an exact
  span of a passage. The graph records what the text asserts, never what is true.
- **What the text states vs. what is inferred.** Everything extracted today is
  explicit. Anything synthesised across passages, or interpreted when applying
  the Course to a user's situation, must be labelled as such when it's built. The
  agent must be able to tell "the Course says X" from "this follows from what it
  says".
- **Narrow extraction passes, scored against gold labels.** No single "build the
  ontology" LLM call. Each pass is small, versioned (`PROMPT_VERSION`, hashes in
  every run header) and measured before the next one is built on it.
- **Small increments, each useful by itself.**

## Decisions

### Adopted

| Decision | Why |
| -------- | --- |
| `attribution` field (`course` / `ego` / `others` / `hypothetical`) | The Course constantly describes views it rejects ("the ego believes…", "many ministers preach…"). Without this field, those views enter the graph as the Course's own teaching. This was the proposal's biggest omission. |
| `polarity` separate from `predicate`; no `is_not`-style predicates | Negation lives in one place, so a dropped "not" shows up as a mismatch rather than a new kind of edge. The same goes for negative quantifiers: "no-one…" becomes a plain subject + `negated`, never counted twice. |
| `mode` (assertion / normative / conditional / question) | Should/must statements, if-clauses and rhetorical questions aren't plain assertions. Questions are stored as literally worded, never flipped to the implied answer, which would be interpretation. |
| A fixed predicate list plus `other`, and `verb_phrase` keeping the text's wording | Free-text predicates split apart ("arises_from", "comes_from", "is_caused_by"…) and make the graph impossible to traverse. `causes` has one direction: cause → effect. `makes`/`creates` stay separate because of the Course's made vs. created distinction. |
| Evidence stored as the model's exact quote, turned into character offsets by code, with the quote verified to appear exactly once | Models copy text reliably but count characters badly. Claims whose evidence can't be anchored are kept as rejections, because their rate is a measure of the model's quality. |
| Gold labels written in the same format and loaded by the same code as model output | Gold and predicted claims can't disagree because of how they were read. |
| The labelling rules live in one place: `SYSTEM_PROMPT` | The rules the model is given and the rules the gold labels follow can't drift apart. |
| Provider-agnostic: an adapter only supplies `(system, user) -> reply` | Every provider is compared on the same prompt, parser and scorer. |

### Changed or rejected from the proposal

| Proposal | Decision | Why |
| -------- | -------- | --- |
| `ontological_status` labels (REAL / MADE / PERCEIVED / EGO) and a fixed Idea/Concept/Thought… type taxonomy | Rejected for now | They decide theology before extraction (labelling LOVE as REAL is itself interpretation), and they mix different kinds of category. If they come back, they should be derived from `makes`/`creates` and `is` claims, not assigned up front. |
| Automatically inferring A→C from A→B and B→C | Rejected | Causal chains aren't reliably transitive, and `associated_with` isn't transitive at all. Stored inferred links would grow the graph while making it less trustworthy. The agent should chain cited claims when answering, not rely on precomputed links. |
| LLM-reported confidence driving a human review queue | Rejected | A model's confidence in itself isn't calibrated. Use agreement across runs or models, and evidence verification, instead. |
| Postgres + pgvector from the start | Deferred | Versioned JSONL is enough while extraction quality is still being measured. Move to a database when retrieval needs to query claims at scale. |
| Citations in FIP format (`T-6.IV.3`, W-, M-) | Rejected | This corpus is the Original Edition (CMI text). Its section and paragraph numbering differ, so cite only in the scheme actually held. |
| A separate `acim-kb/` project layout | Rejected | Fits the existing DDD layers instead: `domain/claims`, `application/extraction`, `evaluation/claims`, with provider adapters under `infrastructure/llm`. |

## Corpus caveats

- **Original Edition numbering.** Principle numbers repeat (two 24s and two 27s in
  T1.1), and commentary paragraphs sit between principles. Always key on
  `source_id`.
- **Passage IDs and offsets depend on the parser.** `sources_acim.py` splits on
  blank lines and normalises whitespace and `*`. Any parser change moves them. The
  gold loader fails loudly when labels stop lining up, and run headers hash the
  passages.
- **Capitals are the author's emphasis, not noise.** Keep them in the text and in
  `verb_phrase`.
- **Known text glitches:** OCR run-ons (`Source,Which`, `conviction.Without`) and
  footnote markers (`[^1]` in principle 22). They're harmless to extraction.
  Cleaning them later will change hashes and needs a relabel check.

## Roadmap

| # | Increment | Status |
| - | --------- | ------ |
| 1 | `Claim` model + gold set (T1.1 principles, T3.2 paragraphs) + scorer | done |
| 2 | Extraction layer: `ClaimExtractor`, evidence anchoring, prompt, reply parser | done |
| 3 | Runner, run records, first provider run (v2: exact P 0.30 / R 0.31) | done |
| 4 | Scoring fixes, near-miss report, prompt v3, predicate conventions | done: `claim-extraction-scoring-and-prompt-v3.md` |
| 5 | Scale: extract chapters 1–4 into versioned JSONL; second gold batch including `ego` attribution; review the predicate list against recurring `other` verbs | done: `scale-and-second-gold-batch.md` |
| 6 | Entity resolution: merge surface forms into entities, with the LLM choosing among candidates rather than inventing them | done: `entity-resolution.md` (resolver pair R 0.895 vs baseline 0.789 at P 1.0; residual gap is blocking recall) |
| 7 | Claims in retrieval: expose claims and their passages to the agent (MCP tool or `find_sources` extension) | done: `claims-in-retrieval.md` (`find_claims` + `find_claims_for_entity` live) |
| 8 | Deterministic synthesis: cross-passage claim chains computed at answer time (never stored), each chain labelled inferred while its links stay stated and Course-attributed | done: `synthesis-and-interpretation.md` (`chain_claims` use case + MCP tool live) |
| 9 | Situation → concept mapping: an LLM maps a user's free-text situation to candidate concept mentions (scored against a small gold set), which feed #7 retrieval and #8 chaining; never presented as the Course speaking | done: `situation-concept-mapping.md` (`map_situation` + eval; dev set R 0.889 / P 0.294 / F1 0.442, recall the metric that matters) |
| 10 | Black-box evaluation harness: a DeepEval regression suite that treats the agent as a black box (`question → answer + sources`, no internal knowledge), scoring source grounding / answer behavior / epistemic boundaries / citation quality across ~20 behavioral fixtures; a *separate* A/B/C diagnostic (evidence availability / adequacy / answer fidelity) reads pipeline traces to explain failures without ever changing the verdict | planned: `black-box-eval-harness.md` |
| 11 | Claim ranking / retrieval improvements (incl. question-mode → per-intent ranking extending `ranking.py`) | gated: only where #10's A/B/C split shows misses dominated by retrieval/ranking (A), not synthesis (C) |
| 12 | Embeddings + persistent semantic index (Postgres/pgvector) | gated: only if **A** persists after #11 — answering passage exists but lexical/concept retrieval can't reach it |
| 13 | Concept / entity dossiers | gated: when repeated describe/exploration failures show per-concept *aggregation* is the bottleneck (a B the ranking can't fix), not retrieval |

Write a detailed plan for each increment only when its predecessor is done, since
each one's scope depends on the previous one's results. #10 reframes the tail of this
roadmap from "the semantic layer" to "the retrieval/evidence layer", and puts a
black-box regression gate *ahead* of any architecture change: the goal is no longer to
find *related* text but the evidence *appropriate to the question* — and to measure which
failures are retrieval's (A), evidence-selection's (B), or synthesis's (C) before
spending effort on any of them.
