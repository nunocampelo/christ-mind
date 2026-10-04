import pytest

from application.extraction.extract_claims import CandidateClaim, anchor_claim
from application.extraction.spans import (
    AmbiguousEvidenceError,
    EvidenceNotFoundError,
    validate_span,
)
from domain.claims.models import Attribution, Mode, Polarity, Predicate
from domain.sources.models import Source

SOURCE = Source(id="s", book="ACIM", chapter=1, text="Forgiveness is correction, not judgement.")


def test_validate_span_returns_offsets():
    assert validate_span(SOURCE, "correction") == (15, 25)
    assert SOURCE.text[15:25] == "correction"


def test_validate_span_not_found():
    with pytest.raises(EvidenceNotFoundError):
        validate_span(SOURCE, "healing")


def test_validate_span_blank_is_not_found():
    with pytest.raises(EvidenceNotFoundError):
        validate_span(SOURCE, "   ")


def test_validate_span_ambiguous():
    source = Source(id="s", book="ACIM", chapter=1, text="love and love")
    with pytest.raises(AmbiguousEvidenceError):
        validate_span(source, "love")


def test_anchor_claim_still_anchors_via_validate_span():
    candidate = CandidateClaim(
        subject="Forgiveness",
        verb_phrase="is",
        object="correction",
        predicate=Predicate.IS,
        polarity=Polarity.AFFIRMED,
        mode=Mode.ASSERTION,
        attribution=Attribution.COURSE,
        evidence="Forgiveness is correction",
    )
    claim = anchor_claim(SOURCE, candidate)
    assert (claim.evidence_start, claim.evidence_end) == (0, len("Forgiveness is correction"))


def test_anchor_claim_rejects_missing_evidence():
    candidate = CandidateClaim(
        subject="x",
        verb_phrase="is",
        object=None,
        predicate=Predicate.IS,
        polarity=Polarity.AFFIRMED,
        mode=Mode.ASSERTION,
        attribution=Attribution.COURSE,
        evidence="not in the source",
    )
    with pytest.raises(EvidenceNotFoundError):
        anchor_claim(SOURCE, candidate)
