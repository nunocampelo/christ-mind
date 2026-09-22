"""Loads hand-labelled gold claims from JSONL.

Gold files name their evidence by exact text rather than by offsets, which are
impractical to write by hand. Offsets are resolved against the parsed
`Source.text` at load time, so a parser or corpus change that moves or alters
the text fails here instead of silently re-pointing labels.
"""

import json
from collections.abc import Sequence
from pathlib import Path

from domain.claims.models import Attribution, Claim, Mode, Polarity, Predicate
from domain.sources.models import Source


class GoldLabelError(ValueError):
    pass


def load_gold_claims(path: Path, sources: Sequence[Source]) -> list[Claim]:
    texts = {source.id: source.text for source in sources}
    claims = []
    for line_number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            claims.append(_to_claim(record, texts))
        except (KeyError, ValueError) as e:
            raise GoldLabelError(f"invalid gold claim on line {line_number}") from e
    return claims


def _to_claim(record: dict[str, str | None], texts: dict[str, str]) -> Claim:
    source_id = _require(record, "source_id")
    evidence = _require(record, "evidence")
    text = texts.get(source_id)
    if text is None:
        raise ValueError("gold claim names an unknown source_id")
    start = text.find(evidence)
    if start == -1:
        raise ValueError("gold evidence is not a substring of its source text")
    if text.find(evidence, start + 1) != -1:
        raise ValueError("gold evidence occurs more than once in its source text")

    return Claim(
        source_id=source_id,
        subject=_require(record, "subject"),
        predicate=Predicate(_require(record, "predicate")),
        object=record.get("object"),
        verb_phrase=_require(record, "verb_phrase"),
        polarity=Polarity(_require(record, "polarity")),
        mode=Mode(_require(record, "mode")),
        attribution=Attribution(_require(record, "attribution")),
        evidence_start=start,
        evidence_end=start + len(evidence),
    )


def _require(record: dict[str, str | None], key: str) -> str:
    value = record[key]
    if not isinstance(value, str):
        raise ValueError("gold claim field must be a string")
    return value
