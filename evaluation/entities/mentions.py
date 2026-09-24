"""Sizes the entity-resolution problem from an unscored corpus run.

    python -m evaluation.entities.mentions evaluation/runs/<run_id>.jsonl

It resolves nothing. It reports the mention universe (every distinct subject/object
surface form the extractor produced) and the free floor a normaliser already gets,
so the increment #6 pair gold set is sized by evidence rather than guessed:

- The mention universe: distinct surface forms and total occurrences. This is the
  set entity resolution partitions.
- Lexical blocking: mentions grouped by their `_normalize` value (the same
  normaliser the claim scorer and `corpus_survey` use, so "the ego" and "ego" block
  together for free). The block-size distribution is the floor -- merges a normaliser
  already gets before any model is asked to judge a pair. Multi-member blocks are the
  near-duplicate clusters a labeller should sample; the surviving singletons are the
  work an LLM pass would have to justify.

Subject and object mentions share one universe: a surface form is the same entity
whether it appears as a subject or an object, and attribution is a property of the
claim, not the mention (see the increment #6 plan's open questions).
"""

import argparse
import json
from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from evaluation.claims.run_format import ClaimLine
from evaluation.claims.score import _normalize


@dataclass(frozen=True)
class Mention:
    """A distinct surface form and where it was observed. Keyed by the raw text, not
    the normalised form -- normalisation is the blocking step, reported separately."""

    text: str
    occurrences: int
    source_ids: frozenset[str]


def _load_claims(path: Path) -> list[ClaimLine]:
    return [
        ClaimLine.model_validate(record)
        for line in path.read_text().splitlines()
        if line.strip()
        for record in [json.loads(line)]
        if record.get("type") == "claim"
    ]


def collect_mentions(claims: Sequence[ClaimLine]) -> list[Mention]:
    counts: Counter[str] = Counter()
    sources: dict[str, set[str]] = defaultdict(set)
    for claim in claims:
        for surface in (claim.subject, claim.object):
            if surface is None:
                continue
            counts[surface] += 1
            sources[surface].add(claim.source_id)
    return [
        Mention(text=text, occurrences=count, source_ids=frozenset(sources[text]))
        for text, count in counts.most_common()
    ]


def block_by_normalization(mentions: Sequence[Mention]) -> dict[str, list[Mention]]:
    """Groups mentions whose normalised text is equal. The key is the normalised form
    (never None: a mention with only punctuation would normalise to "", which still
    groups sensibly)."""
    blocks: dict[str, list[Mention]] = defaultdict(list)
    for mention in mentions:
        blocks[_normalize(mention.text) or ""].append(mention)
    return dict(blocks)


def survey(path: Path) -> str:
    claims = _load_claims(path)
    mentions = collect_mentions(claims)
    total_occurrences = sum(m.occurrences for m in mentions)
    blocks = block_by_normalization(mentions)

    multi = {key: members for key, members in blocks.items() if len(members) > 1}
    singletons = len(blocks) - len(multi)
    collapsed = sum(len(members) for members in multi.values())

    out = [
        f"{path.name}: {len(claims)} claims",
        f"mention universe: {len(mentions)} distinct surface forms, "
        f"{total_occurrences} occurrences",
        "",
        f"lexical blocking (normalised): {len(blocks)} blocks",
        f"  {singletons} singleton blocks (no normalisation merge)",
        f"  {len(multi)} multi-member blocks collapsing {collapsed} surface forms",
        "",
        "multi-member blocks (the free floor; most members first):",
    ]
    for key, members in sorted(
        multi.items(), key=lambda kv: len(kv[1]), reverse=True
    ):
        forms = ", ".join(f"{m.text!r}×{m.occurrences}" for m in members)
        out.append(f"  [{len(members)}] {key!r}: {forms}")
    return "\n".join(out)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Size the mention universe and lexical-blocking floor of a run."
    )
    parser.add_argument("run_file", type=Path, help="evaluation/runs/<run_id>.jsonl")
    args = parser.parse_args(argv)
    print(survey(args.run_file))


if __name__ == "__main__":
    main()
