"""Anchoring a quoted span to offsets in a source, and the errors that raising fails with.

A quote that isn't in the source, or appears more than once, can't be anchored. Both the
claim extractor and the fidelity gold schema need this check, so it lives here on its own
rather than inside `anchor_claim` -- a derived-gold entry can be span-validated without
constructing a dummy `CandidateClaim`. `extract_claims` imports these errors from here; the
dependency only ever runs that direction.
"""

from domain.sources.models import Source


class EvidenceError(ValueError):
    pass


class EvidenceNotFoundError(EvidenceError):
    pass


class AmbiguousEvidenceError(EvidenceError):
    pass


def validate_span(source: Source, quote: str) -> tuple[int, int]:
    start = source.text.find(quote) if quote.strip() else -1
    if start == -1:
        raise EvidenceNotFoundError("evidence is not a substring of the source text")
    if source.text.find(quote, start + 1) != -1:
        raise AmbiguousEvidenceError("evidence occurs more than once in the source text")
    return start, start + len(quote)
