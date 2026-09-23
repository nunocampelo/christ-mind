"""Scores predicted claims against gold claims.

Only predictions for sources that appear in the gold set are scored, so
extracting a whole section and scoring against a partial gold set doesn't
count unlabelled passages as false positives.

Three tiers answer three questions. `loose` is a regression detector for
literal correctness (triple match after normalisation). `strict` also requires
polarity, mode, and attribution to agree, and is the primary metric that must
rise. `relaxed` is a diagnostic for surface-form disagreement: it keeps the
predicate but matches subject/object by containment when the evidence spans
overlap, so it answers "is the model extracting the same claim despite
wording?" -- never the optimization target, since tuning toward it rewards
broad predictions that score through containment.
"""

from collections import Counter, defaultdict
from collections.abc import Callable, Hashable, Sequence
from dataclasses import dataclass

from domain.claims.models import Claim

_LEADING_DETERMINERS = frozenset(
    {"the", "a", "an", "this", "that", "their", "his", "its"}
)
_PUNCTUATION = str.maketrans("", "", '.,?!"')
_QUOTE_FOLDING = str.maketrans("’‘“”", "''\"\"")


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
    requires polarity, mode, and attribution to agree; `relaxed` matches
    subject/object by containment over overlapping evidence. The mismatch counts
    say which of polarity/mode/attribution account for the loose-strict gap.
    """

    loose: ClaimScore
    strict: ClaimScore
    relaxed: ClaimScore
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
        relaxed=_count_relaxed(predicted, gold),
        polarity_mismatches=polarity_mismatches,
        mode_mismatches=mode_mismatches,
        attribution_mismatches=attribution_mismatches,
    )


def _normalize(value: str | None) -> str | None:
    if value is None:
        return None
    folded = value.lower().translate(_QUOTE_FOLDING).translate(_PUNCTUATION)
    words = folded.split()
    while words and words[0] in _LEADING_DETERMINERS:
        words.pop(0)
    return " ".join(words)


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


def _evidence_overlaps(a: Claim, b: Claim) -> bool:
    return a.evidence_start < b.evidence_end and b.evidence_start < a.evidence_end


def _phrase_contains(a: str | None, b: str | None) -> bool:
    """One normalised phrase contains the other. Both null counts as a match;
    exactly one null does not.
    """
    na, nb = _normalize(a), _normalize(b)
    if na is None or nb is None:
        return na is None and nb is None
    return na in nb or nb in na


def _relaxed_matches(predicted: Claim, gold: Claim) -> bool:
    return (
        predicted.source_id == gold.source_id
        and predicted.predicate == gold.predicate
        and _evidence_overlaps(predicted, gold)
        and _phrase_contains(predicted.subject, gold.subject)
        and _phrase_contains(predicted.object, gold.object)
    )


@dataclass(frozen=True)
class RelaxedPairing:
    """The one-to-one relaxed match of predictions to gold: `pairs` are matched
    (predicted, gold), `unmatched_gold` are gold claims with no relaxed partner,
    and `unmatched_predicted` are predictions that matched no gold claim.
    """

    pairs: list[tuple[Claim, Claim]]
    unmatched_gold: list[Claim]
    unmatched_predicted: list[Claim]


def relaxed_pairing(
    predicted: Sequence[Claim], gold: Sequence[Claim]
) -> RelaxedPairing:
    """Pairs one-to-one, strict matches first so a claim already counted under
    strict consumes its gold partner and can't also be reached by a broad
    containment match, then containment matches for the rest. Used both to count
    the relaxed tier and by the near-miss report, so "matched" means the same in
    both.
    """
    remaining_predicted = list(predicted)
    pairs: list[tuple[Claim, Claim]] = []
    pending_gold: list[Claim] = []

    for gold_claim in gold:
        exact = next(
            (c for c in remaining_predicted if _strict_key(c) == _strict_key(gold_claim)),
            None,
        )
        if exact is None:
            pending_gold.append(gold_claim)
        else:
            remaining_predicted.remove(exact)
            pairs.append((exact, gold_claim))

    unmatched_gold: list[Claim] = []
    for gold_claim in pending_gold:
        partner = next(
            (c for c in remaining_predicted if _relaxed_matches(c, gold_claim)),
            None,
        )
        if partner is None:
            unmatched_gold.append(gold_claim)
        else:
            remaining_predicted.remove(partner)
            pairs.append((partner, gold_claim))

    return RelaxedPairing(
        pairs=pairs,
        unmatched_gold=unmatched_gold,
        unmatched_predicted=remaining_predicted,
    )


def _count_relaxed(predicted: Sequence[Claim], gold: Sequence[Claim]) -> ClaimScore:
    true_positives = len(relaxed_pairing(predicted, gold).pairs)
    return ClaimScore(
        true_positives=true_positives,
        false_positives=len(predicted) - true_positives,
        false_negatives=len(gold) - true_positives,
    )
