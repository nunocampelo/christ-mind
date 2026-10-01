"""Shared judging machinery for the frozen-answer diagnostics.

`capture_flagged.py` (live-ask, five flagged cases) and `calibration/run.py` (frozen
fixtures, the validation harness) both freeze an answer and re-judge it N times to separate
judge variability from answer drift. The freeze/re-judge/dump pieces live here so the two
scripts share one implementation; each script keeps only its own orchestration.
"""

import statistics
from dataclasses import dataclass

from evaluation.blackbox.client import A2AAgentClient
from evaluation.blackbox.evaluator import BlackBoxResponse
from evaluation.blackbox.gold import BlackBoxCase
from evaluation.blackbox.harness import live_stack
from evaluation.blackbox.llm_judge import LLMEvaluator


@dataclass
class Frozen:
    case: BlackBoxCase
    response: BlackBoxResponse


def ask_once(cases: list[BlackBoxCase], agent_url: str) -> list[Frozen]:
    """Ask each case once over the live stack and freeze the answer + its full evidence."""
    with live_stack(agent_url=agent_url) as url:
        client = A2AAgentClient(url)
        return [Frozen(case, client.ask(case.question)) for case in cases]


def judge_repeated(
    judge: LLMEvaluator, case: BlackBoxCase, response: BlackBoxResponse, repeats: int
) -> dict[str, object]:
    """Score the SAME frozen answer `repeats` times. Spread here is judge variability only."""
    per_trial: list[dict[str, float | None]] = []
    for _ in range(repeats):
        per_trial.append({c.name: c.score for c in judge.evaluate(case, response)})
    names = sorted({name for trial in per_trial for name in trial})
    summary: dict[str, object] = {}
    for name in names:
        vals = [t[name] for t in per_trial if t.get(name) is not None]
        floats = [v for v in vals if isinstance(v, float)]
        summary[name] = {
            "scores": [t.get(name) for t in per_trial],
            "n_scored": len(floats),
            "min": min(floats) if floats else None,
            "max": max(floats) if floats else None,
            "mean": round(statistics.fmean(floats), 3) if floats else None,
            "stdev": round(statistics.pstdev(floats), 3) if len(floats) > 1 else None,
        }
    return summary


def claim_dump(response: BlackBoxResponse) -> list[dict[str, object]]:
    """Human-readable dump of the cited claims with offsets, for reviewer records."""
    return [
        {
            "claim_id": c.claim_id,
            "source_id": c.source_id,
            "subject": c.subject,
            "predicate": c.predicate,
            "object": c.object,
            "polarity": c.polarity,
            "evidence": c.evidence,
            "evidence_context": c.evidence_context,
            "evidence_start": c.evidence_start,
            "evidence_end": c.evidence_end,
        }
        for c in response.cited_claims
    ]
