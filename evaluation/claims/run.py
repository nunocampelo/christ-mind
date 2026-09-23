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
import sys
from collections import Counter
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from application.extraction.extract_claims import (
    ClaimExtractor,
    ExtractionResult,
    SourceExtraction,
    collect_extraction,
    extract_claims,
    extract_source,
)
from application.extraction.prompt import PROMPT_VERSION, PromptedClaimExtractor
from domain.sources.models import Source
from evaluation.claims.gold import load_gold_claims
from evaluation.claims.run_format import ClaimLine
from evaluation.claims.score import ClaimScore, ScoreReport, score_claims
from infrastructure.database.sources_acim import list_acim_sources

GOLD_DIR = Path(__file__).parent / "gold"
RUNS_DIR = Path(__file__).parent.parent / "runs"


class Split(StrEnum):
    DEV = "dev"
    HOLDOUT = "holdout"
    CORPUS = "corpus"


GOLD_FILES = {
    Split.DEV: (
        GOLD_DIR / "t1_1.jsonl",
        GOLD_DIR / "t3_2.jsonl",
        GOLD_DIR / "t4_ego.jsonl",
    ),
    Split.HOLDOUT: (GOLD_DIR / "t1_1_holdout.jsonl",),
    Split.CORPUS: (),
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
    score: ScoreReport | None
    rejected: int
    failed_sources: int


@dataclass(frozen=True)
class RunOutcome:
    run_id: str
    path: Path
    result: ExtractionResult
    report: ScoreReport | None


def run(
    extractor: ClaimExtractor,
    extractor_name: str,
    split: Split,
    sources: Sequence[Source],
    runs_dir: Path,
    now: datetime,
    workers: int = 1,
) -> RunOutcome:
    gold_files = GOLD_FILES[split]
    gold = [claim for path in gold_files for claim in load_gold_claims(path, sources)]
    if split is Split.CORPUS:
        targets = list(sources)
    else:
        gold_source_ids = {claim.source_id for claim in gold}
        targets = [source for source in sources if source.id in gold_source_ids]

    texts = {source.id: source.text for source in targets}
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    runs_dir.mkdir(parents=True, exist_ok=True)
    path = runs_dir / f"{run_id}.jsonl"

    total = len(targets)
    completed = 0

    with path.open("w") as file:

        def write_source(outcome: SourceExtraction) -> None:
            nonlocal completed
            for line in _source_lines(outcome, texts):
                file.write(json.dumps(line, ensure_ascii=False) + "\n")
            file.flush()
            completed += 1
            status = "FAILED" if outcome.failed else f"{len(outcome.claims)} claims"
            print(
                f"[{completed}/{total}] {outcome.source_id}: {status}",
                file=sys.stderr,
                flush=True,
            )

        if workers > 1:
            result = _extract_concurrent(targets, extractor, workers, write_source)
        else:
            result = extract_claims(
                targets, extractor, on_source_complete=write_source
            )
        report = (
            score_claims(result.claims, gold) if split is not Split.CORPUS else None
        )
        header = RunHeader(
            run_id=run_id,
            created_at=now.isoformat(),
            extractor=extractor_name,
            prompt_version=(
                PROMPT_VERSION
                if isinstance(extractor, PromptedClaimExtractor)
                else None
            ),
            split=split,
            passages_sha256=_hash_passages(targets),
            gold_sha256=_hash_files(gold_files) if gold_files else "",
            score=report,
            rejected=len(result.rejected),
            failed_sources=len(result.failed_source_ids),
        )
        file.write(
            json.dumps({"type": "header", **asdict(header)}, ensure_ascii=False) + "\n"
        )

    return RunOutcome(run_id=run_id, path=path, result=result, report=report)


def _extract_concurrent(
    targets: Sequence[Source],
    extractor: ClaimExtractor,
    workers: int,
    on_source_complete: Callable[[SourceExtraction], None],
) -> ExtractionResult:
    """Runs `extract_source` across a thread pool (the provider call is I/O-bound,
    so threads give real concurrency). Outcomes complete out of order; the caller's
    `on_source_complete` runs here in the main thread as each finishes, so it stays
    the sole writer and needs no lock. An unexpected error in any worker surfaces
    from `future.result()` and stops the run, matching the serial path.
    """
    outcomes: list[SourceExtraction] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(extract_source, source, extractor): source
            for source in targets
        }
        for future in as_completed(futures):
            outcome = future.result()
            outcomes.append(outcome)
            on_source_complete(outcome)
    return collect_extraction(outcomes)


def _source_lines(
    outcome: SourceExtraction, texts: dict[str, str]
) -> list[dict[str, object]]:
    if outcome.failed:
        return [{"type": "failed", "source_id": outcome.source_id}]
    lines: list[dict[str, object]] = [
        ClaimLine.from_claim(
            claim, texts[claim.source_id][claim.evidence_start : claim.evidence_end]
        ).model_dump()
        for claim in outcome.claims
    ]
    lines += [
        {"type": "rejected", **asdict(rejection)} for rejection in outcome.rejected
    ]
    return lines


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
    rows = [f"run {outcome.run_id} -> {outcome.path}"]
    if report is None:
        rows.append(f"  unscored corpus run: {len(result.claims)} claims")
    else:
        rows += [
            _score_line("loose", report.loose),
            _score_line("strict", report.strict),
            _score_line("relaxed", report.relaxed),
            f"  mismatches on loose matches: polarity {report.polarity_mismatches}, "
            f"mode {report.mode_mismatches}, "
            f"attribution {report.attribution_mismatches}",
        ]
    rows += [
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
    split_group = parser.add_mutually_exclusive_group()
    split_group.add_argument(
        "--holdout",
        action="store_true",
        help="score against the held-out set; don't use while tuning",
    )
    split_group.add_argument(
        "--all",
        action="store_true",
        help="extract over the whole corpus, unscored; writes versioned JSONL",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="concurrent extraction requests (default 8; 1 runs serially)",
    )
    args = parser.parse_args(argv)
    if args.workers < 1:
        parser.error("--workers must be at least 1")

    try:
        extractor = _load_extractor(args.extractor)
    except ValueError as e:
        parser.error(str(e))

    if args.all:
        split = Split.CORPUS
    elif args.holdout:
        split = Split.HOLDOUT
    else:
        split = Split.DEV

    outcome = run(
        extractor=extractor,
        extractor_name=args.extractor,
        split=split,
        sources=list_acim_sources(),
        runs_dir=RUNS_DIR,
        now=datetime.now(UTC),
        workers=args.workers,
    )
    print(_summary(outcome))


if __name__ == "__main__":
    main()
