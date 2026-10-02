# Retrieval follow-ups — candidate increments surfaced by the black-box eval

## Context

Increments #10 (black-box harness), #11 (query-relevance ranking), and #12 (direct-question
retrieval for questions about the Course itself) are done. Running the eval across five live
rounds surfaced three *distinct* remaining problems that #10–#12 did not address. This file
records them as candidate next increments — each with its concrete evidence, a gating
condition (when it's worth doing), and an explicit note of what it is **not**, so the
roadmap stays evidence-driven rather than guessed. None is started; the point is to capture
the signals while they're fresh and let measurement decide the order.

The through-line: each fix so far has made the *next* bottleneck measurable rather than
hypothetical. These follow-ups are what the sharpened eval now points at. **Embeddings
(the roadmap's nominal #12) remain unjustified** — every failure below is ordering,
selection, or query-formulation, not genuine corpus *absence*.

**The dominant symptom, confirmed by run-6 answer prose, is PREMATURE ABSTENTION**: the agent
says "this isn't in what I have / touches only the edges" while the direct answer sits in the
corpus, unretrieved. It recurs across `ego-definition-023` ("they don't give a direct account
of what the ego actually is" — 25 "ego is…" claims exist), `mind-of-god-004b`, and
`highlight-chapter-one-024` (dismissed a fifth of the corpus). So C, B, and D are not four
independent problems — they are **one failure class from two angles**: C is the *measurement*
that makes premature abstention visible; B and D are the *retrieval-side* fixes for the two
ways it's caused (concept phrasing vs. corpus structure). A is the odd one out (a selection
problem) and is the weakest-evidenced — its own probe passed.

---

## SESSION END-STATE (supersedes the per-signal analysis below where they conflict)

Shipped and committed this session: **#10** black-box harness, **#11** query-relevance
ranking, **#12** meta-question direct-search, **C** abstention-quality advisory criterion
(`premature_abstention`), **B1** concept-subject supplementation, and the **front-load
ordering fix** (supplements seeded first). Result: `ego` and several definitional cases fixed;
gating ~17–18/21.

**The remaining "premature abstention on definitional questions" splits into THREE distinct
root causes — investigated to ground truth (via the `conversation_messages` join: user row →
agent row `message_json.cited_claims`), NOT a single class, and deliberately NOT built:**

1. **Claim-selection** (`course-about-006`, partly `mind-definition-025`): the subject query's
   rank-0 result is *not* the key/thesis claim (e.g. `find_claims("course")` rank-0 is the
   trivial "required course", not the thesis; `find_claims("mind")` rank-0 is "mind that serves
   the Spirit is", not the anchored definition). **First audit whether the gold anchor is
   genuinely the only valid answer** — this is likely partly the recurring over-strict-anchor
   pattern, not a pure retrieval bug.
2. **Deep lexical rank on high-frequency subjects** (`mind-of-god-004b`): the definition ranks
   ~18 among 300+ "God" matches; surfaces only at `global_limit=100`. Lexical `find_claims`
   fundamentally can't rank it high. **This is the strongest embeddings signal so far** — the
   genuine #12-embeddings trigger — but still ~1 case; gated on recurrence per the roadmap.
3. **Round-robin × small `global_limit`** (`mind`): a within-query rank≥1 definition is pushed
   past position 12 by rank-major interleave. Real but entangled with #1/#2; don't fix alone.

**Tested and rejected as fixes:** raising `global_limit`/`limit_per_query` (surfaces the
definitions only at positions 20–80, flooding context — no good); a single `find_claims_batch`
interleave change (query-major-cap-2 still misses `mind`). So there is **no clean single
increment** here — building one would chase three different causes, one of which is possibly a
fixture-anchor artifact. **Decision: pause, don't build; let recurrence across more cases pick
the real increment.** The `mind`/`knowledge` probe cases remain in the gold set as measurement.

### Latest run (18/21, `runs/20260927T212847Z.jsonl`) — failures are HETEROGENEOUS

Three gating failures, three different profiles — reinforcing "don't build one fix":
- `course-about-006`: answers well (answers_question 0.8, strong grounding/fidelity) but misses
  the required claim → **audit the anchor first**, likely not a retrieval bug.
- `mind-definition-025`: same shape (grounding 0.85, synthesis 0.75, required evidence absent)
  → **audit the anchor first**.
- `mind-of-god-004b`: coherent answer (grounding 0.9, fidelity 0.9) but the specific expected
  sources never enter the evidence set → a retrieval miss *relative to this fixture*; the
  strongest (but still ~1-case) embeddings signal. Does NOT by itself justify embeddings.
- **`knowledge-definition-026` (secondary, important): required evidence PASSES, yet
  answers_question is 0.4 and it still prematurely abstains.** The right claim was surfaced and
  the agent *still* didn't use it well → a **pure SYNTHESIS signal, decoupled from retrieval** —
  the first case isolating "using available evidence effectively" as its own frontier, separate
  from any retrieval fix.

### Next investigation (documented entry point): ANCHOR AUDIT

Before any retrieval/embeddings work: audit the gold anchors for `mind-definition-025` and
`course-about-006`. Question is not "can retrieval eventually find the expected claim?" but
"is this genuinely the canonical evidence the agent should be *required* to surface for the
wording of this question?" (`find_claims("mind")` rank-0 is "mind that serves the Spirit is",
arguably a valid answer; `find_claims("course")` rank-0 is the trivial "required course".) If
an anchor is too strict → loosen it (the recurring over-strict-anchor pattern), failure
dissolves. Only if an anchor SURVIVES the audit does its retrieval miss become a real signal —
and only then does `mind-of-god`'s deep-lexical-rank miss get promoted to an embeddings
investigation. Sequence: **architecture stop → retrieval stop → anchor audit → (survivors only)
embeddings investigation**; synthesis (`knowledge`) is a separate, later thread.

---

## A. Evidence selection — surface the *right* claim, not just a retrievable one

**The strongest current signal.** `course-about-006` still gating-fails after #12, and the
diagnosis is three-layered — #12 fixed only the first:

1. Formulation (fixed by #12): `"course"` is now searched, so `t1-0-1` is reachable.
2. **Round-robin depth:** `t1-0-1` lands at position 10 of 12 in the seed batch (the
   supplemental `"course"` query is last, and round-robin gives it a late slot), so it's
   present but buried.
3. **Wrong claim within the source:** `find_claims("course")` ranks `t1-0-1`'s *trivial*
   claim (`2b084ddea28ce42c`, "this course is a required course") above its *thesis* claims
   (`44e9f68768054c02` / `934b7f695826e53c`, "aims at removing the blocks to the awareness
   of love's Presence"). Query-relevance ranking (#11) can't distinguish them — both are
   subject-position `is` claims — so the administrative claim wins on corpus order.

**What this increment is:** improve *which* claim is selected/ranked when several claims share
a subject and position, and reconsider how the supplemental/round-robin ordering seats a
high-value claim. Candidate levers (to be designed, not prejudged): a salience/specificity
signal beyond subject-position+predicate-role; weighting the supplemental direct-query result
higher than a late round-robin slot; or a per-intent rank that prefers thesis/definitional
phrasing over administrative.

**It is NOT:** #11 (that was query→field position, already shipped), #12 (formulation, shipped),
or embeddings (the claim is retrieved; the problem is choosing among retrieved claims).

**Gated on:** already justified — `course-about-006` is re-anchored to
`must_include_any_claim_ids [44e9f68…, 934b7f6…]` (the thesis claims) specifically so this
problem is now a measurable gating failure, not a vague sense. This is the most-evidenced
next increment.

---

## B. Semantic query expansion for concept questions

**Signal:** `mind-of-god-004b` ("How does God think? What is the Mind of God?"). The corpus
*has* direct answers — `t3-6-9` ("God's Miracles are as total as His Thoughts because they
ARE His Thoughts"), `t3-4-8` ("God knows His Children"), `t3-5-13` ("God knows you only in
peace") — but the agent surfaced only generic God-attributes and abstained ("touches the
edges"). Two mechanisms:

- `find_claims("mind of god")` returns `[]` — the corpus phrases it as "God's Thoughts",
  "God knows", never the literal "mind of god".
- `find_claims("god")` doesn't reach the `t3-x` claims in its top results — "god" matches
  100+ claims and the direct ones sit deep in corpus order.

So a concept question whose natural phrasing doesn't match the corpus's phrasing gets
premature abstention. The fix is **expanding a concept question into retrieval-effective
terms** (e.g. "how does God think" → god / mind / thought / thinking / knowing) alongside
`map_situation`, so the direct claims enter the candidate set.

**It is NOT #12:** #12 handles when the *corpus itself* is the subject ("what is the Course
about"). This is a *concept within the corpus* phrased so the mapper doesn't emit the
retrieval-effective term. Do **not** extend the narrow meta-detector to cover it — different
mechanism, different fix.

**Gated on:** `mind-of-god-004b` exists now (corpus_reality `sufficient`,
`acknowledge_insufficient_evidence_when_appropriate` in *prohibited* — abstaining is the
failure). Take this up when the eval shows concept-phrasing misses are a recurring class, not
a single case; consider whether expansion belongs in the mapper (with the `MAP_VERSION` +
mapping-gold cost) or as an orchestrator-side expansion step (cheaper, like #12).

---

## C. An abstention-quality dimension for the eval itself

**The deepest signal — a measurement-system gap, not an agent bug.** The harness currently
cannot distinguish:

- **premature abstention** — the agent says "I don't have enough" when the corpus *does*
  contain a sufficiently direct answer (the `mind-of-god` case); versus
- **correct abstention** — the agent declines when the corpus genuinely lacks the material
  (the `outside_corpus` cases).

Today only *anchored* cases catch premature abstention (via `required_evidence_present`). An
un-anchored `sufficient` question where the agent wrongly abstains would pass gating — a
silent quality failure. An agent that abstains when the answer is present is arguably a worse
product failure than thin retrieval, and it's currently invisible unless a human anchors the
case.

**What this increment is:** a first-class eval capability that scores abstention against
corpus reality — e.g. for a `sufficient` case, an answer that abstains without surfacing the
available evidence is flagged, independent of hand-anchored claim ids. Likely a new criterion
(deterministic where the case is anchored; advisory/judge where it isn't) plus the
`corpus_reality` label already carried on every case.

**It is NOT** a retrieval or agent change — it improves what the harness can *see*, so A and
B (and future work) are measured honestly. Per the #10 discipline (the harness is the durable
asset), this deepens the measurement system rather than chasing another product tweak — do it
when the product signals from A/B are exhausted, or sooner if premature abstention proves
common.

---

## D. Structural / navigational queries

**Signal:** "Can you highlight the most important parts of the first chapter of the Course?"
The live trace is damning: `Mapped situation to 0 concept(s)` → `find_sources for "chapter 1
principles of miracles"` → `0 returned` → the agent declared it had "nothing from the first
chapter." But the corpus is **825 chapter-1 claims** (a fifth of it). A catastrophic false
abstention. Two compounding gaps:

- The mapper returns `[]` for a structural/navigational request (no *situational* concept to
  extract from "the first chapter").
- Nothing can retrieve by corpus *structure*: `find_claims("chapter"/"first chapter")` → `[]`;
  chapter membership lives only inside `source_id` (`t1-*`), not in any searchable field.

**What this increment is:** let retrieval navigate the corpus by its structure — "chapter 1"
→ the claims/sources whose `source_id` starts `t1-`, then surface the salient ones. Closer to
a `get_sources`-style structural lookup than to concept retrieval. Confirmed in scope for the
product (a legitimate ask the agent should answer, not decline).

**It is NOT** A (selection), B (concept-phrasing), embeddings, or #12 (Course-as-subject).
This is *positional* retrieval the pipeline has no notion of.

**Gated on:** `highlight-chapter-one-024` gold case added (`corpus_reality: sufficient`,
`intent: structural`; `acknowledge_material_not_present` + `acknowledge_insufficient_evidence`
in *prohibited* — false abstention is the failure). Its deterministic gate is `not_evaluated`
(no single anchor is "correct" — any reasonable salient set answers), so **C (below) is what
actually catches it** — reinforcing that C is the higher-leverage measurement work.

## Also outstanding (tracked elsewhere, not re-planned here)

- **`[88]`-style citation fabrication** — the agent occasionally emits a truncated claim_id
  (a bare paragraph number) as a citation marker; caught by `citation_integrity`. The prompt
  fix (`_MARKER_CONTRACT`) is nondeterministic; the durable fix is *structural* — strip/repair
  markers not in `citation_diagnostics` before the answer ships. A focused robustness
  increment, separate from A/B/C.
- **A/B/C failure-attribution diagnostic** and **validating advisory judges against human
  labels** — deferred later-#10 slices (see `black-box-eval-harness.md`). C above is a
  narrower, sooner slice of the same "deepen the measurement" theme.

## Suggested order (evidence-driven — updated after expanding the case set)

An earlier draft put A first as "most-evidenced." A closer count corrected that: only
**one** case (`course-about-006`) actually fails on claim-*selection* (`miracles-order-001`,
the other claim-anchored case, passes) — so A is effectively n=1 and building a salience
ranker for it risks overfitting, the trap held against elsewhere. Meanwhile **premature
abstention now spans two cases** (`mind-of-god-004b` thin-but-present, `highlight-chapter-
one-024` egregious), and D compounds it. So:

1. **C (abstention-quality)** — now the best-evidenced *and* highest-leverage: it's a
   measurement gap (the harness can't see false abstention on un-anchored `sufficient`
   cases), and false abstention when the answer is present is a worse product failure than
   thin retrieval. Building C makes A, B, and D all measurable honestly.
2. **Then B (concept-phrasing query expansion)** — the strongest *product* class: run 6 had
   both `ego-definition-023` and `mind-of-god-004b` fail `required_evidence_present` (the
   direct claims exist but the natural query phrasing doesn't reach them). A larger class than
   A.
3. Robustness/measurement items as focused increments when the product frontier quiets.

**Run 6 (19 cases) settled the counts:**
- **C is proven, not hypothetical:** `highlight-chapter-one-024` **PASSED gating** while
  scoring `answers_question: 0.2` — a false abstention (dismissed a fifth of the corpus) that
  the gate is blind to because the case has no single anchorable claim. That is precisely the
  measurement hole C closes; advisory caught it but advisory doesn't gate.
- **A is confirmed too thin:** `atonement-definition-022` (a selection probe) *passed* — so A
  doesn't even reproduce reliably. Only `course-about-006` fails on selection; n=1 and noisy.
  Do not build A.
- **B is a real 2-case class:** ego + mind-of-god both fail on unreachable-by-phrasing direct
  claims.

Do **not** start A on n=1. Add cases and let the failure *class* — not a single case —
justify the increment. Each increment follows: **hypothesis → minimal change → tests → dev
eval → inspect → iterate**. Embeddings stay out until the eval shows genuine *absence* (a
needed claim not in the corpus), which none of A/B/C/D are.
