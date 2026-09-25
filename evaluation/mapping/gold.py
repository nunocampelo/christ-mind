"""Loads hand-labelled situation -> concept gold from JSONL.

A gold line is a free-text situation and the concept mentions a good mapper should
surface for it:

    {"situation": "I keep getting angry when criticized", "concepts": ["anger", ...]}

The concepts are **retrieval concepts**, not a literal-semantics annotation of the
sentence: they name the claim space the mapper should open for this situation, which
legitimately includes concepts the person never said. "I lied and feel awful" gets
`forgiveness` because that is the claim space to retrieve, not because "forgiveness"
appears in the text. The whole pipeline maps situation -> retrieval concepts ->
relevant claims, so the gold labels the middle of that, not the surface words.

The concepts are surface forms in the same shape `map_situation` returns, scored as a
set (see `score.py`), so unlike the claims/entities gold there is no corpus anchoring:
a concept the corpus doesn't contain is still a legitimate expectation, and its absence
downstream is a retrieval signal, not a labelling error. Malformed records fail loudly
at load time, mirroring `evaluation/entities/gold.py`.
"""

import json
from dataclasses import dataclass
from pathlib import Path


class GoldSituationError(ValueError):
    pass


@dataclass(frozen=True)
class GoldSituation:
    situation: str
    concepts: frozenset[str]


def load_gold_situations(path: Path) -> list[GoldSituation]:
    situations = []
    for line_number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            situation, concepts = record["situation"], record["concepts"]
            if not isinstance(situation, str) or not situation.strip():
                raise ValueError("gold situation must be a non-empty string")
            if not isinstance(concepts, list) or not concepts:
                raise ValueError("gold concepts must be a non-empty list")
            if not all(isinstance(c, str) and c.strip() for c in concepts):
                raise ValueError("every gold concept must be a non-empty string")
            situations.append(
                GoldSituation(
                    situation=situation,
                    concepts=frozenset(c.strip() for c in concepts),
                )
            )
        except (KeyError, TypeError, ValueError) as e:
            raise GoldSituationError(
                f"invalid gold situation on line {line_number}"
            ) from e
    return situations
