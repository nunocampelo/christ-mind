"""Loads hand-labelled gold claims from JSONL.

Gold files quote their evidence as an extractor does, and are anchored with
the same `anchor_claim`, so gold and predicted offsets can't disagree because
of how they were resolved. Anchoring against the parsed `Source.text` at load
time also means a parser or corpus change that moves or alters the text fails
here instead of silently re-pointing labels.
"""

import json
from collections.abc import Sequence
from pathlib import Path

from application.extraction.extract_claims import CandidateClaim, anchor_claim
from domain.claims.models import Attribution, Claim, Mode, Polarity, Predicate
from domain.sources.models import Source


class GoldLabelError(ValueError):
    pass


def load_gold_claims(path: Path, sources: Sequence[Source]) -> list[Claim]:
    sources_by_id = {source.id: source for source in sources}
    claims = []
    for line_number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            source = sources_by_id.get(_require(record, "source_id"))
            if source is None:
                raise ValueError("gold claim names an unknown source_id")
            claims.append(anchor_claim(source, _to_candidate(record)))
        except (KeyError, ValueError) as e:
            raise GoldLabelError(f"invalid gold claim on line {line_number}") from e
    return claims


def _to_candidate(record: dict[str, str | None]) -> CandidateClaim:
    return CandidateClaim(
        subject=_require(record, "subject"),
        verb_phrase=_require(record, "verb_phrase"),
        object=record.get("object"),
        predicate=Predicate(_require(record, "predicate")),
        polarity=Polarity(_require(record, "polarity")),
        mode=Mode(_require(record, "mode")),
        attribution=Attribution(_require(record, "attribution")),
        evidence=_require(record, "evidence"),
    )


def _require(record: dict[str, str | None], key: str) -> str:
    value = record[key]
    if not isinstance(value, str):
        raise ValueError("gold claim field must be a string")
    return value
