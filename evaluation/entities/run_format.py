"""The on-disk shape of a resolution run's header line.

A resolution file is one `entity` line per entity (see
`domain/entities/serialization.py`'s `EntityLine`) behind this `header` line, which
carries the `passages_sha256` of the corpus run it was resolved from -- so a resolution
can be checked for drift against that run before its entities are trusted, the same
discipline as `evaluation/claims/run.py`'s header, plus the pair score so the run file
is self-describing. The header is an evaluation run-record concern, not domain data, so
it stays here while `EntityLine` lives in the domain layer.
"""

from typing import Literal

from pydantic import BaseModel


class ScoreLine(BaseModel):
    """The pair-scoring result, embedded in the header so a run file is
    self-describing. Kept as primitive counts + a rate rather than importing the
    scorer's dataclass, so this on-disk shape doesn't depend on `score.py`."""

    true_positives: int
    false_positives: int
    false_negatives: int
    blocking_recall: float


class ResolutionHeader(BaseModel):
    type: Literal["header"] = "header"
    run_id: str
    created_at: str
    resolver: str
    resolver_prompt_version: str | None
    source_run_id: str
    passages_sha256: str
    mentions: int
    entities: int
    rejected: int
    failed: bool
    score: ScoreLine | None
