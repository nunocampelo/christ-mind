"""Loads hand-labelled gold mention pairs from JSONL.

A gold line is two surface forms and whether they name the same thing:

    {"left": "the ego", "right": "his ego", "same": true}

Both forms are anchored against the mention universe of a corpus run at load time --
the same forms the extractor actually produced -- so a gold pair naming a mention that
no longer appears (a re-extraction or parser change moved it) fails here instead of
silently scoring against a form the resolver never sees. This mirrors how
`load_gold_claims` anchors every gold quote against `Source.text`.

Pairs are keyed on the two forms; `same` labels both the positives (the resolver
should merge these) and the negatives (it must not). Negatives are not optional: a
pair scorer needs gold `different` pairs to have any false positives to count.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path


class GoldPairError(ValueError):
    pass


@dataclass(frozen=True)
class GoldPair:
    left: str
    right: str
    same: bool


def load_gold_pairs(path: Path, mention_universe: Sequence[str]) -> list[GoldPair]:
    known = set(mention_universe)
    pairs = []
    for line_number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            left, right, same = record["left"], record["right"], record["same"]
            if not isinstance(left, str) or not isinstance(right, str):
                raise ValueError("gold pair left/right must be strings")
            if not isinstance(same, bool):
                raise ValueError("gold pair same must be a boolean")
            if left not in known or right not in known:
                raise ValueError("gold pair names a mention not in the run's universe")
            if left == right:
                raise ValueError("gold pair names one mention twice")
            pairs.append(GoldPair(left=left, right=right, same=same))
        except (KeyError, TypeError, ValueError) as e:
            raise GoldPairError(f"invalid gold pair on line {line_number}") from e
    return pairs
