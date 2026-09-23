"""Surveys an unscored corpus run to pick the next gold-labelling targets.

    python -m evaluation.claims.corpus_survey evaluation/runs/<run_id>.jsonl

It labels nothing. It reports what a person should label next, so the second
gold batch is chosen by evidence rather than hand-picked:

- Sources where the model emitted a non-`course` attribution (`ego`,
  `others`, `hypothetical`), with the claim's evidence. These are where an
  ego- or other-attributed view most likely lives, so the labeller starts here.
  A zero `ego` count is itself a finding -- see the increment #5 plan.
- Recurring `other` predicates, tallied by normalised `verb_phrase` (the same
  `_normalize` the scorer uses), most frequent first with source counts. This
  is the direct input to the predicate-list review: grow the predicate list
  only for a verb that recurs across more passages than the current gold.
"""

import argparse
import json
from collections import Counter, defaultdict
from collections.abc import Sequence
from pathlib import Path

from domain.claims.models import Attribution, Claim, Predicate
from evaluation.claims.run_format import ClaimLine
from evaluation.claims.score import _normalize


def _load_claims(path: Path) -> list[ClaimLine]:
    return [
        ClaimLine.model_validate(record)
        for line in path.read_text().splitlines()
        if line.strip()
        for record in [json.loads(line)]
        if record.get("type") == "claim"
    ]


def _triple(claim: ClaimLine) -> str:
    obj = "" if claim.object is None else f" | {claim.object}"
    return f"{claim.subject} | {claim.predicate}{obj}"


def _attribution_candidates(claims: Sequence[ClaimLine]) -> list[str]:
    out: list[str] = []
    for attribution in (Attribution.EGO, Attribution.OTHERS, Attribution.HYPOTHETICAL):
        matching = [c for c in claims if c.attribution is attribution]
        sources = {c.source_id for c in matching}
        out.append(
            f"\n{attribution.value}: {len(matching)} claims across "
            f"{len(sources)} sources"
        )
        for claim in matching:
            out.append(f"  [{claim.source_id}] {_triple(claim)}  <- {claim.evidence!r}")
    return out


def _other_verbs(claims: Sequence[ClaimLine]) -> list[str]:
    sources_by_verb: dict[str, set[str]] = defaultdict(set)
    counts: Counter[str] = Counter()
    for claim in claims:
        if claim.predicate is not Predicate.OTHER:
            continue
        verb = _normalize(claim.verb_phrase) or ""
        counts[verb] += 1
        sources_by_verb[verb].add(claim.source_id)

    out = [f"\nRecurring `other` verbs ({counts.total()} claims):"]
    for verb, count in counts.most_common():
        out.append(f"  {count:4}  ({len(sources_by_verb[verb])} sources)  {verb!r}")
    return out


def survey(path: Path) -> str:
    claims = _load_claims(path)
    out = [f"{path.name}: {len(claims)} claims"]
    out += _attribution_candidates(claims)
    out += _other_verbs(claims)
    return "\n".join(out)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Survey an unscored corpus run for gold-labelling targets."
    )
    parser.add_argument("run_file", type=Path, help="evaluation/runs/<run_id>.jsonl")
    args = parser.parse_args(argv)
    print(survey(args.run_file))


if __name__ == "__main__":
    main()
