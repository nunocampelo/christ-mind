from collections.abc import Sequence
from dataclasses import replace

import pytest

from application.extraction.extract_claims import (
    AmbiguousEvidenceError,
    CandidateClaim,
    EvidenceNotFoundError,
    RejectedCandidate,
    RejectionReason,
    anchor_claim,
    extract_claims,
)
from domain.claims.models import Attribution, Claim, Mode, Polarity, Predicate
from domain.sources.models import Source

NATURAL_SOURCE = Source(
    id="t1-1-6",
    book="ACIM",
    chapter=1,
    text="6. Miracles are natural. When they do NOT occur something has gone wrong.",
)
RIGHT_SOURCE = Source(
    id="t1-1-7",
    book="ACIM",
    chapter=1,
    text="7. Miracles are everyone’s right, but purification is necessary first.",
)
NATURAL = CandidateClaim(
    subject="miracles",
    verb_phrase="are",
    object="natural",
    predicate=Predicate.IS,
    polarity=Polarity.AFFIRMED,
    mode=Mode.ASSERTION,
    attribution=Attribution.COURSE,
    evidence="Miracles are natural.",
)
PURIFICATION = replace(
    NATURAL,
    verb_phrase="require first",
    object="purification",
    predicate=Predicate.REQUIRES,
    evidence="purification is necessary first",
)


class FakeExtractor:
    def __init__(self, candidates: dict[str, list[CandidateClaim]]):
        self._candidates = candidates

    def extract(self, source: Source) -> Sequence[CandidateClaim]:
        return self._candidates.get(source.id, [])


def test_anchor_claim_resolves_quoted_evidence_to_offsets():
    claim = anchor_claim(NATURAL_SOURCE, NATURAL)

    assert claim == Claim(
        source_id="t1-1-6",
        subject="miracles",
        predicate=Predicate.IS,
        object="natural",
        verb_phrase="are",
        polarity=Polarity.AFFIRMED,
        mode=Mode.ASSERTION,
        attribution=Attribution.COURSE,
        evidence_start=3,
        evidence_end=24,
    )
    assert NATURAL_SOURCE.text[claim.evidence_start : claim.evidence_end] == (
        "Miracles are natural."
    )


@pytest.mark.parametrize(
    ("evidence", "error"),
    [
        ("Miracles are supernatural.", EvidenceNotFoundError),
        ("miracles are natural.", EvidenceNotFoundError),
        ("", EvidenceNotFoundError),
        ("   ", EvidenceNotFoundError),
        ("ra", AmbiguousEvidenceError),
    ],
    ids=["invented", "case-differs", "empty", "whitespace", "ambiguous"],
)
def test_anchor_claim_rejects_unanchorable_evidence(
    evidence: str, error: type[Exception]
):
    with pytest.raises(error):
        anchor_claim(NATURAL_SOURCE, replace(NATURAL, evidence=evidence))


def test_extract_claims_anchors_each_source_under_its_own_id():
    extractor = FakeExtractor({"t1-1-6": [NATURAL], "t1-1-7": [PURIFICATION]})

    result = extract_claims([NATURAL_SOURCE, RIGHT_SOURCE], extractor)

    assert [(c.source_id, c.object) for c in result.claims] == [
        ("t1-1-6", "natural"),
        ("t1-1-7", "purification"),
    ]
    assert result.rejected == ()


def test_extract_claims_keeps_unanchorable_candidates_as_rejections():
    invented = replace(NATURAL, evidence="Miracles are rare.")
    ambiguous = replace(NATURAL, evidence="ra")
    extractor = FakeExtractor({"t1-1-6": [NATURAL, invented, ambiguous]})

    result = extract_claims([NATURAL_SOURCE], extractor)

    assert [c.object for c in result.claims] == ["natural"]
    assert result.rejected == (
        RejectedCandidate("t1-1-6", invented, RejectionReason.EVIDENCE_NOT_FOUND),
        RejectedCandidate("t1-1-6", ambiguous, RejectionReason.EVIDENCE_AMBIGUOUS),
    )


def test_extract_claims_with_no_candidates_returns_empty_result():
    result = extract_claims([NATURAL_SOURCE], FakeExtractor({}))

    assert (result.claims, result.rejected) == ((), ())
