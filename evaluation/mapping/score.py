"""Scores predicted concepts against situation gold as a set-overlap metric.

Each situation is scored independently: the predicted concept set is compared to the
expected set, and per-situation precision/recall are macro-averaged across situations
(each situation counts once, regardless of how many concepts it has). Concepts are
compared case- and whitespace-normalised, matching the mapper's own normalisation in
`application/mapping/prompt.py`, so casing alone is never a miss.

This is deliberately a set metric, not a ranked one: #9's mapper is unordered by design
(no relevance ranking -- see the increment plan's scope guards). Kept separate from the
claim and pair scorers because it measures a set of mentions per situation, a third
evaluation unit.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from evaluation.mapping.gold import GoldSituation


def _normalise(concepts: Iterable[str]) -> set[str]:
    return {c.strip().casefold() for c in concepts if c.strip()}


@dataclass(frozen=True)
class SituationScore:
    situation: str
    true_positives: int
    predicted: int
    expected: int

    @property
    def precision(self) -> float:
        return self.true_positives / self.predicted if self.predicted else 0.0

    @property
    def recall(self) -> float:
        return self.true_positives / self.expected if self.expected else 0.0


@dataclass(frozen=True)
class MappingReport:
    per_situation: tuple[SituationScore, ...]

    @property
    def precision(self) -> float:
        return _mean(s.precision for s in self.per_situation)

    @property
    def recall(self) -> float:
        return _mean(s.recall for s in self.per_situation)

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p + r else 0.0


def score_situation(predicted: Iterable[str], gold: GoldSituation) -> SituationScore:
    predicted_set = _normalise(predicted)
    expected_set = _normalise(gold.concepts)
    return SituationScore(
        situation=gold.situation,
        true_positives=len(predicted_set & expected_set),
        predicted=len(predicted_set),
        expected=len(expected_set),
    )


def score_mapping(
    predictions: Sequence[tuple[GoldSituation, list[str]]],
) -> MappingReport:
    return MappingReport(
        per_situation=tuple(
            score_situation(predicted, gold) for gold, predicted in predictions
        )
    )


def _mean(values: Iterable[float]) -> float:
    values = list(values)
    return sum(values) / len(values) if values else 0.0
