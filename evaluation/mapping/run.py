"""Scores a situation mapper against the concept gold, and records mapping runs.

    python -m evaluation.mapping.run --mapper infrastructure.llm.anthropic_proxy:make_mapper
    python -m evaluation.mapping.run --mapper <spec> --record
    python -m evaluation.mapping.run --mapper <spec> --holdout

`--mapper` names a zero-argument factory returning a `SituationMapper`. Scoring is on
the dev gold by default; `--holdout` scores the held-out split instead and is only for
reporting a final number, never while tuning the prompt. `--record` writes
`runs/<run_id>.jsonl` (a header with the aggregate score and gold hash, one line per
situation), which should be committed.
"""

import argparse
import hashlib
import importlib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from application.mapping.map_situation import SituationMapper, map_situation
from application.mapping.prompt import MAP_VERSION
from evaluation.mapping.gold import GoldSituation, load_gold_situations
from evaluation.mapping.run_format import MappingHeader, ScoreLine, SituationLine
from evaluation.mapping.score import MappingReport, score_mapping

GOLD_DIR = Path(__file__).parent / "gold"
DEV_GOLD = GOLD_DIR / "situations.jsonl"
HOLDOUT_GOLD = GOLD_DIR / "situations_holdout.jsonl"
RUNS_DIR = Path(__file__).parent / "runs"


@dataclass(frozen=True)
class RunOutcome:
    predictions: list[tuple[GoldSituation, list[str]]]
    report: MappingReport
    path: Path | None


def _load_mapper(spec: str) -> SituationMapper:
    module_name, _, factory_name = spec.partition(":")
    if not module_name or not factory_name:
        raise ValueError("mapper must be given as 'module:factory'")
    factory = getattr(importlib.import_module(module_name), factory_name)
    return factory()


def run(
    mapper: SituationMapper,
    mapper_name: str,
    gold: Sequence[GoldSituation],
    gold_path: Path,
    record: bool,
    now: datetime,
) -> RunOutcome:
    predictions = [(g, map_situation(mapper, g.situation)) for g in gold]
    report = score_mapping(predictions)
    path = _write(predictions, report, mapper_name, gold_path, now) if record else None
    return RunOutcome(predictions=predictions, report=report, path=path)


def _write(
    predictions: Sequence[tuple[GoldSituation, list[str]]],
    report: MappingReport,
    mapper_name: str,
    gold_path: Path,
    now: datetime,
) -> Path:
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    path = RUNS_DIR / f"{run_id}.jsonl"

    header = MappingHeader(
        run_id=run_id,
        created_at=now.isoformat(),
        mapper=mapper_name,
        map_version=MAP_VERSION,
        gold_sha256=hashlib.sha256(gold_path.read_bytes()).hexdigest(),
        score=ScoreLine(
            precision=report.precision,
            recall=report.recall,
            f1=report.f1,
            situations=len(report.per_situation),
        ),
    )
    with path.open("w") as file:
        file.write(header.model_dump_json() + "\n")
        for (gold, predicted), score in zip(predictions, report.per_situation):
            line = SituationLine(
                situation=gold.situation,
                predicted=predicted,
                expected=sorted(gold.concepts),
                true_positives=score.true_positives,
            )
            file.write(line.model_dump_json() + "\n")
    return path


def _summary(label: str, outcome: RunOutcome) -> str:
    r = outcome.report
    line = (
        f"{label}: set P {r.precision:.3f}  R {r.recall:.3f}  F1 {r.f1:.3f}  "
        f"({len(r.per_situation)} situations)"
    )
    if outcome.path is not None:
        line += f"\n  recorded -> {outcome.path}"
    return line


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Score a situation mapper against the concept gold."
    )
    parser.add_argument(
        "--mapper",
        required=True,
        help="module:factory returning a SituationMapper",
    )
    parser.add_argument(
        "--holdout",
        action="store_true",
        help="score the held-out split (reporting only, never while tuning)",
    )
    parser.add_argument(
        "--record",
        action="store_true",
        help="write runs/<run_id>.jsonl",
    )
    args = parser.parse_args(argv)

    gold_path = HOLDOUT_GOLD if args.holdout else DEV_GOLD
    gold = load_gold_situations(gold_path)

    try:
        mapper = _load_mapper(args.mapper)
    except ValueError as e:
        parser.error(str(e))

    outcome = run(
        mapper, args.mapper, gold, gold_path, args.record, datetime.now(UTC)
    )
    print(_summary(args.mapper, outcome))


if __name__ == "__main__":
    main()
