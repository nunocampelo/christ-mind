import pytest

from application.retrieval.evidence import EvidenceResolutionError, evidence_text
from domain.claims.models import Attribution, Claim, Mode, Polarity, Predicate
from infrastructure.database.sources import list_sources


def _claim(source_id: str, start: int, end: int) -> Claim:
    return Claim(
        claim_id="test",
        source_id=source_id,
        subject="Peace of God",
        predicate=Predicate.OTHER,
        object="herein",
        verb_phrase="lies",
        polarity=Polarity.AFFIRMED,
        mode=Mode.ASSERTION,
        attribution=Attribution.COURSE,
        evidence_start=start,
        evidence_end=end,
    )


def test_evidence_text_returns_the_source_substring():
    source = next(s for s in list_sources() if s.id == "t1-0-4")
    claim = _claim("t1-0-4", 0, 29)

    quote = evidence_text(claim)

    assert quote == source.text[0:29]
    assert quote == "Herein lies the Peace of God."


def test_evidence_text_unknown_source_raises():
    with pytest.raises(EvidenceResolutionError):
        evidence_text(_claim("no-such-source", 0, 5))


def test_evidence_text_out_of_range_offsets_raise():
    source = next(s for s in list_sources() if s.id == "t1-0-4")
    with pytest.raises(EvidenceResolutionError):
        evidence_text(_claim("t1-0-4", 0, len(source.text) + 1))
