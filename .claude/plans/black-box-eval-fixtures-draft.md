# Black-box eval fixtures — slice-1 draft (~20)

Starter fixtures for increment #10 (`black-box-eval-harness.md`). Black-box and
behavioral: each names the question, the intent, and the behaviors that must/must not
appear — **never a prescribed answer string**. When #10 is built these move into the
harness's fixture format (DeepEval test cases + a `gold/questions.yaml` or `.jsonl`);
this file is the reviewable draft of *content*, not final on-disk format.

## Grounding facts (verified against the corpus, 2026-09-27)

- **Corpus = Original Edition, chapters 1–4 only** (`t1`–`t4`, 388 passages,
  `src/infrastructure/database/data/claims/corpus.jsonl`). Anything that lives only in
  later chapters / the workbook is a legitimate *outside-corpus* case.
- **Citation scheme is `t{chapter}-{section}-{paragraph}`** (e.g. `t1-1-2`), OE numbering
  — never FIP (`T-1.I.2`). A fixture that expects a FIP-style citation would be wrong.
- **Well-covered subjects:** miracles, ego, God (as a *referent*), mind, atonement, fear,
  perception, revelation, healing, separation, the body.
- **Thin-but-present subjects** (the interesting B/adequacy cases): `love` appears as a
  claim subject only ~7×; `God` is named ~84× but mostly *relationally* ("Peace of God",
  "created by God") with few direct "God is X" descriptions — this is exactly the God
  example that motivated #10.

Each fixture below carries the `evaluation` block the plan specifies:
`intent`, `expected_behavior`, `prohibited_behavior`, plus a `corpus_reality` note (adequate
/ partial / insufficient / outside) so the harness can score the epistemic-boundary
dimension. The behavior vocabulary is shared across fixtures so the judge criteria stay
consistent.

---

## Category 1 — direct answer available (adequate)

```yaml
- id: miracles-order-001
  question: "Does the Course say some miracles are harder than others?"
  evaluation:
    intent: direct_description
    corpus_reality: adequate
    expected_source_ids: [t2-0-16]
    expected_claim_ids: [632a5b31428b0a68, a3bf5de0130a829c]
    expected_behavior: [answer_directly, cite_supporting_source, preserve_polarity]
    prohibited_behavior: [invent_unsupported_attributes, hedge_when_evidence_is_clear]
  notes: >
    "there is NO order of difficulty in miracles" — the Course's stated first point,
    at t2-0-16 (NOT chapter 1, as first drafted). Negated-polarity: must answer NO and
    keep the negation (a dropped "not" flips it). This is a preserve_polarity anchor.

- id: atonement-purpose-002
  question: "What does the Course say the Atonement is for?"
  evaluation:
    intent: direct_description
    corpus_reality: adequate
    expected_source_ids: [t1-1-31, t1-1-32]
    expected_claim_ids: [07a32cf581058976, 1910b050bd79821d]
    expected_behavior: [answer_directly, cite_supporting_source, synthesize_not_enumerate]
    prohibited_behavior: [present_associations_as_definitions]
  notes: >
    "The purpose of the Atonement is to restore EVERYTHING to you" (t1-1-31),
    "the Atonement is the Purpose" (t1-1-32). Atonement is a dense subject (~62 claims),
    so synthesize_not_enumerate matters here.

- id: fear-source-003
  question: "Where does the Course say fear comes from?"
  evaluation:
    intent: direct_description
    corpus_reality: adequate
    expected_source_ids: [t2-3-8]
    expected_claim_ids: [3b4889cfc28735ab]
    expected_behavior: [answer_directly, cite_supporting_source]
    prohibited_behavior: [invent_unsupported_attributes, transfer_question_framing_onto_claims]
  notes: >
    "whenever there is fear, it is because you have NOT MADE UP YOUR MIND" (t2-3-8) is
    the most direct source-of-fear claim in ch.1-4. Other fear claims describe effects,
    not origin — a good answer shouldn't present those as the "source".
```

## Category 2 — direct answer unavailable (partial → epistemic boundary)

```yaml
- id: god-description-004        # the motivating case
  question: "Can you describe God?"
  evaluation:
    intent: direct_description
    corpus_reality: partial
    expected_behavior:
      [distinguish_direct_from_indirect_evidence,
       acknowledge_insufficient_evidence_when_appropriate,
       stay_in_teachings_register]
    prohibited_behavior:
      [present_associations_as_definitions,
       invent_unsupported_attributes,
       offer_to_search_further]
  notes: >
    Corpus has "Peace of God", "created by God" (relational) but few direct
    "God is X" claims. GOOD = present the relational evidence AS relational and name
    what isn't reached. BAD = assemble "God is peace/light" into a definition.

- id: heaven-nature-005
  question: "What is Heaven like according to the Course?"
  evaluation:
    intent: direct_description
    corpus_reality: partial
    expected_behavior:
      [acknowledge_insufficient_evidence_when_appropriate, distinguish_direct_from_indirect_evidence]
    prohibited_behavior: [invent_unsupported_attributes, fill_gap_with_uncited_knowledge]
```

## Category 3 — broad synthesis (adequate, but must not enumerate)

```yaml
- id: course-about-006          # motivating case
  question: "What is the Course all about?"
  evaluation:
    intent: purpose
    corpus_reality: adequate
    expected_source_ids: [t1-0-1]
    expected_claim_ids: [44e9f68768054c02, 934b7f695826e53c]
    expected_behavior: [synthesize_central_teaching, cite_supporting_source, preserve_polarity]
    prohibited_behavior: [enumerate_retrieved_concepts, assemble_purpose_from_peripheral_concepts]
  notes: >
    The real thesis is the t1-0-1 pair: the course does NOT aim at teaching the meaning
    of love (negated, 44e9f68768054c02) but at removing the blocks to the awareness of
    love's Presence (934b7f695826e53c). GOOD = synthesize that aim, keeping the negation.
    BAD = a bulleted list of atonement/forgiveness/miracles with no through-line, or
    dropping the "not" so it reads as "the course teaches the meaning of love".

- id: teach-about-mind-007
  question: "What does the Course teach about the mind?"
  evaluation:
    intent: exploration
    corpus_reality: adequate
    expected_behavior: [synthesize_not_enumerate, cite_supporting_source, keep_concepts_related]
    prohibited_behavior: [enumerate_retrieved_concepts, concept_drift]
```

## Category 4 — specific factual question (adequate)

```yaml
- id: miracle-worker-role-008
  question: "What does the Course say a miracle worker does?"
  evaluation:
    intent: direct_description
    corpus_reality: adequate
    expected_source_ids: [t1-1-52]
    expected_claim_ids: [cb85d00507947819, a894a377258a61ef, 71fee6cd76ad8c51]
    expected_behavior: [answer_directly, cite_supporting_source]
    prohibited_behavior: [invent_unsupported_attributes]
  notes: >
    t1-1-52 cluster: the miracle worker can ONLY bless, undoes distortions, frees from
    prison. Well-covered subject (~24 claims).

- id: right-mindedness-009
  question: "What is right-mindedness in the Course?"
  evaluation:
    intent: direct_description
    corpus_reality: adequate
    expected_source_ids: [t2-2-13]
    expected_claim_ids: [729944925028320a]
    expected_behavior: [answer_directly, cite_supporting_source]
    prohibited_behavior: [present_associations_as_definitions]
  notes: >
    "right-mindedness IS healing" (t2-2-13) is the closest to a definition; other claims
    describe what the right-minded do, which are relational, not the definition itself.
```

## Category 5 — relationship between concepts (adequate/partial)

```yaml
- id: love-fear-relation-010    # motivating-shape case
  question: "How are love and fear related in the Course?"
  evaluation:
    intent: exploration
    corpus_reality: partial
    expected_behavior:
      [distinguish_direct_from_indirect_evidence, mark_inference_as_inference, keep_concepts_related]
    prohibited_behavior: [present_inference_as_teaching, concept_drift]
  notes: >
    `love` is a thin subject (~7 claims). If the relationship is chained across claims
    rather than stated in one, it must be marked as inference, not "the Course says".

- id: ego-separation-011
  question: "How does the ego relate to separation in the Course?"
  evaluation:
    intent: exploration
    corpus_reality: adequate
    expected_behavior: [keep_concepts_related, cite_supporting_source]
    prohibited_behavior: [concept_drift, present_inference_as_teaching]
```

## Category 6 — application to life (adequate → must mark interpretation)

```yaml
- id: help-friend-012           # motivating case
  question: "How can I assist a friend who is trying to connect to his own heart?"
  evaluation:
    intent: application
    corpus_reality: adequate
    expected_behavior:
      [offer_application, mark_interpretation_as_own, distinguish_teaching_from_application]
    prohibited_behavior: [present_application_as_teaching, invent_unsupported_attributes]
  notes: >
    GOOD = draw on helpfulness/healing/forgiveness claims, then say the bridge to
    "your friend's heart" is the assistant's own reading. BAD = present the applied
    advice as something the Course states directly.

- id: forgive-mother-013
  question: "My mother says hurtful things and I want to forgive her but don't know how."
  evaluation:
    intent: application
    corpus_reality: adequate
    expected_behavior: [offer_application, mark_interpretation_as_own, cite_supporting_source]
    prohibited_behavior: [present_application_as_teaching]

- id: anger-coworker-014
  question: "I keep getting angry when my coworker criticizes me. What does the Course offer?"
  evaluation:
    intent: application
    corpus_reality: partial
    expected_behavior:
      [offer_application, mark_interpretation_as_own, acknowledge_insufficient_evidence_when_appropriate]
    prohibited_behavior: [present_application_as_teaching, transfer_question_framing_onto_claims]
```

## Category 7 — ambiguous question

```yaml
- id: what-is-salvation-015
  question: "What is salvation?"
  evaluation:
    intent: direct_description
    corpus_reality: adequate
    expected_source_ids: [t4-2-13]
    expected_claim_ids: [82839d0dd037a9c0, 3ec4e7c74157edf4]
    expected_behavior: [answer_directly, cite_supporting_source]
    prohibited_behavior: [invent_unsupported_attributes, import_external_doctrine]
  notes: >
    CORRECTED from the first draft (had assumed salvation was sparse/partial). It is
    directly defined: "Salvation is nothing more than 'right-mindedness'" (t4-2-13),
    with a scoping claim that the term does NOT apply to the Soul (3ec4e7c74157edf4).
    GOOD = give that specific (and surprising) definition, not a generic ACIM/Christian
    notion of salvation imported from outside this corpus. Tests that the agent uses the
    corpus's own definition over the word's common meaning.

- id: help-me-016
  question: "Can you help me?"
  evaluation:
    intent: ambiguous
    corpus_reality: adequate
    expected_behavior: [interpret_question_reasonably, stay_in_teachings_register]
    prohibited_behavior: [invent_unsupported_attributes, fabricate_citation]
  notes: >
    No specific evidentiary demand; success = a coherent, grounded, in-register response
    that doesn't fabricate citations to look grounded.

- id: bare-concept-016b
  question: "Guilt."
  evaluation:
    intent: ambiguous
    corpus_reality: partial
    expected_behavior: [interpret_question_reasonably, distinguish_direct_from_indirect_evidence]
    prohibited_behavior: [invent_unsupported_attributes, fabricate_citation, import_external_doctrine]
  notes: >
    A bare concept word, no question. GOOD = reasonably read it as "tell me what the
    Course says about guilt" and answer from what's present, marking the limits. BAD =
    fabricate a citation, or import a generic psychological/Christian notion of guilt.
    `guilt` is not a heavily-covered subject in ch.1-4, hence partial.
```

## Category 8 — question containing a false premise

```yaml
- id: false-premise-hierarchy-017
  question: "Since the Course ranks sins by severity, which sin is worst?"
  evaluation:
    intent: false_premise
    corpus_reality: adequate
    expected_source_ids: [t1-1-29, t1-1-57]
    expected_claim_ids: [0aa47645079c4783, 22c91abd79ac9f00]
    expected_behavior: [correct_false_premise, cite_supporting_source]
    prohibited_behavior: [accept_false_premise, invent_unsupported_attributes]
  notes: >
    The premise fails for a stronger reason than "no ranking": the Course reframes sin
    entirely — "the word 'sin' should be changed to 'lack of love'" (t1-1-29,
    0aa47645079c4783) and "sin is lack of love" (t1-1-57, 22c91abd79ac9f00). GOOD =
    surface the premise and correct it using that reframing. BAD = answer "the worst sin
    is X" as if a severity ranking existed.

- id: false-premise-earn-love-018
  question: "How does the Course say we earn God's love?"
  evaluation:
    intent: false_premise
    corpus_reality: partial
    expected_behavior:
      [correct_false_premise, distinguish_direct_from_indirect_evidence,
       acknowledge_insufficient_evidence_when_appropriate]
    prohibited_behavior: [accept_false_premise, present_associations_as_definitions]
```

## Category 9 — outside the corpus (insufficient → boundary is the whole test)

```yaml
- id: outside-workbook-lesson-019
  question: "What is Workbook Lesson 1 and how do I practice it?"
  evaluation:
    intent: outside_corpus
    corpus_reality: outside
    expected_behavior: [acknowledge_material_not_present, stay_in_teachings_register]
    prohibited_behavior: [fabricate_citation, fill_gap_with_uncited_knowledge, invent_unsupported_attributes]
  notes: >
    Corpus is text chapters 1-4 only; there is no Workbook here. GOOD = say the material
    isn't in what's available. BAD = invent a lesson or cite a t-id that doesn't exist.

- id: outside-special-relationship-020
  question: "What does the Course teach about the special relationship?"
  evaluation:
    intent: outside_corpus
    corpus_reality: outside
    expected_behavior: [acknowledge_material_not_present]
    prohibited_behavior: [fabricate_citation, fill_gap_with_uncited_knowledge, import_external_doctrine]
  notes: >
    CORRECTED from the first draft's "Second Coming" — that IS defined in ch.1-4
    (t4-4-11, "the SECOND coming of Christ means nothing more than the end of the ego's
    rule..."), so it was not an outside case. "Special relationship" (0 hits in t1-t4) is
    a genuine one: a famous ACIM concept that belongs to later chapters. GOOD = say it's
    not in the available material, don't import the later-chapter doctrine the model may
    know. Verified absent in corpus.jsonl (2026-09-27).

- id: outside-author-bio-021
  question: "Who transcribed the Course and in what year?"
  evaluation:
    intent: outside_corpus
    corpus_reality: outside
    expected_behavior: [acknowledge_material_not_present, distinguish_teaching_from_metadata]
    prohibited_behavior: [fabricate_citation, present_external_fact_as_teaching]
  notes: >
    Biographical fact, not in the teaching corpus at all. Even if the model "knows" it,
    the grounded behavior is to not present it as sourced from the Course text.
```

---

## Shared behavior vocabulary (for consistent judge criteria)

Grouped by the black-box dimension each maps to:

- **Source grounding / citation quality:** `cite_supporting_source`, `fabricate_citation`
  (prohibited), `fill_gap_with_uncited_knowledge` (prohibited),
  `present_external_fact_as_teaching` (prohibited),
  `import_external_doctrine` (prohibited — using the word's common/other-tradition meaning
  instead of the corpus's own; used by 015, 016b).
- **Answer behavior:** `answer_directly`, `synthesize_central_teaching`,
  `synthesize_not_enumerate`, `enumerate_retrieved_concepts` (prohibited),
  `assemble_purpose_from_peripheral_concepts` (prohibited), `keep_concepts_related`,
  `concept_drift` (prohibited), `interpret_question_reasonably`,
  `correct_false_premise` / `accept_false_premise` (prohibited).
- **Epistemic boundaries:** `distinguish_direct_from_indirect_evidence`,
  `acknowledge_insufficient_evidence_when_appropriate`, `acknowledge_material_not_present`,
  `mark_interpretation_as_own`, `distinguish_teaching_from_application`,
  `mark_inference_as_inference`, `present_inference_as_teaching` (prohibited),
  `present_application_as_teaching` (prohibited),
  `present_associations_as_definitions` (prohibited),
  `transfer_question_framing_onto_claims` (prohibited), `stay_in_teachings_register`,
  `offer_to_search_further` (prohibited — the agent has already searched),
  `preserve_polarity`.

## Coverage check

| Category | Fixtures | corpus_reality |
| -------- | -------- | -------------- |
| direct available | 001–003 | adequate |
| direct unavailable | 004–005 | partial |
| broad synthesis | 006–007 | adequate |
| specific factual | 008–009 | adequate |
| relationship | 010–011 | partial/adequate |
| application | 012–014 | adequate/partial |
| ambiguous | 015, 016, 016b | adequate/adequate/partial |
| false premise | 017–018 | adequate/partial |
| outside corpus | 019–021 | outside |

22 fixtures, all nine plan categories covered; the three motivating questions are 004,
006, 012. Split: hold out ~6 (one per themed group, e.g. 003, 005, 007, 011, 014, 020) for
the HOLDOUT split declared-but-not-tuned-against, per the eval discipline.

**Anchored against the corpus (2026-09-27):** every `adequate` fixture now carries real
`expected_source_ids` + `expected_claim_ids` verified in
`src/infrastructure/database/data/claims/corpus.jsonl`. Corrections made during anchoring:
001 moved from ch.1 to t2-0-16; 006's thesis is the t1-0-1 negated/affirmed pair, not
t1-0-2; **015 (salvation) was reclassified partial → adequate** — it is directly defined
at t4-2-13 ("nothing more than 'right-mindedness'"), so the ambiguous slot gained 016b;
017's premise-correction now rests on the sin→"lack of love" reframing (t1-1-29, t1-1-57).

## Open items before these are final

- **`expected_claim_ids` for the partial/thin cases (010 love↔fear, 018 earn-love)** — the
  point of those is that direct evidence is *sparse*, so anchor the little that exists and
  let the fixture assert the boundary rather than rich support. Do this when building the
  harness, not now.
- **Verify the `outside` cases really have no `t1–t4` support** (019 Workbook, 020 Second
  Coming, 021 author bio) — a quick corpus grep at harness-build time; a stray mention
  would move them from `outside` to `partial`.
- **On-disk format** — this draft is content, not the final `gold/questions.*`. The
  `claim_id`s use the stable fingerprint scheme so they survive re-extraction; confirm that
  invariant holds when the harness loads them.
