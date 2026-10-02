# Graph explorer: inspection report and projection contract (increment A)

Deliverable for increment A of `.claude/plans/0030_source-backed-graph-explorer.md`.
Records what the live baseline snapshot actually contains for the three inspection
cases, and fixes the projection contract the later increments implement.

Snapshot inspected: `src/infrastructure/database/data/claims/corpus.jsonl` (3984
anchored claims), `.../data/resolutions/baseline.jsonl` (4308 entities),
`list_sources()` (405 sources: 399 ACIM "Sparkly Edition", 6 Bible stub).

## 1. The three inspection cases resolve

All three resolve to real baseline entity IDs. None had to be invented.

| Case | entity_id (prefix) | members | shape |
| --- | --- | --- | --- |
| forgiveness | `53c7a87f3cb1` | `{forgiveness}` | singleton |
| right-mindedness | `6de728f2a59d` | `{Right-mindedness, right-mindedness}` | case-variant merge |
| God | `7fc3fee914ba` | `{GOD, God}` | case-variant merge |

The lexical baseline merges almost nothing: 4083 of 4308 entities are singletons; the
largest group has 5 members. Merges observed are case variants only. **Consequence for
eligibility:** a singleton entity is still a legitimate starting point (forgiveness is
one), so eligibility must not require a merged group. "No match" means no catalogued
expression matched, never that the corpus is silent on the concept.

`"right mindedness"` (no hyphen) resolves to nothing — the catalog holds only the
hyphenated form. Search must index the exact observed expressions, not a normalized form.

## 2. What each case's claims look like

Participation = claims whose subject OR object is one of the entity's forms.

- **forgiveness** — 4 outgoing, 0 incoming. All `affirmed`/`course`. 3 of 4 are
  `conditional` mode, 1 `assertion`. Predicates `is`×3, `requires`×1. No missing
  objects. This is the clean **definition** case, but note the conditional mode must be
  shown on the edge, not buried — "forgiveness is an empty gesture" is a conditional the
  Course sets up, not a flat assertion.
- **right-mindedness** — 11 outgoing, 1 incoming. 10 affirmed / 2 negated; 11 assertion
  / 1 normative. Predicates span `other`×4, `is`×4, `causes`×2, `creates`×1,
  `requires`×1. The **ordinary + negation** case.
- **God** — 84 outgoing, 19 incoming. The **dense/qualified** case, and it exercises
  every exclusion the plan anticipates: 23 negated, non-course attribution (7 `others`,
  1 `ego`), 11 conditional + 2 question + 2 normative modes, and **2 outgoing claims
  with a missing object** (e.g. `God --"WOULD be mocked"--> None`). These must stay
  inspectable in the relationship list, not drawn as edges and not given a manufactured
  endpoint node.

## 3. Claim-to-passage join

- `claim.source_id -> Source.id` over aggregated `list_sources()`. Source IDs are
  **unique** (405/405) and **every** claim joins (0 failures in the current snapshot).
- A claim whose `source_id` is absent from `list_sources()` is a **generation failure**
  with an actionable diagnostic (which claim, which missing id) — not a silent drop and
  not a semantic exclusion.
- Evidence anchors verified against `Source.text`: `evidence_start/evidence_end` slice
  the expected clause (spot-checked; full validation is increment B's job over all
  claims).

## 4. Locator rendering by book / edition

Two schemes coexist; render each from the fields actually populated, never inferring the
other scheme's fields.

- **ACIM** (399 sources, `edition="Sparkly Edition"`): `book="ACIM"`, `chapter`,
  `section` (can be **0** — e.g. `t1-0-1`), `paragraph`. The `paragraph`/`source_id`
  numbers are **positional block ordinals assigned at import**, not the Course's
  Principle/verse numbers — see `docs/followup-source-id-stability.md`. Display them as a
  stored location, explicitly **not** a verified canonical citation, and do not relabel
  `"Sparkly Edition"` as a real edition.
- **Bible** (6 sources, blank edition): `book` (e.g. `Matthew`), `chapter`, `verse`;
  `section`/`paragraph` are `None`. Some Bible source IDs encode verse *ranges* the
  single `verse` field cannot represent — do not fabricate a range from the id.
- Fallbacks: when fields are missing or the edition is unknown, fall back to the raw
  `source_id` as the locator rather than guessing. Section 0 renders as section 0, not
  omitted.

## 5. Projection contract (fixed here, implemented in B/C)

- **Endpoint eligibility:** an endpoint is drawable iff it is a non-empty surface form
  that resolves to a catalogued entity *or* stands as its own singleton form. A claim is
  drawn as one directed edge iff **both** subject and object are drawable and `object`
  is not `None`. No curated per-concept allow/deny list in this increment; if one is ever
  added it is explicit and versioned.
- **Non-projectable, kept inspectable:** missing object, or an endpoint that is not a
  usable surface form. Shown in the relationship list with the original wording and the
  exclusion reason. Never given a manufactured node.
- **One edge per eligible claim.** Parallel edges and self-loops retained. No merging, no
  aggregation this increment.
- **Semantic fields on the edge/list before selection:** predicate (normalized, for
  filtering), original `verb_phrase` (for meaning), `polarity`, `mode`, `attribution` —
  as text, not only styling. `is` establishes neither identity, symmetry, nor
  transitivity; related entities (God, God's Thoughts, God's Miracles) stay distinct.
- **Label policy:** deterministic choice among the entity's observed expressions
  (shortest, then lexicographic, stable under re-export). Labels are presentation, never
  canonical names or evidence of equivalence.
- **Direction vs. wording:** `predicate` controls direction and filtering; the displayed
  quote is never reversed even when normalization flipped direction (`arises from`
  stored as `causes`).
- **Ordering / caps:** neighborhoods default to ≤20 eligible relationships, ordered
  deterministically by (predicate, object label, claim_id). A total visible-graph cap is
  defined in C and truncation is explained in the counts, never silent.

## 6. Status taxonomy (what an automated check may assert)

- **Mechanical resolution** (resolver merged a form) and **endpoint eligibility**
  (drawable per §5): automatable, reported by the export.
- **Concept validity / contextual meaning** (is this surface form really the concept;
  pronoun referents; stripped qualifications): **not** automatable. Reported only via the
  recorded manual sample review in increment D. The export must not present eligibility
  as semantic validity.

## 7. Export measurements (increment B)

Live export of the current snapshot (`python -m application.projection.export_cli --out
apps/web/public/graph/projection.json`):

- 3984 input claims -> **3763 drawn edges + 221 non-projectable** (all `missing_object`),
  accounted exactly. 4216 nodes, all catalogued; **225 are real merges** (>1 expression),
  matching §1's multi-member count.
- Artifact size: **5.7 MB raw / ~573 KB gzipped** as one file. Passages were 69% of the
  payload until the redundant full-`text` field was dropped (it equalled
  `before`+`clause`+`after`); evidence is now stored once as segments.
- **Single-file decision:** 573 KB gzipped is acceptable for a cached, read-only,
  API-less page. Static evidence chunking is **not** warranted yet and stays deferred per
  the plan; revisit only if the corpus grows the artifact materially.
- Re-export against an unchanged snapshot is **byte-identical** (stable `content_hash`).

## Acceptance (increment A)

Each representative case is faithfully representable (forgiveness, right-mindedness, and
the drawable subset of God) or explicitly classified non-projectable (God's missing-object
and non-course claims), with the original claim always available for inspection. ✓
