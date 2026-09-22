"""Runs a claim extractor over a gold set, scores it, and records the run.

    python -m evaluation.claims.run --extractor my_pkg.my_module:make_extractor

`--extractor` names a zero-argument factory that returns a `ClaimExtractor`
(usually `PromptedClaimExtractor(complete)` around a provider's `Complete`).
Each run is written to `evaluation/runs/<run_id>.jsonl`, and those files are
meant to be committed. The header line hashes the passages and the gold files,
so two runs can be checked for comparability before their scores are compared.
"""

import argparse
import hashlib
import importlib
import json
from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from application.extraction.extract_claims import (
    ClaimExtractor,
    ExtractionResult,
    extract_claims,
)
from application.extraction.prompt import PROMPT_VERSION, PromptedClaimExtractor
from domain.sources.models import Source
from evaluation.claims.gold import load_gold_claims
from evaluation.claims.score import ClaimScore, ScoreReport, score_claims
from infrastructure.database.sources_acim import list_acim_sources

GOLD_DIR = Path(__file__).parent / "gold"
RUNS_DIR = Path(__file__).parent.parent / "runs"


class Split(StrEnum):
    DEV = "dev"
    HOLDOUT = "holdout"


GOLD_FILES = {
    Split.DEV: (GOLD_DIR / "t1_1.jsonl", GOLD_DIR / "t3_2.jsonl"),
    Split.HOLDOUT: (GOLD_DIR / "t1_1_holdout.jsonl",),
}


@dataclass(frozen=True)
class RunHeader:
    run_id: str
    created_at: str
    extractor: str
    prompt_version: str | None
    split: Split
    passages_sha256: str
    gold_sha256: str
    score: ScoreReport
    rejected: int
    failed_sources: int


@dataclass(frozen=True)
class RunOutcome:
    run_id: str
    path: Path
    result: ExtractionResult
    report: ScoreReport


def run(
    extractor: ClaimExtractor,
    extractor_name: str,
    split: Split,
    sources: Sequence[Source],
    runs_dir: Path,
    now: datetime,
) -> RunOutcome:
    gold_files = GOLD_FILES[split]
    gold = [claim for path in gold_files for claim in load_gold_claims(path, sources)]
    gold_source_ids = {claim.source_id for claim in gold}
    targets = [source for source in sources if source.id in gold_source_ids]

    result = extract_claims(targets, extractor)
    report = score_claims(result.claims, gold)

    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    header = RunHeader(
        run_id=run_id,
        created_at=now.isoformat(),
        extractor=extractor_name,
        prompt_version=(
            PROMPT_VERSION if isinstance(extractor, PromptedClaimExtractor) else None
        ),
        split=split,
        passages_sha256=_hash_passages(targets),
        gold_sha256=_hash_files(gold_files),
        score=report,
        rejected=len(result.rejected),
        failed_sources=len(result.failed_source_ids),
    )
    texts = {source.id: source.text for source in targets}
    lines = [{"type": "header", **asdict(header)}]
    lines += [
        {
            "type": "claim",
            **asdict(claim),
            "evidence": texts[claim.source_id][
                claim.evidence_start : claim.evidence_end
            ],
        }
        for claim in result.claims
    ]
    lines += [
        {"type": "rejected", **asdict(rejection)} for rejection in result.rejected
    ]
    lines += [
        {"type": "failed", "source_id": source_id}
        for source_id in result.failed_source_ids
    ]

    runs_dir.mkdir(parents=True, exist_ok=True)
    path = runs_dir / f"{run_id}.jsonl"
    path.write_text(
        "".join(json.dumps(line, ensure_ascii=False) + "\n" for line in lines)
    )
    return RunOutcome(run_id=run_id, path=path, result=result, report=report)


def _hash_passages(sources: Sequence[Source]) -> str:
    digest = hashlib.sha256()
    for source in sources:
        digest.update(f"{source.id}\0{source.text}\0".encode())
    return digest.hexdigest()


def _hash_files(paths: Sequence[Path]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _load_extractor(spec: str) -> ClaimExtractor:
    module_name, _, factory_name = spec.partition(":")
    if not module_name or not factory_name:
        raise ValueError("extractor must be given as 'module:factory'")
    factory = getattr(importlib.import_module(module_name), factory_name)
    return factory()


def _summary(outcome: RunOutcome) -> str:
    report = outcome.report
    result = outcome.result
    rows = [
        f"run {outcome.run_id} -> {outcome.path}",
        _score_line("loose", report.loose),
        _score_line("strict", report.strict),
        f"  mismatches on loose matches: polarity {report.polarity_mismatches}, "
        f"mode {report.mode_mismatches}, "
        f"attribution {report.attribution_mismatches}",
        f"  rejected candidates: {len(result.rejected)}"
        + "".join(
            f", {reason} {count}"
            for reason, count in sorted(
                Counter(rejection.reason for rejection in result.rejected).items()
            )
        ),
        f"  failed sources: {len(result.failed_source_ids)}",
    ]
    return "\n".join(rows)


def _score_line(label: str, score: ClaimScore) -> str:
    return (
        f"  {label:6} P {score.precision:.3f}  R {score.recall:.3f}  "
        f"(tp {score.true_positives}, fp {score.false_positives}, "
        f"fn {score.false_negatives})"
    )


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Run a claim extractor over a gold set and score it."
    )
    parser.add_argument("--extractor", required=True, help="module:factory")
    parser.add_argument(
        "--holdout",
        action="store_true",
        help="score against the held-out set; don't use while tuning",
    )
    args = parser.parse_args(argv)

    try:
        extractor = _load_extractor(args.extractor)
    except ValueError as e:
        parser.error(str(e))

    outcome = run(
        extractor=extractor,
        extractor_name=args.extractor,
        split=Split.HOLDOUT if args.holdout else Split.DEV,
        sources=list_acim_sources(),
        runs_dir=RUNS_DIR,
        now=datetime.now(UTC),
    )
    print(_summary(outcome))


if __name__ == "__main__":
    main()
