"""Scores an entity resolver against the pair gold, next to the lexical baseline.

    python -m evaluation.entities.run --resolver infrastructure.llm.anthropic_proxy:make_resolver
    python -m evaluation.entities.run --baseline

`--resolver` names a zero-argument factory returning a `ResolveEntities`. `--baseline`
runs the lexical-only resolver (merge a pair iff its two forms share a normalised form)
with no model, so the two numbers are produced by the same `resolve`/`score_pairs` path
and differ only in who judges the pairs.

The scored run resolves the gold's own mentions -- enough to score the 22 gold pairs
cheaply and identically across N runs. The large full-corpus resolution is written only
once a resolver has beaten the baseline (a separate step), not here.
"""

import argparse
import importlib
from collections.abc import Sequence
from pathlib import Path

from application.resolution.resolve_entities import (
    CandidatePair,
    PairVerdict,
    ResolveEntities,
    resolve,
)
from evaluation.claims.score import _normalize
from evaluation.entities.gold import GoldPair, load_gold_pairs
from evaluation.entities.mentions import _load_claims, collect_mentions
from evaluation.entities.score import PairReport, score_pairs

GOLD_DIR = Path(__file__).parent / "gold"
GOLD_FILES = (GOLD_DIR / "pairs_ch1_4.jsonl",)
CORPUS_RUN = Path(__file__).parent.parent / "runs" / "20260923T221456Z.jsonl"


class LexicalBaseline:
    """The free floor: two mentions are the same iff they share a normalised form.
    No model -- this is what a normaliser alone gets, the bar an LLM resolver must
    clear to be worth its cost."""

    def judge(self, pairs: Sequence[CandidatePair]) -> Sequence[PairVerdict]:
        return [
            PairVerdict(pair=p, same=_normalize(p.left) == _normalize(p.right))
            for p in pairs
        ]


def _load_resolver(spec: str) -> ResolveEntities:
    module_name, _, factory_name = spec.partition(":")
    if not module_name or not factory_name:
        raise ValueError("resolver must be given as 'module:factory'")
    factory = getattr(importlib.import_module(module_name), factory_name)
    return factory()


def _gold_mentions(gold: Sequence[GoldPair]) -> list[str]:
    return sorted({p.left for p in gold} | {p.right for p in gold})


def score(resolver: ResolveEntities, gold: Sequence[GoldPair]) -> PairReport:
    result = resolve(_gold_mentions(gold), resolver)
    return score_pairs(result.entities, gold)


def _summary(label: str, report: PairReport) -> str:
    s = report.score
    return (
        f"{label}: pair P {s.precision:.3f}  R {s.recall:.3f}  "
        f"(tp {s.true_positives}, fp {s.false_positives}, fn {s.false_negatives})  "
        f"blocking recall {report.blocking_recall:.3f}"
    )


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Score an entity resolver against the pair gold and baseline."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--resolver", help="module:factory returning a ResolveEntities")
    group.add_argument(
        "--baseline",
        action="store_true",
        help="score the lexical-only baseline (no model)",
    )
    args = parser.parse_args(argv)

    mentions = [m.text for m in collect_mentions(_load_claims(CORPUS_RUN))]
    gold = [c for f in GOLD_FILES for c in load_gold_pairs(f, mentions)]

    if args.baseline:
        print(_summary("baseline", score(LexicalBaseline(), gold)))
        return

    try:
        resolver = _load_resolver(args.resolver)
    except ValueError as e:
        parser.error(str(e))
    print(_summary("baseline", score(LexicalBaseline(), gold)))
    print(_summary(args.resolver, score(resolver, gold)))


if __name__ == "__main__":
    main()
