"""Draft calibration fixtures from real answers, for human approval.

Asks each named case once over the live stack, freezes the answer + its full evidence, and
writes a `*.draft.jsonl` fixtures file whose per-criterion verdicts are a FIRST PASS the judge
proposed -- `approved_by` is left empty on purpose. A human then reviews each fixture against
its cited paragraphs, corrects every verdict and writes an evidence-based reason, derives the
negative/positive controls by minimal edits (see calibration/README), sets `approved_by`, and
assigns the `tune`/`holdout` split. The draft is a labour-saver, never the ground truth.

Run from the repo root with the live-stack prerequisites (DATABASE_URL, Docker, cproxy):
    .venv/bin/python -m evaluation.blackbox.calibration.draft --cases id1,id2,... --out <path>
"""

import argparse
import os
from datetime import datetime, timezone
from pathlib import Path

from infrastructure.config.env import load_env

from evaluation.blackbox.calibration.fixtures import (
    CriterionVerdict,
    Fixture,
    FrozenCase,
    dump_fixtures,
)
from evaluation.blackbox.calibration.judging import Frozen, ask_once
from evaluation.blackbox.gold import load_cases
from evaluation.blackbox.llm_judge import (
    PROMPT_VERSION,
    LLMEvaluator,
    make_llm_judge,
    prompt_hash,
)
from evaluation.blackbox.run import _resolve_model

_GOLD = Path(__file__).resolve().parents[1] / "gold" / "cases.jsonl"


def _draft_verdicts(judge: LLMEvaluator, frozen: Frozen) -> dict[str, CriterionVerdict]:
    verdicts: dict[str, CriterionVerdict] = {}
    for result in judge.evaluate(frozen.case, frozen.response):
        if result.status == "not_evaluated":
            verdict = "not_applicable"
            reason = f"judge draft: {result.detail or 'not evaluated'}"
        else:
            verdict = result.status
            reason = f"judge draft score {result.score}"
        verdicts[result.name] = CriterionVerdict(verdict=verdict, reason=reason)
    return verdicts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cases", required=True, help="comma-separated gold case ids to freeze (8-10)"
    )
    parser.add_argument("--out", required=True, type=Path, help="draft fixtures JSONL")
    args = parser.parse_args()

    load_env()
    agent_url = os.environ.get("AGENT_URL", "http://127.0.0.1:8766")

    wanted = [c.strip() for c in args.cases.split(",") if c.strip()]
    by_id = {c.id: c for c in load_cases(_GOLD)}
    missing = [cid for cid in wanted if cid not in by_id]
    if missing:
        raise SystemExit(f"gold is missing case ids: {missing}")
    cases = [by_id[cid] for cid in wanted]

    frozen = ask_once(cases, agent_url)
    judge = make_llm_judge()

    fixtures = [
        Fixture(
            id=f"real-{fr.case.id}",
            role="real",
            split="tune",
            case=FrozenCase.of(fr.case),
            response=fr.response,
            verdicts=_draft_verdicts(judge, fr),
            drafted_by="llm_judge (unapproved)",
            approved_by="",
        )
        for fr in frozen
    ]
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    header: dict[str, object] = {
        "drafted_at": datetime.now(timezone.utc).isoformat(),
        "draft_run_id": run_id,
        "draft_source": "live agent answers, verdicts proposed by llm_judge (UNAPPROVED)",
        "draft_judge_model": _resolve_model(),
        "draft_judge_prompt_version": PROMPT_VERSION,
        "draft_judge_prompt_hash": prompt_hash(),
        "agent_url": agent_url,
        "gold_file": _GOLD.name,
        "case_ids": wanted,
    }
    dump_fixtures(fixtures, args.out, header=header)
    print(
        f"wrote {len(fixtures)} DRAFT fixtures to {args.out} (run {run_id}).\n"
        "Review each verdict against its cited paragraphs, write reasons, derive controls, "
        "set approved_by, and assign tune/holdout before calibrating."
    )


if __name__ == "__main__":
    main()
