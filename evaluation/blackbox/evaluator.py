"""The pluggable evaluator seam -- the durable asset the harness is built around.

An `Evaluator` sees only the black-box response (question, answer, sources) and a case's
criteria; it never reaches into the agent's pipeline. `combine` turns the criteria several
evaluators produce into one PASS/FAIL, and the whole gating contract lives in one place:
a case fails iff a *gating* criterion failed. Advisory criteria (graded judge scores) are
recorded but never flip the verdict, and `not_evaluated` is a third state distinct from
`pass` -- it matters while the judges are unvalidated. Adding another judge (System-1,
DeepEval) later means writing one more `Evaluator`, nothing here changes.
"""

from collections.abc import Iterable
from typing import Literal, Protocol

from pydantic import BaseModel

from mind_of_christ_agent.application.answer import (
    CitationDiagnostics,
    CitedClaim,
    InferredChain,
)

from evaluation.blackbox.gold import BlackBoxCase


class BlackBoxResponse(BaseModel):
    """Everything an evaluator is allowed to see: the question and the agent's externally
    visible output. `citation_diagnostics` is part of the visible output (the agent already
    computes it), not a pipeline trace -- the A/B/C diagnostic's trace access is separate."""

    model_config = {"frozen": True}
    question: str
    answer: str
    cited_claims: list[CitedClaim]
    inferred_chains: list[InferredChain]
    citation_diagnostics: CitationDiagnostics


class CriterionResult(BaseModel):
    model_config = {"frozen": True}
    name: str
    kind: Literal["gating", "advisory"]
    status: Literal["pass", "fail", "not_evaluated"]
    score: float | None = None
    detail: str = ""


class CaseResult(BaseModel):
    model_config = {"frozen": True}
    case_id: str
    status: Literal["pass", "fail"]
    criteria: list[CriterionResult]


class Evaluator(Protocol):
    name: str

    def evaluate(
        self, case: BlackBoxCase, response: BlackBoxResponse
    ) -> list[CriterionResult]: ...


def combine(case_id: str, results: Iterable[CriterionResult]) -> CaseResult:
    criteria = list(results)
    failed_gating = any(c.kind == "gating" and c.status == "fail" for c in criteria)
    return CaseResult(
        case_id=case_id,
        status="fail" if failed_gating else "pass",
        criteria=criteria,
    )
