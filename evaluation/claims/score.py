"""Scores predicted claims against gold claims.

Only predictions for sources that appear in the gold set are scored, so
extracting a whole section and scoring against a partial gold set doesn't
count unlabelled passages as false positives.
"""

from collections import Counter, defaultdict
from collections.abc import Callable, Hashable, Sequence
from dataclasses import dataclass

from domain.claims.models import Claim


@dataclass(frozen=True)
class ClaimScore:
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
class ScoreReport:
    """`loose` matches on (source, subject, predicate, object); `strict` also
    requires polarity, mode, and attribution to agree. The mismatch counts say
    which of those three fields account for the gap between the two.
    """

    loose: ClaimScore
    strict: ClaimScore
    polarity_mismatches: int
    mode_mismatches: int
    attribution_mismatches: int


def score_claims(predicted: Sequence[Claim], gold: Sequence[Claim]) -> ScoreReport:
    gold_source_ids = {claim.source_id for claim in gold}
    predicted = [claim for claim in predicted if claim.source_id in gold_source_ids]

    polarity_mismatches = mode_mismatches = attribution_mismatches = 0
    for predicted_claim, gold_claim in _pair_loose_matches(predicted, gold):
        polarity_mismatches += predicted_claim.polarity != gold_claim.polarity
        mode_mismatches += predicted_claim.mode != gold_claim.mode
        attribution_mismatches += predicted_claim.attribution != gold_claim.attribution

    return ScoreReport(
        loose=_count(predicted, gold, _loose_key),
        strict=_count(predicted, gold, _strict_key),
        polarity_mismatches=polarity_mismatches,
        mode_mismatches=mode_mismatches,
        attribution_mismatches=attribution_mismatches,
    )


def _normalize(value: str | None) -> str | None:
    return None if value is None else " ".join(value.lower().split())


def _loose_key(claim: Claim) -> tuple[Hashable, ...]:
    return (
        claim.source_id,
        _normalize(claim.subject),
        claim.predicate,
        _normalize(claim.object),
    )


def _strict_key(claim: Claim) -> tuple[Hashable, ...]:
    return (*_loose_key(claim), claim.polarity, claim.mode, claim.attribution)


def _count(
    predicted: Sequence[Claim],
    gold: Sequence[Claim],
    key: Callable[[Claim], tuple[Hashable, ...]],
) -> ClaimScore:
    predicted_keys = Counter(map(key, predicted))
    gold_keys = Counter(map(key, gold))
    true_positives = (predicted_keys & gold_keys).total()
    return ClaimScore(
        true_positives=true_positives,
        false_positives=predicted_keys.total() - true_positives,
        false_negatives=gold_keys.total() - true_positives,
    )


def _pair_loose_matches(
    predicted: Sequence[Claim], gold: Sequence[Claim]
) -> list[tuple[Claim, Claim]]:
    """Pairs claims sharing a loose key, strict matches first, so a duplicate
    triple with different fields isn't paired against the wrong gold claim.
    """
    predicted_by_key: defaultdict[tuple[Hashable, ...], list[Claim]] = defaultdict(list)
    for claim in predicted:
        predicted_by_key[_loose_key(claim)].append(claim)

    pairs = []
    unpaired_gold = []
    for gold_claim in gold:
        candidates = predicted_by_key[_loose_key(gold_claim)]
        exact = next(
            (c for c in candidates if _strict_key(c) == _strict_key(gold_claim)),
            None,
        )
        if exact is None:
            unpaired_gold.append(gold_claim)
        else:
            candidates.remove(exact)
            pairs.append((exact, gold_claim))

    for gold_claim in unpaired_gold:
        candidates = predicted_by_key[_loose_key(gold_claim)]
        if candidates:
            pairs.append((candidates.pop(0), gold_claim))
    return pairs
