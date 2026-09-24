"""Partitions observed mention surface forms into entities.

Resolution never invents a canonical name: it decides, for pairs of surface forms
the extractor actually produced, which name the same thing, then takes the transitive
closure of the "same" judgements. This mirrors extraction's discipline -- the model
chooses among given options, it doesn't generate free text that would splinter (see
the increment #6 plan). A judgement naming a mention that wasn't in the presented pair
is rejected, the way an unanchorable claim is, because how often the model does that
is a quality signal.

Candidate pairs come from blocking, not all-pairs: two mentions are only judged if a
cheap lexical test already thinks they might match. A pair the blocker never proposes
can never be merged, so blocking recall is measured directly by the pair gold set.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from domain.entities.identity import compute_entity_id
from domain.entities.models import Entity
from evaluation.claims.score import _normalize


class ResolutionFailedError(Exception):
    """Raised by a `ResolveEntities` when it got a response it can't turn into
    verdicts. Only this is caught per batch; any other error, such as a provider
    outage, stops the whole run.
    """


@dataclass(frozen=True)
class CandidatePair:
    """Two distinct surface forms a resolver is asked to judge. Ordered so a pair
    and its reverse are the same candidate (`left < right`), so the blocker never
    proposes both directions."""

    left: str
    right: str


@dataclass(frozen=True)
class PairVerdict:
    pair: CandidatePair
    same: bool


class RejectionReason(StrEnum):
    MENTION_NOT_IN_PAIR = "mention_not_in_pair"


@dataclass(frozen=True)
class RejectedVerdict:
    verdict: PairVerdict
    reason: RejectionReason


class ResolveEntities(Protocol):
    def judge(self, pairs: Sequence[CandidatePair]) -> Sequence[PairVerdict]: ...


@dataclass(frozen=True)
class ResolutionResult:
    entities: tuple[Entity, ...]
    rejected: tuple[RejectedVerdict, ...]
    failed: bool


def candidate_pairs(mentions: Iterable[str]) -> list[CandidatePair]:
    """Blocks mentions into candidate pairs. Two mentions are a candidate when they
    share a normalised form (the free floor -- caps and determiner variants) or share
    their head token, which catches cross-block modifier differences the normaliser
    can't ("the ego" vs "the ego's wish", head token "ego"). Head-token blocking is
    deliberately loose: a false candidate only costs the resolver one judgement,
    while a missing candidate is an unrecoverable miss.
    """
    surfaces = sorted(set(mentions))
    keys: dict[str, set[str]] = {}
    for surface in surfaces:
        normalised = _normalize(surface) or ""
        head = _head_token(surface)
        for key in {normalised, head}:
            keys.setdefault(key, set()).add(surface)

    pairs: set[CandidatePair] = set()
    for members in keys.values():
        ordered = sorted(members)
        for i, left in enumerate(ordered):
            for right in ordered[i + 1 :]:
                pairs.add(CandidatePair(left, right))
    return sorted(pairs, key=lambda p: (p.left, p.right))


def _head_token(surface: str) -> str:
    normalised = _normalize(surface) or ""
    tokens = normalised.split()
    return tokens[-1] if tokens else ""


def resolve(mentions: Sequence[str], resolver: ResolveEntities) -> ResolutionResult:
    """Judges the blocked candidate pairs and takes the transitive closure of the
    "same" verdicts. Every mention ends up in exactly one entity -- an unmatched
    mention is a singleton entity, not dropped.
    """
    pairs = candidate_pairs(mentions)
    try:
        verdicts = resolver.judge(pairs)
    except ResolutionFailedError:
        return ResolutionResult((), (), failed=True)

    presented = {(p.left, p.right) for p in pairs}
    rejected: list[RejectedVerdict] = []
    merges: list[CandidatePair] = []
    for verdict in verdicts:
        pair = verdict.pair
        if (pair.left, pair.right) not in presented:
            rejected.append(
                RejectedVerdict(verdict, RejectionReason.MENTION_NOT_IN_PAIR)
            )
            continue
        if verdict.same:
            merges.append(pair)

    entities = _closure(mentions, merges)
    return ResolutionResult(tuple(entities), tuple(rejected), failed=False)


def _closure(mentions: Iterable[str], merges: Iterable[CandidatePair]) -> list[Entity]:
    parent: dict[str, str] = {m: m for m in mentions}

    def find(x: str) -> str:
        root = x
        while parent[root] != root:
            root = parent[root]
        while parent[x] != root:
            parent[x], x = root, parent[x]
        return root

    for pair in merges:
        parent.setdefault(pair.left, pair.left)
        parent.setdefault(pair.right, pair.right)
        parent[find(pair.left)] = find(pair.right)

    groups: dict[str, set[str]] = {}
    for mention in parent:
        groups.setdefault(find(mention), set()).add(mention)

    return [
        Entity(entity_id=compute_entity_id(members), mentions=frozenset(members))
        for members in groups.values()
    ]
