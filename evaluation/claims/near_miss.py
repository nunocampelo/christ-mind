"""Explains a run's misses, so steps that fix them can be checked each run.

    python -m evaluation.claims.near_miss evaluation/claims/runs/<run_id>.jsonl

"Matched" means the same here as in the scorer: a gold claim is a near miss
when `relaxed_pairing` found no relaxed partner for it. For each such gold
claim this prints the prediction from the same source whose evidence overlaps
it most and which fields differ, then tallies the differing fields across all
near misses. Finally it lists predictions that overlap no gold evidence at all
-- either extra claims or gaps in the gold set, which needs a person to judge.
"""

import argparse
import json
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from domain.claims.models import Claim, Polarity
from domain.sources.models import Source
from evaluation.claims.gold import load_gold_claims
from evaluation.claims.run import GOLD_FILES, Split
from evaluation.claims.run_format import ClaimLine
from evaluation.claims.score import relaxed_pairing
from infrastructure.database.sources_acim import list_acim_sources

_FIELDS = ("subject", "predicate", "object", "polarity", "mode", "attribution")


def _load_run(path: Path) -> tuple[Split, list[Claim]]:
    records = [
        json.loads(line) for line in path.read_text().splitlines() if line.strip()
    ]
    header = next(record for record in records if record.get("type") == "header")
    predicted = [
        ClaimLine.model_validate(record).to_claim()
        for record in records
        if record.get("type") == "claim"
    ]
    return Split(header["split"]), predicted


def _overlap(a: Claim, b: Claim) -> int:
    return max(
        0, min(a.evidence_end, b.evidence_end) - max(a.evidence_start, b.evidence_start)
    )


def _overlaps_any(claim: Claim, others: Sequence[Claim]) -> bool:
    return any(
        c.source_id == claim.source_id and _overlap(c, claim) > 0 for c in others
    )


def _differing_fields(predicted: Claim, gold: Claim) -> list[str]:
    return [f for f in _FIELDS if getattr(predicted, f) != getattr(gold, f)]


def _nearest_prediction(gold: Claim, predicted: Sequence[Claim]) -> Claim | None:
    overlapping = [
        (c, _overlap(c, gold))
        for c in predicted
        if c.source_id == gold.source_id and _overlap(c, gold) > 0
    ]
    if not overlapping:
        return None
    return max(overlapping, key=lambda pair: pair[1])[0]


def _triple(claim: Claim) -> str:
    obj = "" if claim.object is None else f" | {claim.object}"
    marker = "" if claim.polarity is Polarity.AFFIRMED else " [negated]"
    return f"{claim.subject} | {claim.predicate}{obj}{marker}"


def report(run_path: Path, sources: Sequence[Source] | None = None) -> str:
    resolved_sources = list_acim_sources() if sources is None else sources
    split, predicted = _load_run(run_path)
    gold = [
        claim
        for path in GOLD_FILES[split]
        for claim in load_gold_claims(path, resolved_sources)
    ]

    pairing = relaxed_pairing(predicted, gold)
    field_tally: Counter[str] = Counter()

    out = [f"{run_path.name}: {len(pairing.unmatched_gold)} near-miss gold claims"]
    for gold_claim in pairing.unmatched_gold:
        out.append(f"\n[{gold_claim.source_id}] gold: {_triple(gold_claim)}")
        nearest = _nearest_prediction(gold_claim, predicted)
        if nearest is None:
            out.append("  no overlapping prediction")
            continue
        out.append(f"  near: {_triple(nearest)}")
        differ = _differing_fields(nearest, gold_claim)
        field_tally.update(differ)
        out.append(
            f"  differs on: {', '.join(differ) if differ else '(evidence only)'}"
        )

    out.append("\nDiffering-field tally across near misses:")
    for field, count in field_tally.most_common():
        out.append(f"  {field}: {count}")

    no_gold = [c for c in pairing.unmatched_predicted if not _overlaps_any(c, gold)]
    out.append(f"\nPredictions overlapping no gold evidence ({len(no_gold)}):")
    for claim in no_gold:
        out.append(f"  [{claim.source_id}] {_triple(claim)}")

    return "\n".join(out)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Explain a run's near misses.")
    parser.add_argument(
        "run_file", type=Path, help="evaluation/claims/runs/<run_id>.jsonl"
    )
    args = parser.parse_args(argv)
    print(report(args.run_file))


if __name__ == "__main__":
    main()
