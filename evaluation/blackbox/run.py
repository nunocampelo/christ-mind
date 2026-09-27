"""Runs the black-box suite: for each gold case, ask the real agent, evaluate the response
with the configured evaluators, and record a run. A run needs the live stack (the agent
generates answers via the LLM proxy), so there is no offline full run -- `--live` brings the
stack up (see harness.py). Without it, the CLI errors clearly rather than pretending.

    python -m evaluation.blackbox.run --live
    python -m evaluation.blackbox.run --live --holdout --record
    python -m evaluation.blackbox.run --live --evaluators \
        evaluation.blackbox.deterministic:make_deterministic,evaluation.blackbox.llm_judge:make_llm_judge
"""

import argparse
import hashlib
import importlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from evaluation.blackbox.client import A2AAgentClient
from evaluation.blackbox.evaluator import Evaluator, combine
from evaluation.blackbox.gold import BlackBoxCase, load_cases
from evaluation.blackbox.harness import live_stack
from evaluation.blackbox.run_format import BlackBoxHeader, CaseLine, ScoreLine
from evaluation.blackbox.score import BlackBoxReport, score_cases

GOLD_DIR = Path(__file__).parent / "gold"
DEV_GOLD = GOLD_DIR / "cases.jsonl"
HOLDOUT_GOLD = GOLD_DIR / "cases_holdout.jsonl"
RUNS_DIR = Path(__file__).parent / "runs"
CORPUS = (
    Path(__file__).resolve().parents[2]
    / "src/infrastructure/database/data/claims/corpus.jsonl"
)
_DEFAULT_EVALUATORS = "evaluation.blackbox.deterministic:make_deterministic"


@dataclass(frozen=True)
class RunOutcome:
    report: BlackBoxReport
    intents: list[str]
    path: Path | None


def _load_evaluator(spec: str) -> Evaluator:
    module_name, _, factory_name = spec.partition(":")
    if not module_name or not factory_name:
        raise ValueError("evaluator must be given as 'module:factory'")
    return getattr(importlib.import_module(module_name), factory_name)()


def run(
    client: A2AAgentClient,
    evaluators: Sequence[Evaluator],
    evaluator_names: Sequence[str],
    cases: Sequence[BlackBoxCase],
    gold_path: Path,
    agent_url: str,
    record: bool,
    now: datetime,
) -> RunOutcome:
    results = []
    for case in cases:
        response = client.ask(case.question)
        criteria = [c for ev in evaluators for c in ev.evaluate(case, response)]
        results.append(combine(case.id, criteria))
    report = score_cases(results)
    intents = [c.intent for c in cases]
    path = (
        _write(report, cases, evaluator_names, gold_path, agent_url, now)
        if record
        else None
    )
    return RunOutcome(report=report, intents=intents, path=path)


def _write(
    report: BlackBoxReport,
    cases: Sequence[BlackBoxCase],
    evaluator_names: Sequence[str],
    gold_path: Path,
    agent_url: str,
    now: datetime,
) -> Path:
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    path = RUNS_DIR / f"{run_id}.jsonl"
    header = BlackBoxHeader(
        run_id=run_id,
        created_at=now.isoformat(),
        agent_url=agent_url,
        evaluators=list(evaluator_names),
        corpus_run_id=_corpus_run_id(),
        gold_sha256=hashlib.sha256(gold_path.read_bytes()).hexdigest(),
        score=ScoreLine(
            passed=report.passed,
            total=report.total,
            gating_pass_rate=report.pass_rate,
        ),
    )
    with path.open("w") as file:
        file.write(header.model_dump_json() + "\n")
        for case, case_result in zip(cases, report.per_case):
            line = CaseLine(
                case_id=case.id,
                intent=case.intent,
                status=case_result.status,
                criteria=case_result.criteria,
            )
            file.write(line.model_dump_json() + "\n")
    return path


def _corpus_run_id() -> str:
    for raw in CORPUS.read_text().splitlines():
        if raw.strip():
            record = json.loads(raw)
            if record.get("type") == "header":
                return str(record.get("run_id", "unknown"))
    return "unknown"


def _summary(outcome: RunOutcome) -> str:
    r = outcome.report
    by_intent = r.pass_rate_by_intent(outcome.intents)
    lines = [f"gating: {r.passed}/{r.total} passed ({r.pass_rate:.3f})"]
    for intent in sorted(by_intent):
        passed, total = by_intent[intent]
        lines.append(f"  {intent:20} {passed}/{total}")
    for name, mean in sorted(outcome.report.advisory_means().items()):
        lines.append(f"  advisory {name:26} mean {mean:.3f}")
    if outcome.path is not None:
        lines.append(f"recorded -> {outcome.path}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Run the black-box eval suite against the real agent."
    )
    parser.add_argument("--live", action="store_true", help="bring up the real stack")
    parser.add_argument("--holdout", action="store_true", help="score the held-out split")
    parser.add_argument("--record", action="store_true", help="write runs/<run_id>.jsonl")
    parser.add_argument(
        "--evaluators",
        default=_DEFAULT_EVALUATORS,
        help="comma-separated module:factory evaluators",
    )
    parser.add_argument(
        "--agent-url",
        default="http://127.0.0.1:8000",
        help="base URL of the A2A server to spawn/hit",
    )
    args = parser.parse_args(argv)

    if not args.live:
        parser.error(
            "the black-box suite needs the live stack to generate answers; pass --live "
            "(there is no offline full run -- unit tests cover the pieces offline)"
        )

    gold_path = HOLDOUT_GOLD if args.holdout else DEV_GOLD
    cases = load_cases(gold_path)
    evaluator_names = [s.strip() for s in args.evaluators.split(",") if s.strip()]
    try:
        evaluators = [_load_evaluator(s) for s in evaluator_names]
    except ValueError as e:
        parser.error(str(e))

    with live_stack(agent_url=args.agent_url) as agent_url:
        client = A2AAgentClient(agent_url)
        outcome = run(
            client,
            evaluators,
            evaluator_names,
            cases,
            gold_path,
            agent_url,
            args.record,
            datetime.now(UTC),
        )
    print(_summary(outcome))


if __name__ == "__main__":
    main()
