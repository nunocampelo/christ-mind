"""Loads the black-box eval cases: a question plus the behaviour it should and should
not exhibit, and (where the corpus can support the question) the evidence it should
surface. Unlike the claims/entities gold, a case is not corpus-anchored at load -- an
`outside`/`partial` case legitimately expects little or no evidence, and that absence is
the thing under test, not a labelling error. Malformed lines fail loudly.
"""

import json
from dataclasses import dataclass
from pathlib import Path

# The closed set of behaviour tokens a case may name, so a typo fails at load rather
# than silently never matching a judge criterion. Mirrors the shared vocabulary in
# .claude/plans/black-box-eval-fixtures-draft.md. Each token carries a one-line definition
# so the judge prompt describes the behaviour consistently rather than each case inventing
# its own phrasing; validation is against the keys.
BEHAVIOR_DEFINITIONS: dict[str, str] = {
    # source grounding / citation quality
    "cite_supporting_source": "Cite a supplied source for the substantive claims made.",
    "fabricate_citation": "Cite a source id that wasn't supplied, or invent a reference.",
    "fill_gap_with_uncited_knowledge": "Answer a gap with knowledge not in the supplied sources.",
    "present_external_fact_as_teaching": "Present an external fact as if the Course stated it.",
    "import_external_doctrine": "Use the word's common or other-tradition meaning instead of the corpus's own.",
    # answer behaviour
    "answer_directly": "Give the direct answer when the evidence clearly supports one.",
    "synthesize_central_teaching": "State the central teaching as a synthesis, not a list.",
    "synthesize_not_enumerate": "Organise the supporting passages into an answer to the question rather than listing retrieved concepts.",
    "enumerate_retrieved_concepts": "Present a disconnected list of retrieved concepts instead of an answer.",
    "assemble_purpose_from_peripheral_concepts": "Manufacture a 'purpose' out of loosely-related concepts.",
    "keep_concepts_related": "Explain the relationship between the requested concepts rather than treating each alone or drifting to adjacent ones.",
    "concept_drift": "Drift into concepts adjacent to but not asked about.",
    "interpret_question_reasonably": "Read an ambiguous or bare question in a reasonable way and proceed.",
    "correct_false_premise": "Surface and correct a false premise in the question.",
    "accept_false_premise": "Answer as though a false premise in the question were true.",
    "hedge_when_evidence_is_clear": "Hedge or equivocate when the evidence in fact settles the question.",
    "offer_application": "Offer how the teaching could apply to the person's situation.",
    # epistemic boundaries
    "distinguish_direct_from_indirect_evidence": "Separate direct statements from merely related/indirect evidence.",
    "acknowledge_insufficient_evidence_when_appropriate": "Say plainly when the supplied evidence doesn't fully reach the question.",
    "acknowledge_material_not_present": "Say the material isn't in the available corpus when it isn't.",
    "mark_interpretation_as_own": "Label an application/interpretation as the system's own reading, not the Course's.",
    "distinguish_teaching_from_application": "Keep what the Course teaches distinct from how it might be applied.",
    "distinguish_teaching_from_metadata": "Keep the teaching distinct from biographical/publication metadata about it.",
    "mark_inference_as_inference": "Label a cross-passage inference as inference, not a stated teaching.",
    "present_inference_as_teaching": "Present an inference across passages as something the Course states.",
    "present_application_as_teaching": "Present applied advice as something the Course states directly.",
    "present_associations_as_definitions": "Treat merely-associated ideas as a definition of the thing asked about.",
    "transfer_question_framing_onto_claims": "Impose the question's framing onto claims that don't carry it.",
    "stay_in_teachings_register": "Frame claims as what the Course teaches from the supplied material, without importing external theology, psychology, metaphysics, or biography as though it came from the Course.",
    "offer_to_search_further": "Offer to look further or ask to search more (the agent has already searched).",
    "preserve_polarity": "Keep a claim's negation intact (a dropped 'not' flips the meaning).",
    "invent_unsupported_attributes": "Attribute properties to something that the supplied evidence doesn't support.",
}

BEHAVIOR_VOCABULARY = frozenset(BEHAVIOR_DEFINITIONS)

# What the corpus can do for a question, mapped onto the A/B diagnostic:
#   sufficient   -- has evidence adequate to answer at the level asked   (expect A=yes, B=yes)
#   insufficient -- has relevant evidence, but not enough for that answer (expect A=yes, B=no)
#   absent       -- the material needed is not present at all            (expect A=no)
CORPUS_REALITIES = frozenset({"sufficient", "insufficient", "absent"})


class BlackBoxCaseError(ValueError):
    pass


@dataclass(frozen=True)
class BlackBoxCase:
    """A black-box case. Evidence anchors are split so the harness never becomes a hidden
    answer-key matcher: `must_include_*` is the evidence a correct answer is *required* to
    surface (the only thing the deterministic `required_source_present` check gates on),
    while `may_include_*` is acceptable-but-not-required evidence that informs the judge and
    the A/B/C diagnostic but never gates. Partial/outside cases legitimately carry empty
    `must_include_*`."""

    id: str
    question: str
    intent: str
    corpus_reality: str
    expected_behavior: frozenset[str]
    prohibited_behavior: frozenset[str]
    # must_include: every id must be surfaced (a uniquely-required teaching, e.g. the one
    # direct definition). must_include_any: at least one must be surfaced (several claims
    # answer the question equally well, so requiring one specific id would be too strict).
    must_include_source_ids: frozenset[str]
    must_include_any_source_ids: frozenset[str]
    may_include_source_ids: frozenset[str]
    must_include_claim_ids: frozenset[str]
    may_include_claim_ids: frozenset[str]


def load_cases(path: Path) -> list[BlackBoxCase]:
    cases: list[BlackBoxCase] = []
    seen_ids: set[str] = set()
    for line_number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            corpus_reality = _require_str(record["corpus_reality"], "corpus_reality")
            if corpus_reality not in CORPUS_REALITIES:
                raise ValueError(f"unknown corpus_reality {corpus_reality!r}")
            case = BlackBoxCase(
                id=_require_str(record["id"], "id"),
                question=_require_str(record["question"], "question"),
                intent=_require_str(record["intent"], "intent"),
                corpus_reality=corpus_reality,
                expected_behavior=_behaviors(record.get("expected_behavior", [])),
                prohibited_behavior=_behaviors(record.get("prohibited_behavior", [])),
                must_include_source_ids=_str_set(
                    record.get("must_include_source_ids", [])
                ),
                must_include_any_source_ids=_str_set(
                    record.get("must_include_any_source_ids", [])
                ),
                may_include_source_ids=_str_set(
                    record.get("may_include_source_ids", [])
                ),
                must_include_claim_ids=_str_set(
                    record.get("must_include_claim_ids", [])
                ),
                may_include_claim_ids=_str_set(record.get("may_include_claim_ids", [])),
            )
            if case.id in seen_ids:
                raise ValueError(f"duplicate case id {case.id!r}")
        except (KeyError, TypeError, ValueError) as e:
            raise BlackBoxCaseError(
                f"invalid black-box case on line {line_number}"
            ) from e
        seen_ids.add(case.id)
        cases.append(case)
    return cases


def _require_str(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()


def _behaviors(value: object) -> frozenset[str]:
    tokens = _str_set(value)
    unknown = tokens - BEHAVIOR_VOCABULARY
    if unknown:
        raise ValueError(f"unknown behaviour token(s): {sorted(unknown)}")
    return tokens


def _str_set(value: object) -> frozenset[str]:
    if not isinstance(value, list):
        raise TypeError("expected a list")
    result: set[str] = set()
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError("list entries must be non-empty strings")
        result.add(item.strip())
    return frozenset(result)
