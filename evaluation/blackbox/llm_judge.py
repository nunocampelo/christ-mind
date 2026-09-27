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

import json

from application.extraction.prompt import Complete
from evaluation.blackbox.evaluator import BlackBoxResponse, CriterionResult
from evaluation.blackbox.gold import BlackBoxCase

# The advisory criteria the judge scores. Names match the fixtures' behaviour vocabulary
# family; each is a 0-1 the judge returns, with a pass threshold applied only for display.
_CRITERIA = (
    "answers_question",
    "semantic_grounding",
    "synthesis_fidelity",
    "epistemic_boundary",
    "interpretation_marked",
)
_PASS_THRESHOLD = 0.6

SYSTEM_PROMPT = """\
You are grading one answer from a system that must speak only from a fixed body of source \
passages (A Course in Miracles, Original Edition). You see the user's question, the \
answer, and the exact source claims the answer was allowed to cite. Judge only what is in \
front of you; do not use outside knowledge of the Course.

Return ONLY a JSON object mapping each criterion to a number from 0.0 to 1.0:
- answers_question: does the answer address the actual question asked?
- semantic_grounding: is every substantive assertion supported by the cited claims (not \
just plausible)?
- synthesis_fidelity: does it stay within what the evidence supports, without overreach, \
conflation, or invented attributes?
- epistemic_boundary: where the evidence is thin or absent, does it say so plainly rather \
than filling the gap? (1.0 if no gap to acknowledge.)
- interpretation_marked: is any inference or application labelled as the system's own \
reading rather than presented as the Course's teaching? (1.0 if none was drawn.)
- abstained: does the answer decline to answer -- say the material isn't present, that it \
can't answer, or confine itself to peripheral remarks -- rather than actually answering the \
question? 1.0 = fully declines/abstains, 0.0 = answers directly. Report only what the answer \
does; do NOT judge whether abstaining was appropriate.

No prose, no code fences -- just the JSON object."""


class LLMEvaluator:
    name = "llm_judge"

    def __init__(self, complete: Complete):
        self._complete = complete

    def evaluate(
        self, case: BlackBoxCase, response: BlackBoxResponse
    ) -> list[CriterionResult]:
        user = _user_prompt(case, response)
        try:
            reply = self._complete(SYSTEM_PROMPT, user)
            scores = _parse_scores(reply)
        except Exception:  # noqa: BLE001 -- any judge failure degrades to not_evaluated
            results = [_not_evaluated(name, "judge reply unavailable") for name in _CRITERIA]
            return results + [
                _not_evaluated("premature_abstention", "judge reply unavailable")
            ]
        results = [_scored(name, scores.get(name)) for name in _CRITERIA]
        return results + [_premature_abstention(case, scores.get("abstained"))]


def _scored(name: str, value: float | None) -> CriterionResult:
    if value is None:
        return _not_evaluated(name, "criterion missing from judge reply")
    return CriterionResult(
        name=name,
        kind="advisory",
        status="pass" if value >= _PASS_THRESHOLD else "fail",
        score=value,
    )


def _not_evaluated(name: str, detail: str) -> CriterionResult:
    return CriterionResult(
        name=name, kind="advisory", status="not_evaluated", detail=detail
    )


def _premature_abstention(case: BlackBoxCase, abstained: float | None) -> CriterionResult:
    """The policy join of two independent signals: the judge's `abstained` observation and the
    fixture's `corpus_reality`. Premature = the agent abstained on a question the corpus can
    actually answer. Only defined for `sufficient` cases; `absent`/`insufficient` are out of
    this criterion's scope (it makes no claim about abstention quality there). Advisory pending
    validation. A missing `abstained` degrades to not_evaluated -- never a spurious signal."""
    name = "premature_abstention"
    if case.corpus_reality != "sufficient":
        return _not_evaluated(name, "only scored when corpus_reality is sufficient")
    if abstained is None:
        return _not_evaluated(name, "abstained missing from judge reply")
    return CriterionResult(
        name=name,
        kind="advisory",
        status="fail" if abstained >= _PASS_THRESHOLD else "pass",
        score=abstained,
        detail="abstained despite sufficient corpus evidence" if abstained >= _PASS_THRESHOLD else "",
    )


def _parse_scores(reply: str) -> dict[str, float]:
    parsed = json.loads(reply.strip())
    if not isinstance(parsed, dict):
        raise ValueError("judge reply was not a JSON object")
    scores: dict[str, float] = {}
    for key, value in parsed.items():
        if isinstance(key, str) and isinstance(value, (int, float)) and not isinstance(
            value, bool
        ):
            scores[key] = max(0.0, min(1.0, float(value)))
    return scores


def _user_prompt(case: BlackBoxCase, response: BlackBoxResponse) -> str:
    claims = "\n".join(
        f"- [{c.claim_id}] {c.evidence}" for c in response.cited_claims
    ) or "(no claims cited)"
    expected = ", ".join(sorted(case.expected_behavior)) or "(none)"
    prohibited = ", ".join(sorted(case.prohibited_behavior)) or "(none)"
    return (
        f"QUESTION:\n{response.question}\n\n"
        f"ANSWER:\n{response.answer}\n\n"
        f"CITED CLAIMS:\n{claims}\n\n"
        f"This question's intent: {case.intent}. "
        f"Expected behaviours: {expected}. Prohibited: {prohibited}."
    )


def make_llm_judge() -> LLMEvaluator:
    from infrastructure.llm.anthropic_proxy import make_complete

    return LLMEvaluator(make_complete())
