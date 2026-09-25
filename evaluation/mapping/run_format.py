"""The on-disk shape of a situation-mapping run's records.

A mapping run file is a `header` line carrying the run's provenance and aggregate
score, then one `situation` line per gold situation recording what the mapper produced
and how that situation scored -- so the file is self-describing, the same discipline as
`evaluation/entities/run_format.py`. Unlike resolution there is no source-corpus hash:
the mapper's input is the gold situations themselves, so the gold file's own hash is
the provenance that matters. These are run-record concerns, not domain data.
"""

from typing import Literal

from pydantic import BaseModel


class ScoreLine(BaseModel):
    """The macro-averaged set score, embedded in the header so a run file is
    self-describing. Kept as primitive rates rather than importing the scorer's
    dataclass, so this on-disk shape doesn't depend on `score.py`."""

    precision: float
    recall: float
    f1: float
    situations: int


class MappingHeader(BaseModel):
    type: Literal["header"] = "header"
    run_id: str
    created_at: str
    mapper: str
    map_version: str
    gold_sha256: str
    score: ScoreLine


class SituationLine(BaseModel):
    type: Literal["situation"] = "situation"
    situation: str
    predicted: list[str]
    expected: list[str]
    true_positives: int
