"""The LLM judge: the behavioural criteria that need judgment, not code. Scored 0-1 and
advisory *pending validation* -- a judge signal does not gate a case until its calls have
been checked against human judgment on these fixtures (a System-1 model's general benchmarks
are not this domain). `premature_abstention` is the first criterion intended to graduate to
gating once validated; until then it, like the rest, is advisory. The judge sees only the
black-box output plus the case's expected/prohibited behaviour, never a pipeline trace and
never the `corpus_reality` label -- it reports observations (including whether the answer
abstained), and the evaluator does the policy join against the fixture's corpus_reality. A
reply it can't parse yields `not_evaluated`, not a spurious fail: an unreachable or confused
judge must not flip a verdict it never actually made.
"""

import hashlib
import json
import re
from typing import Literal

from application.extraction.prompt import Complete
from evaluation.blackbox.evaluator import BlackBoxResponse, CriterionResult
from evaluation.blackbox.gold import BlackBoxCase
from infrastructure.llm.anthropic_proxy import AnthropicProxyError

_FailureReason = Literal["provider_failure", "parse_failure", "incomplete_coverage"]

# A citation marker in rendered answer prose: a 16-hex claim id in brackets (the shape the
# citation-integrity guard enforces). Coverage is measured against the OCCURRENCES of these in
# the answer -- the authoritative record of what the answer actually cited and where -- never
# the retrieved `cited_claims` pool, which includes claims the answer never used.
_MARKER = re.compile(r"\[([0-9a-f]{16})\]")

# The advisory criteria the judge scores. `semantic_grounding` returns a per-assertion array
# (floor applied in code), the rest a 0-1 the judge returns with a pass threshold for display.
_SCALAR_CRITERIA = (
    "answers_question",
    "synthesis_fidelity",
    "epistemic_boundary",
    "interpretation_marked",
)
_CRITERIA = (
    "answers_question",
    "semantic_grounding",
    "synthesis_fidelity",
    "epistemic_boundary",
    "interpretation_marked",
)
# The score at or above which a criterion counts as pass. Display-only for the five scored
# criteria, but load-bearing for `premature_abstention`'s polarity flip -- and the value the
# calibration harness joins judge scores against, so it records it in each result's provenance.
PASS_THRESHOLD = 0.6

SYSTEM_PROMPT = """\
You are grading one answer from a system that must speak only from a fixed body of source \
passages (A Course in Miracles, Original Edition). You see the user's question, the answer, \
and the cited claims -- each given as its short extracted clause AND its full source \
paragraph. A citation marker licenses that claim's whole source paragraph, not only the \
clause: an assertion carrying a marker is grounded when the paragraph of THAT marker's claim \
supports it, even if the exact words fall outside the clause (support, not proximity). An \
assertion whose marker points to a paragraph that does not support it is ungrounded even if \
some OTHER supplied paragraph would -- that is a mis-cited marker, not grounding. Judge only \
what is in front of you; do not use outside knowledge of the Course.

Return ONLY a JSON object. Most criteria map to a number from 0.0 to 1.0; \
semantic_grounding is the exception -- it maps to a JSON ARRAY, described below.
- answers_question: does the answer respond appropriately to the question GIVEN the evidence \
available to it? A direct answer when the evidence supports one scores high; so does a \
justified refusal or a request for the detail needed when the corpus cannot answer or the \
question is underspecified. Score low only for evading an answerable question or drifting off \
what was asked -- not for declining when declining is the right response.
- semantic_grounding: NOT a number -- a JSON ARRAY, one element per SUBSTANTIVE assertion in \
the answer (every claim the answer makes about the subject matter; skip pure connective or \
meta sentences like "Here is what the passages say"). Include assertions that carry NO marker \
too. Each element is {"assertion": "<the asserted span, copied VERBATIM from the answer, \
character-for-character, INCLUDING any [id] citation markers inside it>", "char_start": <int>, \
"char_end": <int>, "supported_by_its_markers": true|false, "quote": "<exact words from the \
paragraph of ONE of this assertion's own markers that support it, or empty>"}. char_start and \
char_end are 0-based offsets into the ANSWER such that answer[char_start:char_end] is exactly \
"assertion" -- so the span is located by its offsets, not by searching text. Do NOT paraphrase \
or move a marker. The spans must PARTITION the citations: every [id] marker in the answer must \
fall inside exactly ONE element's [char_start, char_end), and spans must not overlap -- so if \
the same id appears twice in the answer, each occurrence sits in a different element's span. \
"supported_by_its_markers" is true ONLY when the paragraph of a marker INSIDE this span \
supports the assertion (support, not proximity; wording outside the clause is fine) -- it is \
FALSE for a mis-cited marker whose paragraph does not support the assertion EVEN IF some other \
supplied paragraph would, and FALSE for any substantive assertion with no marker in its span \
(an uncited claim is ungrounded). Do not average: one false element means not fully grounded.
- synthesis_fidelity: does it stay faithful to the cited paragraphs -- preserving their \
attribution, polarity, and qualifications -- without overreach, conflation, or attributes no \
paragraph carries?
- epistemic_boundary: where the evidence is thin or absent, does it say so plainly rather \
than filling the gap? (1.0 if no gap to acknowledge.)
- interpretation_marked: is any inference or application labelled as the system's own \
reading rather than presented as the Course's teaching? (1.0 if none was drawn.)
- abstained: does the answer decline to engage -- say the material isn't present, that it \
can't answer, or confine itself to peripheral remarks -- rather than either answering the \
question OR asking for a detail it genuinely needs to answer? 1.0 = fully declines/abstains, \
0.0 = answers directly or requests necessary clarification. A request for information the \
question actually requires is NOT abstention. Report only what the answer does; do NOT judge \
whether declining was appropriate.

No prose, no code fences -- just the JSON object."""

# Bump by hand when a grading rule changes, so a calibration result pins the rubric it
# validated (mirrors application.extraction.prompt.PROMPT_VERSION). The hash catches an edit
# that forgot to bump the version.
PROMPT_VERSION = "1.3"


def prompt_hash() -> str:
    return hashlib.sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest()[:16]


class LLMEvaluator:
    name = "llm_judge"

    def __init__(self, complete: Complete):
        self._complete = complete

    def evaluate(
        self, case: BlackBoxCase, response: BlackBoxResponse
    ) -> list[CriterionResult]:
        user = _user_prompt(case, response)
        # Two disjoint failure boundaries: the proxy call (provider_failure) and parsing the
        # reply (parse_failure). Each is caught at its own narrow site -- a provider outage and
        # a malformed reply are different facts, and a non-proxy, non-parse bug propagates.
        try:
            reply = self._complete(SYSTEM_PROMPT, user)
        except AnthropicProxyError:
            return _all_unavailable("provider_failure", "judge call failed")
        try:
            parsed = _parse_object(reply)
        except (ValueError, json.JSONDecodeError):
            return _all_unavailable("parse_failure", "judge reply was not parseable JSON")

        results = [_scored(name, parsed.get(name)) for name in _SCALAR_CRITERIA]
        results.append(_grounding(parsed.get("semantic_grounding"), response))
        results.append(_premature_abstention(case, _as_score(parsed.get("abstained"))))
        return results


def _all_unavailable(
    reason: _FailureReason, detail: str
) -> list[CriterionResult]:
    names = (*_CRITERIA, "premature_abstention")
    return [_not_evaluated(name, detail, reason) for name in names]


def _scored(name: str, raw: object) -> CriterionResult:
    value = _as_score(raw)
    if value is None:
        return _not_evaluated(name, "criterion missing from judge reply", "parse_failure")
    return CriterionResult(
        name=name,
        kind="advisory",
        status="pass" if value >= PASS_THRESHOLD else "fail",
        score=value,
    )


def _grounding(raw: object, response: BlackBoxResponse) -> CriterionResult:
    """Deterministic per-assertion floor over the answer's OWN citation occurrences.

    The judge returns one element per substantive assertion, each a verbatim span of the answer.
    Python -- not the judge -- decides what is grounded: it locates each span in the answer,
    reads the marker occurrences the answer actually places inside that span (the judge cannot
    relabel them), and requires the elements to partition every marker occurrence in the answer
    exactly once. Status is `all_assertions_supported`, independent of PASS_THRESHOLD; the score
    is the supported fraction, diagnostic only.

    Coverage is defined against the answer's `[id]` occurrences, NOT `response.cited_claims`:
    the retrieval pool holds claims the answer never cited, and the same id can appear twice on
    two different clauses (one sound, one mis-cited) -- a per-occurrence partition is what keeps
    the mis-cited use from hiding behind the sound one. Anything that can't be verified
    (unlocatable span, overlapping spans, an uncovered occurrence) is `not_evaluated` rather
    than a guessed pass/fail, so an omission can't manufacture a pass."""
    name = "semantic_grounding"
    try:
        elements = _parse_grounding_elements(raw)
    except ValueError:
        return _not_evaluated(name, "grounding array malformed", "parse_failure")

    answer = response.answer
    # Each occurrence is (start, end, id): a span must contain the WHOLE marker, bracket to
    # bracket, to count it -- a span clipped mid-marker neither covers nor silently drops it.
    occurrences = [(m.start(), m.end(), m.group(1)) for m in _MARKER.finditer(answer)]
    if not occurrences and not elements:
        # No citation in the answer and no substantive assertion to ground (an abstention or a
        # pure clarification request). Not a failure and nothing to score -- no failure_reason,
        # so it never joins a bucket count; the human verdict for these is not_applicable.
        return _not_evaluated(name, "no cited markers and no asserted grounding", None)

    supplied = {c.claim_id for c in response.cited_claims}
    covered: set[int] = set()
    spans: list[tuple[int, int]] = []
    verdicts: list[bool] = []
    for el in elements:
        # Offsets, not substring search: an identical sentence appearing twice is unambiguous.
        if not (0 <= el.char_start < el.char_end <= len(answer)):
            return _not_evaluated(
                name, "grounding offsets are out of range", "parse_failure"
            )
        if answer[el.char_start : el.char_end] != el.assertion:
            return _not_evaluated(
                name, "grounding offsets do not match the answer text", "parse_failure"
            )
        # Text-range overlap, independent of markers: the prompt requires a partition, so two
        # spans that overlap at all (even over marker-free prose) is a malformed judgment.
        if any(el.char_start < e and s < el.char_end for s, e in spans):
            return _not_evaluated(
                name, "grounding spans overlap", "parse_failure"
            )
        spans.append((el.char_start, el.char_end))
        # A marker counts for this span only if the WHOLE [id] sits inside it. A span that
        # clips a marker (one bracket in, the rest out) is a malformed anchor, not a miss.
        clipped = any(
            (el.char_start <= ms < el.char_end) != (el.char_start < me <= el.char_end)
            for ms, me, _ in occurrences
        )
        if clipped:
            return _not_evaluated(
                name, "grounding span cuts through a marker", "parse_failure"
            )
        span = [
            (ms, cid)
            for ms, me, cid in occurrences
            if el.char_start <= ms and me <= el.char_end
        ]
        covered.update(ms for ms, _ in span)
        # An answer marker that resolves to no supplied claim is a grounding DEFECT (the answer
        # mis-cited), not an unverifiable judgment -- so it fails, it does not degrade.
        resolves = all(cid in supplied for _, cid in span)
        # An assertion whose span carries no marker is uncited -- ungrounded in code, never on
        # the judge's say-so (it must not pass an uncited claim).
        verdicts.append(el.supported and bool(span) and resolves)

    if {ms for ms, _, _ in occurrences} - covered:
        return _not_evaluated(
            name,
            "grounding did not account for every marker occurrence in the answer",
            "incomplete_coverage",
        )

    # NOTE: complete occurrence coverage proves every CITED span was examined; it does NOT prove
    # the judge included every uncited substantive assertion (those carry no marker to count).
    # That gap stays with the model's instruction, not an enforceable code check.
    total = len(verdicts)
    supported = sum(verdicts)
    all_supported = total > 0 and supported == total
    return CriterionResult(
        name=name,
        kind="advisory",
        status="pass" if all_supported else "fail",
        score=round(supported / total, 3) if total else 0.0,
    )


def _not_evaluated(
    name: str, detail: str, reason: _FailureReason | None
) -> CriterionResult:
    return CriterionResult(
        name=name,
        kind="advisory",
        status="not_evaluated",
        detail=detail,
        failure_reason=reason,
    )


def _premature_abstention(case: BlackBoxCase, abstained: float | None) -> CriterionResult:
    """The policy join of two independent signals: the judge's `abstained` observation and the
    fixture's `corpus_reality`. Premature = the agent abstained on a question the corpus can
    actually answer. Only defined for `sufficient` cases; `absent`/`insufficient` are out of
    this criterion's scope (it makes no claim about abstention quality there). Advisory pending
    validation. A missing `abstained` degrades to not_evaluated -- never a spurious signal."""
    name = "premature_abstention"
    if case.corpus_reality != "sufficient":
        # Out of scope, not a failure -- no failure_reason, so it never joins a bucket count.
        return _not_evaluated(name, "only scored when corpus_reality is sufficient", None)
    if abstained is None:
        return _not_evaluated(name, "abstained missing from judge reply", "parse_failure")
    return CriterionResult(
        name=name,
        kind="advisory",
        status="fail" if abstained >= PASS_THRESHOLD else "pass",
        score=abstained,
        detail="abstained despite sufficient corpus evidence" if abstained >= PASS_THRESHOLD else "",
    )


def _parse_object(reply: str) -> dict[str, object]:
    parsed = json.loads(reply.strip())
    if not isinstance(parsed, dict):
        raise ValueError("judge reply was not a JSON object")
    return parsed


def _as_score(raw: object) -> float | None:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    return max(0.0, min(1.0, float(raw)))


class _GroundingElement:
    __slots__ = ("assertion", "char_start", "char_end", "supported")

    def __init__(self, assertion: str, char_start: int, char_end: int, supported: bool):
        self.assertion = assertion
        self.char_start = char_start
        self.char_end = char_end
        self.supported = supported


def _parse_grounding_elements(raw: object) -> list[_GroundingElement]:
    """Validate the grounding array into located (assertion, offsets, supported) elements.
    Markers are NOT taken from the element -- they are read from the answer at the element's
    offsets (see `_grounding`), so a judge cannot relabel which id sits on a clause. Raises
    ValueError on any malformed shape; the caller turns that into `not_evaluated`."""
    if not isinstance(raw, list):
        raise ValueError("semantic_grounding was not a JSON array")
    elements: list[_GroundingElement] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("grounding element was not an object")
        assertion = item.get("assertion")
        if not isinstance(assertion, str) or not assertion.strip():
            raise ValueError("grounding element missing an assertion string")
        start = item.get("char_start")
        end = item.get("char_end")
        if (
            isinstance(start, bool)
            or isinstance(end, bool)
            or not isinstance(start, int)
            or not isinstance(end, int)
            or start < 0
            or end < start
        ):
            raise ValueError("grounding element has invalid char offsets")
        supported = item.get("supported_by_its_markers")
        if not isinstance(supported, bool):
            raise ValueError("grounding element supported_by_its_markers was not a bool")
        elements.append(_GroundingElement(assertion, start, end, supported))
    return elements


def _user_prompt(case: BlackBoxCase, response: BlackBoxResponse) -> str:
    # A marker licenses the claim's whole source paragraph, so grading needs that paragraph,
    # not only the extracted clause (the clause is the retrieval anchor). Fall back to the
    # clause where the paragraph was unavailable (evidence_context defaults to "").
    claims = "\n\n".join(
        f"- [{c.claim_id}] clause: {c.evidence}\n"
        f"  source paragraph: {c.evidence_context or c.evidence}"
        for c in response.cited_claims
    ) or "(no claims cited)"
    expected = ", ".join(sorted(case.expected_behavior)) or "(none)"
    prohibited = ", ".join(sorted(case.prohibited_behavior)) or "(none)"
    return (
        f"QUESTION:\n{response.question}\n\n"
        f"ANSWER:\n{response.answer}\n\n"
        f"CITED CLAIMS (clause + its source paragraph):\n{claims}\n\n"
        f"This question's intent: {case.intent}. "
        f"Expected behaviours: {expected}. Prohibited: {prohibited}."
    )


def make_llm_judge() -> LLMEvaluator:
    from infrastructure.llm.anthropic_proxy import make_complete

    return LLMEvaluator(make_complete())
