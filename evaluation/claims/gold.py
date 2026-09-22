"""Loads hand-labelled gold claims from JSONL.

Gold lines use the same fields a prompted model returns, plus `source_id`.
They're parsed and anchored with the same `parse_candidate` and `anchor_claim`
the extractor uses, so gold and predicted claims can't disagree because of how
they were read. Anchoring against the parsed `Source.text` at load time also
means a parser or corpus change that moves or alters the text fails here
instead of silently re-pointing labels.
"""

import json
from collections.abc import Sequence
from pathlib import Path

from application.extraction.extract_claims import anchor_claim, parse_candidate
from domain.claims.models import Claim
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
            source = sources_by_id.get(record["source_id"])
            if source is None:
                raise ValueError("gold claim names an unknown source_id")
            claims.append(anchor_claim(source, parse_candidate(record)))
        except (KeyError, TypeError, ValueError) as e:
            raise GoldLabelError(f"invalid gold claim on line {line_number}") from e
    return claims
