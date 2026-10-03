# Survey: qualified concept uses (do we need a sense/entity layer?)

Read-only corpus survey to decide whether "qualified uses" of a concept (e.g.
"forgiveness lacking correction") should be minted as entities and linked to each other
and to an illusory/"worldly" definition — or held lighter. No model, prompt, corpus id, or
artifact was changed. Prototype: `scripts/proto_forgiveness_condition.py`. Prompted by the
t3-1-5 forgiveness/correction passage reading wrong on the graph.

## What the data shows

> **Reading these counts (important caveat).** The counts below measure *extraction
> patterns* — how often the extractor emitted a conditional/negated claim — **not** the
> strength of a conceptual distinction in the text. A concept with few conditional claims
> may still carry a strong qualified sense the extractor didn't flag as conditional. Do not
> read "forgiveness: 4 conditional" as "forgiveness is weakly distinguished."

**1. Forgiveness is only lightly qualified *by the extractor*; other concepts far more.**
Conditional / negated appearances (subject or object), by concept:

| concept     | conditional | negated |
|-------------|-------------|---------|
| forgiveness | 4           | 1       |
| love        | 10          | 8       |
| healing     | 4           | 5       |
| miracle     | 24          | 38      |
| peace       | 2           | 7       |
| atonement   | 9           | 11      |

So forgiveness is a *weak* example of the phenomenon; miracle/love/atonement are where
qualified uses actually concentrate. A sense layer justified only by forgiveness would be
built on the thinnest case.

**2. Qualified subjects already exist in the data as distinct surface forms.**
Extraction already emits qualified subjects as distinct strings rather than collapsing them
onto a bare concept node: "miraculous forgiveness", "perfect love", "human love", "mind
that perceives without love", "not willing to love". These are *already* separate subject
surface forms — the sense distinction partly exists today; what's missing is a link back to
the base concept, not the distinction itself.

**3. The Course sometimes names a qualified kind itself — that's text-given, not coined.**
e.g. `t3-1-6`: "miraculous forgiveness ... has NO element of judgement at all" names a kind
of forgiveness explicitly. These are evidence-anchored, unlike "forgiveness lacking
correction" (which we coined from the "unless/without" hinge in t3-1-5).

**4. An explicit "worldly/false/illusory + concept" *phrase* is almost absent.**
Searching the raw corpus for `(worldly|false|illusory|unreal|ego's|magic|physical|human|
the world's) + (forgiveness|love|healing|miracle|peace|salvation|atonement|vision|
perception)` yields **5 hits total**: "physical sight" (×3), "physical healing" (×1),
"human love" (×1). **"Worldly forgiveness" never appears as a phrase.**

> **This rules out only the *named category*, not the distinction.** The regex catches
> adjacent "qualifier + concept" phrases; the Course can still draw the same distinction in
> other wording ("forgiveness, as the world understands it, …", a whole passage contrasting
> two kinds without ever compounding them into one phrase). So the finding is: there is no
> text-given *label* "worldly forgiveness" to treat as an entity — not that the text lacks
> the distinction. 5 is a floor on the phrase, not a measure of the idea.

## Reading

- **Minting qualified uses as entities eagerly is not supported by the evidence.** The
  explicit illusory-definition that such entities would consolidate under (tier 3,
  "worldly forgiveness") barely exists in the text, and for forgiveness not at all. Eager
  entities would mostly be coined nodes with nothing real to link to — the auto-relabel
  risk flagged earlier, realised.
- **The lighter model fits what's actually there.** Keep a qualified use as a
  *condition-qualified occurrence scoped to its passage* (tier 1), carrying its evidence,
  linked contextually to the base concept (tier 2). Promote to a shared sense/entity (tier
  3) only where the text itself names the kind ("miraculous forgiveness", "physical sight",
  "human love") or explicitly groups uses — which is rare and concept-specific, not a
  general illusory-twin pattern.
- **The condition is the trigger, not the whole fix.** Preserving the condition (the
  "unless/without" hinge) in extraction is what licenses splitting a qualified occurrence
  out in the first place. So the `condition`-field question doesn't go away; it becomes the
  signal that an occurrence is qualified.

## Working rule (standing conclusion)

Passage-scoped qualified uses are the next step; shared senses are deferred. The rule:

- **Preserve conditions and resolve their references** — e.g. "without this" → "without
  correction". The hinge text is kept, not flattened to a bare `mode=conditional`.
- **Create a qualified occurrence only when the passage explicitly supports the
  qualification** — scoped to that passage, carrying its evidence, linked contextually to
  the base concept. Not a global entity.
- **Keep text-given labels distinct from interpretive labels.** "miraculous forgiveness",
  "human love", "physical sight" are the Course's own words; "forgiveness lacking
  correction" is ours, coined from the hinge. The two must never be conflated in the data.
- **Consolidate occurrences only with evidence that they share a *meaning*** — not merely
  that each is negative, conditional, or illusory. Two uses can both be illusory without
  meaning the same thing.

**Triggers are necessary, not sufficient.** A condition hinge is one trigger; an explicit
modifier ("human love") is another. Neither *alone* establishes that a use is illusory or
that two uses co-refer — that needs separate evidence of shared meaning. This keeps the
eventual grouping (e.g. under a worldly/illusory concept, however the text words it)
*possible* without building it into the data prematurely.

Open question deferred to a real design pass: whether promotion lives in the entity-
resolution layer (`domain/entities`) or as a separate sense layer. Not blocking: the
near-term lever is preserving the condition + reference resolution, which is what makes a
qualified occurrence detectable in the first place.

## Caveats

- Concept matching was substring-based over a fixed concept list; counts are indicative,
  not exact. "forgive" vs "forgiveness" were counted separately.
- The qualifier/concept regex catches adjacent phrases only; a qualified sense expressed
  across a clause boundary ("forgiveness, as the world understands it, …") would be missed,
  so 5 is a floor. Even generously, explicit illusory-twin naming is rare.
