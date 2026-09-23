"""Turns an extractor's candidate claims into `Claim`s anchored in source text.

Extractors quote their evidence instead of giving offsets, because models copy
text far more reliably than they count characters. A quote that isn't in the
source, or appears more than once, can't be anchored. Such candidates are
returned as rejections instead of being dropped, since how often a model invents
evidence is itself a measure of its quality.
"""

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from domain.claims.identity import compute_claim_id
from domain.claims.models import Attribution, Claim, Mode, Polarity, Predicate
from domain.sources.models import Source


class EvidenceError(ValueError):
    pass


class EvidenceNotFoundError(EvidenceError):
    pass


class AmbiguousEvidenceError(EvidenceError):
    pass


class ExtractionFailedError(Exception):
    """Raised by a `ClaimExtractor` when it got a response it can't turn into
    candidates. Only this is caught per source; any other error, such as a
    provider outage, stops the whole run.
    """


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


def parse_candidate(record: object) -> CandidateClaim:
    """Builds a candidate from a decoded JSON object, as written in gold files or
    returned by a prompted model. Raises `ValueError` if a field is missing or
    not one of the allowed values.
    """
    if not isinstance(record, dict):
        raise ValueError("candidate claim must be a JSON object")
    object_ = record.get("object")
    if object_ is not None and not isinstance(object_, str):
        raise ValueError("candidate claim object must be a string or null")
    return CandidateClaim(
        subject=_require_str(record, "subject"),
        verb_phrase=_require_str(record, "verb_phrase"),
        object=object_,
        predicate=Predicate(_require_str(record, "predicate")),
        polarity=Polarity(_require_str(record, "polarity")),
        mode=Mode(_require_str(record, "mode")),
        attribution=Attribution(_require_str(record, "attribution")),
        evidence=_require_str(record, "evidence"),
    )


def _require_str(record: dict[object, object], key: str) -> str:
    value = record.get(key)
    if not isinstance(value, str):
        raise ValueError("candidate claim field is missing or not a string")
    return value


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
class SourceExtraction:
    """One source's outcome. `failed` is True when the extractor raised
    `ExtractionFailedError`, in which case `claims` and `rejected` are empty.
    """

    source_id: str
    claims: tuple[Claim, ...]
    rejected: tuple[RejectedCandidate, ...]
    failed: bool


@dataclass(frozen=True)
class ExtractionResult:
    claims: tuple[Claim, ...]
    rejected: tuple[RejectedCandidate, ...]
    failed_source_ids: tuple[str, ...]


def extract_claims(
    sources: Iterable[Source],
    extractor: ClaimExtractor,
    on_source_complete: Callable[[SourceExtraction], None] | None = None,
) -> ExtractionResult:
    """Extracts and anchors claims from each source. When `on_source_complete` is
    given, it's called with that source's outcome as soon as the source finishes,
    so a caller can persist and report progress incrementally over a long run.
    """
    outcomes = []
    for source in sources:
        outcome = extract_source(source, extractor)
        outcomes.append(outcome)
        if on_source_complete is not None:
            on_source_complete(outcome)
    return collect_extraction(outcomes)


def collect_extraction(outcomes: Iterable[SourceExtraction]) -> ExtractionResult:
    """Folds per-source outcomes into one `ExtractionResult`. A caller that runs
    `extract_source` concurrently uses this to assemble the same result
    `extract_claims` would have returned serially.
    """
    claims = []
    rejected = []
    failed_source_ids = []
    for outcome in outcomes:
        claims.extend(outcome.claims)
        rejected.extend(outcome.rejected)
        if outcome.failed:
            failed_source_ids.append(outcome.source_id)
    return ExtractionResult(
        claims=tuple(claims),
        rejected=tuple(rejected),
        failed_source_ids=tuple(failed_source_ids),
    )


def extract_source(source: Source, extractor: ClaimExtractor) -> SourceExtraction:
    try:
        candidates = extractor.extract(source)
    except ExtractionFailedError:
        return SourceExtraction(source.id, (), (), failed=True)
    claims = []
    rejected = []
    for candidate in candidates:
        try:
            claims.append(anchor_claim(source, candidate))
        except EvidenceNotFoundError:
            reason = RejectionReason.EVIDENCE_NOT_FOUND
            rejected.append(RejectedCandidate(source.id, candidate, reason))
        except AmbiguousEvidenceError:
            reason = RejectionReason.EVIDENCE_AMBIGUOUS
            rejected.append(RejectedCandidate(source.id, candidate, reason))
    return SourceExtraction(
        source.id, tuple(claims), tuple(rejected), failed=False
    )


def anchor_claim(source: Source, candidate: CandidateClaim) -> Claim:
    evidence = candidate.evidence
    start = source.text.find(evidence) if evidence.strip() else -1
    if start == -1:
        raise EvidenceNotFoundError("evidence is not a substring of the source text")
    if source.text.find(evidence, start + 1) != -1:
        raise AmbiguousEvidenceError("evidence occurs more than once in the source text")

    return Claim(
        claim_id=compute_claim_id(
            source_id=source.id,
            evidence=evidence,
            subject=candidate.subject,
            predicate=candidate.predicate,
            object=candidate.object,
            polarity=candidate.polarity,
            mode=candidate.mode,
            attribution=candidate.attribution,
        ),
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
