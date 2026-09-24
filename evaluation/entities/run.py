"""Scores an entity resolver against the pair gold, and records resolution runs.

    python -m evaluation.entities.run --baseline
    python -m evaluation.entities.run --resolver infrastructure.llm.anthropic_proxy:make_resolver
    python -m evaluation.entities.run --baseline --record
    python -m evaluation.entities.run --resolver <spec> --record

`--resolver` names a zero-argument factory returning a `ResolveEntities`. `--baseline`
uses the lexical-only resolver (merge a pair iff its two forms share a normalised form)
with no model, so scored numbers are produced by the same `resolve`/`score_pairs` path
and differ only in who judges the pairs.

Without `--record`, only the gold's own mentions are resolved and scored -- enough to
score the pairs cheaply and identically across N runs. `--record` resolves the whole
corpus mention universe and writes it to `runs/<run_id>.jsonl` (header hashing the
source claim run's passages, one line per entity), then still scores the gold subset
so the file records how the run that produced it did. The baseline record is free (no
model); recording an LLM resolver over ~4589 mentions is a large provider run.
"""

import argparse
import importlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from application.resolution.prompt import RESOLVER_PROMPT_VERSION
from application.resolution.resolve_entities import (
    CandidatePair,
    PairVerdict,
    ResolutionResult,
    ResolveEntities,
    resolve,
)
from evaluation.claims.score import _normalize
from evaluation.entities.gold import GoldPair, load_gold_pairs
from evaluation.entities.mentions import _load_claims, collect_mentions
from evaluation.entities.run_format import EntityLine, ResolutionHeader, ScoreLine
from evaluation.entities.score import PairReport, score_pairs

GOLD_DIR = Path(__file__).parent / "gold"
GOLD_FILES = (GOLD_DIR / "pairs_ch1_4.jsonl",)
RUNS_DIR = Path(__file__).parent / "runs"
# Entity resolution consumes claim extraction's output: this is a claims run, read
# across concepts on purpose (see the increment #6 plan).
CORPUS_RUN = Path(__file__).parent.parent / "claims" / "runs" / "20260923T221456Z.jsonl"


class LexicalBaseline:
    """The free floor: two mentions are the same iff they share a normalised form.
    No model -- this is what a normaliser alone gets, the bar an LLM resolver must
    clear to be worth its cost."""

    def judge(self, pairs: Sequence[CandidatePair]) -> Sequence[PairVerdict]:
        return [
            PairVerdict(pair=p, same=_normalize(p.left) == _normalize(p.right))
            for p in pairs
        ]


@dataclass(frozen=True)
class RunOutcome:
    result: ResolutionResult
    report: PairReport
    path: Path | None


def _load_resolver(spec: str) -> ResolveEntities:
    module_name, _, factory_name = spec.partition(":")
    if not module_name or not factory_name:
        raise ValueError("resolver must be given as 'module:factory'")
    factory = getattr(importlib.import_module(module_name), factory_name)
    return factory()


def _gold_mentions(gold: Sequence[GoldPair]) -> list[str]:
    return sorted({p.left for p in gold} | {p.right for p in gold})


def run(
    resolver: ResolveEntities,
    resolver_name: str,
    resolver_prompt_version: str | None,
    gold: Sequence[GoldPair],
    all_mentions: Sequence[str],
    record: bool,
    now: datetime,
) -> RunOutcome:
    """Resolves the whole corpus when recording, else just the gold's mentions.
    Either way the gold is scored: a recorded run's header carries the score of the
    subset it also resolved, so the file says how good the run that wrote it was.
    """
    targets = all_mentions if record else _gold_mentions(gold)
    result = resolve(targets, resolver)

    if record:
        subset = resolve(_gold_mentions(gold), resolver)
        report = score_pairs(subset.entities, gold)
        path = _write(result, report, resolver_name, resolver_prompt_version, now)
    else:
        report = score_pairs(result.entities, gold)
        path = None

    return RunOutcome(result=result, report=report, path=path)


def _write(
    result: ResolutionResult,
    report: PairReport,
    resolver_name: str,
    resolver_prompt_version: str | None,
    now: datetime,
) -> Path:
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    path = RUNS_DIR / f"{run_id}.jsonl"
    source_run_id, passages_sha256 = _source_run_provenance()

    s = report.score
    header = ResolutionHeader(
        run_id=run_id,
        created_at=now.isoformat(),
        resolver=resolver_name,
        resolver_prompt_version=resolver_prompt_version,
        source_run_id=source_run_id,
        passages_sha256=passages_sha256,
        mentions=sum(len(e.mentions) for e in result.entities),
        entities=len(result.entities),
        rejected=len(result.rejected),
        failed=result.failed,
        score=ScoreLine(
            true_positives=s.true_positives,
            false_positives=s.false_positives,
            false_negatives=s.false_negatives,
            blocking_recall=report.blocking_recall,
        ),
    )
    with path.open("w") as file:
        file.write(header.model_dump_json() + "\n")
        for entity in result.entities:
            file.write(EntityLine.from_entity(entity).model_dump_json() + "\n")
    return path


def _source_run_provenance() -> tuple[str, str]:
    for line in CORPUS_RUN.read_text().splitlines():
        record = json.loads(line)
        if record.get("type") == "header":
            return record["run_id"], record["passages_sha256"]
    raise ValueError("source corpus run has no header line")


def _summary(label: str, outcome: RunOutcome) -> str:
    s = outcome.report.score
    line = (
        f"{label}: pair P {s.precision:.3f}  R {s.recall:.3f}  "
        f"(tp {s.true_positives}, fp {s.false_positives}, fn {s.false_negatives})  "
        f"blocking recall {outcome.report.blocking_recall:.3f}"
    )
    if outcome.path is not None:
        r = outcome.result
        line += (
            f"\n  recorded {len(r.entities)} entities, {len(r.rejected)} rejected"
            f" -> {outcome.path}"
        )
    return line


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Score an entity resolver against the pair gold and baseline."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--resolver", help="module:factory returning a ResolveEntities")
    group.add_argument(
        "--baseline",
        action="store_true",
        help="use the lexical-only baseline (no model)",
    )
    parser.add_argument(
        "--record",
        action="store_true",
        help="resolve the whole corpus and write runs/<run_id>.jsonl",
    )
    args = parser.parse_args(argv)

    all_mentions = [m.text for m in collect_mentions(_load_claims(CORPUS_RUN))]
    gold = [c for f in GOLD_FILES for c in load_gold_pairs(f, all_mentions)]
    now = datetime.now(UTC)

    if args.baseline:
        outcome = run(
            LexicalBaseline(), "baseline", None, gold, all_mentions, args.record, now
        )
        print(_summary("baseline", outcome))
        return

    try:
        resolver = _load_resolver(args.resolver)
    except ValueError as e:
        parser.error(str(e))

    baseline = run(
        LexicalBaseline(), "baseline", None, gold, all_mentions, record=False, now=now
    )
    print(_summary("baseline", baseline))
    outcome = run(
        resolver, args.resolver, RESOLVER_PROMPT_VERSION, gold, all_mentions,
        args.record, now,
    )
    print(_summary(args.resolver, outcome))


if __name__ == "__main__":
    main()
