"""Diagnostic: recover the judge-flagged answers the run file does not persist, and measure
how much the LLM judge's scores vary on a FROZEN answer.

The recorded run stores scores/criteria only -- no answer text, no cited claims, no passages.
This brings up the live stack, asks each flagged case ONCE, freezes that answer + its full
evidence (including `evidence_context`, the source paragraph the agent was shown), and then:

  1. judges the SAME frozen answer `--repeats` times, so score spread reflects judge
     variability alone, not answer regeneration (asking again would change the answer AND the
     judgment, confounding the two);
  2. runs a classification pass that SEES THE PASSAGE and sorts each questionable assertion
     into one of three buckets -- supported by the cited claim clause, supported by its source
     paragraph but outside the claim's scope, or unsupported by any supplied source -- because
     those need different fixes and the earlier clause-only pass could not tell them apart.

Both extra passes are advisory reviewer aids, not verdicts. The persisted record carries full
provenance (run_id, model, agent_url) and the full evidence_context + offsets so a reviewer
can check every assertion against the paragraph the agent actually had.

Not part of the suite. Run from the repo root with the live-stack prerequisites (harness.py):
DATABASE_URL set, Docker and cproxy available.
"""

import argparse
import json
import os
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from application.extraction.prompt import Complete
from infrastructure.config.env import load_env
from infrastructure.llm.anthropic_proxy import make_complete

from evaluation.blackbox.client import A2AAgentClient
from evaluation.blackbox.evaluator import BlackBoxResponse
from evaluation.blackbox.gold import BlackBoxCase, load_cases
from evaluation.blackbox.harness import live_stack
from evaluation.blackbox.llm_judge import LLMEvaluator, make_llm_judge

_FLAGGED = (
    "god-description-004",
    "miracle-worker-role-008",
    "atonement-definition-022",
    "ego-definition-023",
    "mind-definition-025",
)

_GOLD = Path(__file__).resolve().parent / "gold" / "cases.jsonl"
_OUT_DIR = Path(__file__).resolve().parent / "review"

# The classification pass's distinction. The agent's answer prompt shows the whole passage but
# states the cited CLAIM (not the passage) is the licence, so an assertion can be true to the
# paragraph yet outside the claim's scope -- a scope question, not an invention. Only
# `no_source_support` is a fabrication. These three need different fixes; keep them apart.
_SCOPE_SYSTEM = """\
You are auditing one answer from a system that may speak only from a fixed body of source \
passages (A Course in Miracles, Original Edition). For each cited claim you are given the \
exact clause the claim asserts AND the full source paragraph it was drawn from.

Find every substantive assertion in the answer that a cited claim marker is attached to, and \
classify each into exactly one bucket:
- "clause_supported": the assertion is supported by the cited claim's own clause.
- "passage_supported_outside_claim": the assertion is NOT in the cited claim's clause but IS \
stated in that claim's source paragraph (so it is true to the source but broader than the \
claim the marker names).
- "no_source_support": the assertion is in neither the clause nor any supplied paragraph.

Return ONLY a JSON array; each element: {"assertion": "<quoted words from the answer>", \
"marker": "<cited claim_id>", "bucket": "<one of the three>", "note": "<one short reason>"}. \
No prose outside the JSON, no code fences."""


@dataclass
class _Frozen:
    case: BlackBoxCase
    response: BlackBoxResponse


def _ask_once(cases: list[BlackBoxCase], agent_url: str) -> list[_Frozen]:
    with live_stack(agent_url=agent_url) as url:
        client = A2AAgentClient(url)
        return [_Frozen(case, client.ask(case.question)) for case in cases]


def _judge_repeated(
    judge: LLMEvaluator, case: BlackBoxCase, response: BlackBoxResponse, repeats: int
) -> dict[str, object]:
    """Score the SAME frozen answer `repeats` times. Spread here is judge variability only."""
    per_trial: list[dict[str, float | None]] = []
    for _ in range(repeats):
        per_trial.append(
            {c.name: c.score for c in judge.evaluate(case, response)}
        )
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


def _scope_audit(complete: Complete, response: BlackBoxResponse) -> object:
    claims = "\n\n".join(
        f"[{c.claim_id}] source {c.source_id}\n"
        f"  CLAIM CLAUSE: {c.evidence!r}\n"
        f"  SOURCE PARAGRAPH: {c.evidence_context!r}"
        for c in response.cited_claims
    ) or "(no claims cited)"
    user = (
        f"QUESTION:\n{response.question}\n\n"
        f"ANSWER:\n{response.answer}\n\n"
        f"CITED CLAIMS (clause + its source paragraph):\n{claims}"
    )
    reply = complete(_SCOPE_SYSTEM, user)
    try:
        return json.loads(reply.strip())
    except json.JSONDecodeError:
        return {"_raw": reply}


def _claim_dump(response: BlackBoxResponse) -> list[dict[str, object]]:
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


def _record(
    frozen: _Frozen,
    judge: LLMEvaluator,
    complete: Complete,
    repeats: int,
) -> dict[str, object]:
    case, response = frozen.case, frozen.response
    return {
        "case_id": case.id,
        "question": case.question,
        "corpus_reality": case.corpus_reality,
        "expected_behavior": sorted(case.expected_behavior),
        "prohibited_behavior": sorted(case.prohibited_behavior),
        "gold_required": {
            "must_include_source_ids": sorted(case.must_include_source_ids),
            "must_include_any_source_ids": sorted(case.must_include_any_source_ids),
            "must_include_claim_ids": sorted(case.must_include_claim_ids),
            "must_include_any_claim_ids": sorted(case.must_include_any_claim_ids),
            "may_include_claim_ids": sorted(case.may_include_claim_ids),
        },
        "answer": response.answer,
        "cited_claims": _claim_dump(response),
        "cited_source_ids": sorted({c.source_id for c in response.cited_claims}),
        "citation_diagnostics": {
            "unknown_ids": response.citation_diagnostics.unknown_ids,
            "unused_claim_ids": response.citation_diagnostics.unused_claim_ids,
        },
        "judge_variability": _judge_repeated(judge, case, response, repeats),
        "scope_audit": _scope_audit(complete, response),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repeats",
        type=int,
        default=5,
        help="times to re-judge each FROZEN answer (judge-variability sample)",
    )
    args = parser.parse_args()

    load_env()
    agent_url = os.environ.get("AGENT_URL", "http://127.0.0.1:8766")

    by_id = {c.id: c for c in load_cases(_GOLD)}
    missing = [cid for cid in _FLAGGED if cid not in by_id]
    if missing:
        raise SystemExit(f"gold is missing flagged case ids: {missing}")
    cases = [by_id[cid] for cid in _FLAGGED]

    frozen = _ask_once(cases, agent_url)

    judge = make_llm_judge()
    complete = make_complete()

    _OUT_DIR.mkdir(exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    model = os.environ.get("ANTHROPIC_EXTRACTION_MODEL", "proxy default")
    out = _OUT_DIR / f"flagged-{run_id}.jsonl"
    with out.open("w") as f:
        header = {
            "type": "header",
            "run_id": run_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "agent_url": agent_url,
            "model": model,
            "judge_repeats": args.repeats,
            "note": "answers asked once and frozen; judge re-run on the frozen answer",
        }
        f.write(json.dumps(header) + "\n")
        for fr in frozen:
            f.write(json.dumps(_record(fr, judge, complete, args.repeats)) + "\n")

    print(f"wrote header + {len(frozen)} frozen-answer records to {out}")


if __name__ == "__main__":
    main()
