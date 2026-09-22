"""Turns an extractor's candidate claims into `Claim`s anchored in source text.

Extractors quote their evidence instead of giving offsets, because models copy
text far more reliably than they count characters. A quote that isn't in the
source, or appears more than once, can't be anchored. Such candidates are
returned as rejections instead of being dropped, since how often a model invents
evidence is itself a measure of its quality.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from domain.claims.models import Attribution, Claim, Mode, Polarity, Predicate
from domain.sources.models import Source


class EvidenceError(ValueError):
    pass


class EvidenceNotFoundError(EvidenceError):
    pass


class AmbiguousEvidenceError(EvidenceError):
    pass


@dataclass(frozen=True)
class CandidateClaim:
    subject: str
    verb_phrase: str
    object: str | None
    predicate: Predicate
    polarity: Polarity
    mode: Mode
    attribution: Attribution
    evidence: str


class ClaimExtractor(Protocol):
    def extract(self, source: Source) -> Sequence[CandidateClaim]: ...


class RejectionReason(StrEnum):
    EVIDENCE_NOT_FOUND = "evidence_not_found"
    EVIDENCE_AMBIGUOUS = "evidence_ambiguous"


@dataclass(frozen=True)
class RejectedCandidate:
    source_id: str
    candidate: CandidateClaim
    reason: RejectionReason


@dataclass(frozen=True)
class ExtractionResult:
    claims: tuple[Claim, ...]
    rejected: tuple[RejectedCandidate, ...]


def extract_claims(
    sources: Iterable[Source], extractor: ClaimExtractor
) -> ExtractionResult:
    claims = []
    rejected = []
    for source in sources:
        for candidate in extractor.extract(source):
            try:
                claims.append(anchor_claim(source, candidate))
            except EvidenceNotFoundError:
                reason = RejectionReason.EVIDENCE_NOT_FOUND
                rejected.append(RejectedCandidate(source.id, candidate, reason))
            except AmbiguousEvidenceError:
                reason = RejectionReason.EVIDENCE_AMBIGUOUS
                rejected.append(RejectedCandidate(source.id, candidate, reason))
    return ExtractionResult(claims=tuple(claims), rejected=tuple(rejected))


def anchor_claim(source: Source, candidate: CandidateClaim) -> Claim:
    evidence = candidate.evidence
    start = source.text.find(evidence) if evidence.strip() else -1
    if start == -1:
        raise EvidenceNotFoundError("evidence is not a substring of the source text")
    if source.text.find(evidence, start + 1) != -1:
        raise AmbiguousEvidenceError("evidence occurs more than once in the source text")

    return Claim(
        source_id=source.id,
        subject=candidate.subject,
        predicate=candidate.predicate,
        object=candidate.object,
        verb_phrase=candidate.verb_phrase,
        polarity=candidate.polarity,
        mode=candidate.mode,
        attribution=candidate.attribution,
        evidence_start=start,
        evidence_end=start + len(evidence),
    )
