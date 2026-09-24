"""Scores a resolution partition against gold mention pairs.

The resolver produces a partition (entities); the gold is pairs. Two mentions are
predicted "same" iff the partition puts them in one entity, so a gold pair is scored
by looking up where its two forms landed:

  true positive   gold same,      partition merges them
  false positive  gold different, partition merges them
  false negative  gold same,      partition keeps them apart

This is the standard pairwise clustering metric, kept separate from the claim scorer
in `evaluation/claims/score.py`: it measures a partition of mentions, not a match of
claim triples, and sharing a scorer would blur two different evaluation units.

Blocking recall is reported alongside, because a gold same-pair the blocker never
proposes can never be a true positive however good the resolver is -- so a low pair
recall could be the blocker's fault, not the model's, and the two must be told apart
(see the increment #6 plan's blocking-recall gap).
"""

from collections.abc import Sequence
from dataclasses import dataclass

from application.resolution.resolve_entities import candidate_pairs
from domain.entities.models import Entity
from evaluation.entities.gold import GoldPair


@dataclass(frozen=True)
class PairScore:
    true_positives: int
    false_positives: int
    false_negatives: int

    @property
    def precision(self) -> float:
        predicted = self.true_positives + self.false_positives
        return self.true_positives / predicted if predicted else 0.0

    @property
    def recall(self) -> float:
        expected = self.true_positives + self.false_negatives
        return self.true_positives / expected if expected else 0.0


@dataclass(frozen=True)
class PairReport:
    score: PairScore
    blocking_recall: float
    """Fraction of gold same-pairs the blocker proposes at all -- the ceiling on
    recall before the resolver judges anything."""


def _entity_of(entities: Sequence[Entity]) -> dict[str, str]:
    return {
        mention: entity.entity_id
        for entity in entities
        for mention in entity.mentions
    }


def score_pairs(entities: Sequence[Entity], gold: Sequence[GoldPair]) -> PairReport:
    entity_of = _entity_of(entities)
    tp = fp = fn = 0
    for pair in gold:
        merged = (
            pair.left in entity_of
            and entity_of[pair.left] == entity_of.get(pair.right)
        )
        if pair.same and merged:
            tp += 1
        elif pair.same and not merged:
            fn += 1
        elif not pair.same and merged:
            fp += 1

    return PairReport(
        score=PairScore(true_positives=tp, false_positives=fp, false_negatives=fn),
        blocking_recall=blocking_recall(gold),
    )


def blocking_recall(gold: Sequence[GoldPair]) -> float:
    same_pairs = [p for p in gold if p.same]
    if not same_pairs:
        return 0.0
    mentions = {p.left for p in same_pairs} | {p.right for p in same_pairs}
    proposed = {
        frozenset({c.left, c.right}) for c in candidate_pairs(mentions)
    }
    reachable = sum(
        1 for p in same_pairs if frozenset({p.left, p.right}) in proposed
    )
    return reachable / len(same_pairs)
