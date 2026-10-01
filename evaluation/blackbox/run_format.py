"""The on-disk shape of a black-box run: a `header` line with provenance and the aggregate
gating score, then one `case` line per fixture recording its verdict and every criterion
result. Provenance carries the agent URL the run hit, the corpus run it was extracted from,
and the gold file hash -- so two runs are only compared when they saw the same product and
the same fixtures. Mirrors the discipline of `evaluation/entities/run_format.py`.
"""

from typing import Literal

from pydantic import BaseModel

from evaluation.blackbox.evaluator import CriterionResult


class ScoreLine(BaseModel):
    passed: int
    total: int
    gating_pass_rate: float


class BlackBoxHeader(BaseModel):
    type: Literal["header"] = "header"
    run_id: str
    created_at: str
    agent_url: str
    model: str
    evaluators: list[str]
    # Which gold split this run scored. Defaults to "dev" so runs recorded before the field
    # existed still load; a holdout number must never be read as a dev number or vice versa.
    split: Literal["dev", "holdout"] = "dev"
    corpus_run_id: str
    gold_sha256: str
    score: ScoreLine


class CaseLine(BaseModel):
    type: Literal["case"] = "case"
    case_id: str
    intent: str
    status: Literal["pass", "fail"]
    criteria: list[CriterionResult]
