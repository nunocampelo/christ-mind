import json
from pathlib import Path

import pytest

from application.extraction.extract_claims import CandidateClaim
from application.extraction.spans import AmbiguousEvidenceError, EvidenceNotFoundError
from domain.claims.models import Attribution, Mode, Polarity, Predicate
from domain.claims.serialization import ClaimLine
from domain.derivation.identity import compute_annotation_id
from domain.derivation.models import (
    AuthoringStatus,
    DerivedEntry,
    DerivedGold,
    DerivedKind,
    DerivedValidationError,
    PropositionSig,
    Support,
)
from domain.derivation.serialization import DerivedGoldFile
from domain.sources.models import Source
from evaluation.claims.fidelity.author import write_gold
from evaluation.claims.gold import load_gold_claims
from infrastructure.database.sources_acim import list_acim_sources

TEXT = (
    "5. The level-adjustment power of the miracle induces the right perception for healing. "
    "Until this has occurred healing cannot be understood. "
    "Forgiveness is an empty gesture unless it entails correction. "
    "Without this, it is essentially judgemental rather than healing."
)
SOURCE = Source(id="t3-1-5", book="acim", chapter=3, text=TEXT, section=1, paragraph=5)


def _condition_entry(source_id: str = "t3-1-5", evidence: str | None = None) -> DerivedEntry:
    return DerivedEntry(
        annotation_id="",
        source_id=source_id,
        kind=DerivedKind.CONDITION,
        evidence=evidence or "Forgiveness is an empty gesture unless it entails correction.",
        support=Support.LITERAL,
        condition_text="unless it entails correction",
        attaches_to=PropositionSig(
            subject="forgiveness",
            predicate=Predicate.IS,
            object="empty gesture",
            polarity=Polarity.AFFIRMED,
            mode=Mode.CONDITIONAL,
            attribution=Attribution.COURSE,
        ),
    )


def _description_entry() -> DerivedEntry:
    return DerivedEntry(
        annotation_id="",
        source_id="t3-1-5",
        kind=DerivedKind.DESCRIPTION,
        evidence="Without this, it is essentially judgemental rather than healing.",
        support=Support.INTERPRETED,
        description_text="judgemental rather than healing",
        describes=compute_annotation_id(_condition_entry()),
    )


def _gold(*entries: DerivedEntry) -> DerivedGold:
    return DerivedGold(
        source_id="t3-1-5",
        literal_status=AuthoringStatus.AUTHORED,
        derived_status=AuthoringStatus.AUTHORED,
        shared=entries,
    )


def _candidate(evidence: str = "Forgiveness is an empty gesture") -> CandidateClaim:
    return CandidateClaim(
        subject="forgiveness",
        verb_phrase="is an empty gesture",
        object="empty gesture",
        predicate=Predicate.IS,
        polarity=Polarity.AFFIRMED,
        mode=Mode.CONDITIONAL,
        attribution=Attribution.COURSE,
        evidence=evidence,
    )


def test_valid_gold_round_trips_both_layers(tmp_path: Path) -> None:
    gold = _gold(_condition_entry(), _description_entry())
    candidate = _candidate()

    derived_path, literal_path = write_gold(gold, [candidate], SOURCE, tmp_path)

    reloaded = DerivedGoldFile.model_validate_json(derived_path.read_text()).to_gold()
    assert reloaded.source_id == "t3-1-5"
    assert reloaded.literal_status is AuthoringStatus.AUTHORED
    assert reloaded.derived_status is AuthoringStatus.AUTHORED
    assert {e.annotation_id for e in reloaded.shared} == {
        compute_annotation_id(_condition_entry()),
        compute_annotation_id(_description_entry()),
    }

    claims = load_gold_claims(literal_path, [SOURCE])
    assert len(claims) == 1
    assert claims[0].subject == "forgiveness"
    assert claims[0].object == "empty gesture"
    assert SOURCE.text[claims[0].evidence_start : claims[0].evidence_end] == candidate.evidence


def test_round_trip_against_live_corpus_source(tmp_path: Path) -> None:
    """Author against the real `list_acim_sources()` t3-1-5 (not the hardcoded copy), so a
    future corpus edit that moved this text would fail here instead of silently drifting."""
    live = {s.id: s for s in list_acim_sources()}["t3-1-5"]
    candidate = _candidate()

    _, literal_path = write_gold(_gold(_condition_entry()), [candidate], live, tmp_path)

    claims = load_gold_claims(literal_path, list(list_acim_sources()))
    assert len(claims) == 1
    assert live.text[claims[0].evidence_start : claims[0].evidence_end] == candidate.evidence


def test_literal_line_is_byte_identical_to_claimline_serializer(tmp_path: Path) -> None:
    candidate = _candidate()
    _, literal_path = write_gold(_gold(_condition_entry()), [candidate], SOURCE, tmp_path)

    from application.extraction.extract_claims import anchor_claim

    expected = json.dumps(
        ClaimLine.from_claim(anchor_claim(SOURCE, candidate), candidate.evidence).model_dump()
    )
    assert literal_path.read_text() == expected + "\n"


def test_derived_evidence_not_in_source_raises_and_writes_nothing(tmp_path: Path) -> None:
    bad = _condition_entry(evidence="a quote that does not appear in the passage")
    with pytest.raises(EvidenceNotFoundError):
        write_gold(_gold(bad), [], SOURCE, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_derived_evidence_ambiguous_raises(tmp_path: Path) -> None:
    ambiguous = _condition_entry(evidence="healing")  # occurs twice in TEXT
    with pytest.raises(AmbiguousEvidenceError):
        write_gold(_gold(ambiguous), [], SOURCE, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_foreign_source_entry_raises(tmp_path: Path) -> None:
    foreign = _condition_entry(source_id="t9-9-9")
    gold = DerivedGold(
        source_id="t3-1-5",
        literal_status=AuthoringStatus.AUTHORED,
        derived_status=AuthoringStatus.AUTHORED,
        shared=(foreign,),
    )
    with pytest.raises(DerivedValidationError):
        write_gold(gold, [], SOURCE, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_gold_source_mismatch_raises(tmp_path: Path) -> None:
    other = Source(id="t1-1-1", book="acim", chapter=1, text=TEXT)
    with pytest.raises(DerivedValidationError):
        write_gold(_gold(_condition_entry()), [], other, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_duplicate_bundle_entry_raises(tmp_path: Path) -> None:
    dup = _condition_entry()
    gold = _gold(dup, _condition_entry())  # same recomputed id
    with pytest.raises(DerivedValidationError):
        write_gold(gold, [], SOURCE, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_literal_candidate_with_bad_span_raises(tmp_path: Path) -> None:
    bad = _candidate(evidence="not a substring of this source")
    with pytest.raises(EvidenceNotFoundError):
        write_gold(_gold(_condition_entry()), [bad], SOURCE, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_literal_candidate_ambiguous_raises(tmp_path: Path) -> None:
    ambiguous = _candidate(evidence="healing")  # occurs more than once in TEXT
    with pytest.raises(AmbiguousEvidenceError):
        write_gold(_gold(_condition_entry()), [ambiguous], SOURCE, tmp_path)
    assert list(tmp_path.iterdir()) == []


def test_mid_bundle_failure_leaves_both_files_absent(tmp_path: Path) -> None:
    good = _condition_entry()
    bad = _condition_entry(evidence="this quote is nowhere in the passage")
    gold = _gold(good, bad)
    with pytest.raises(EvidenceNotFoundError):
        write_gold(gold, [_candidate()], SOURCE, tmp_path)
    assert not (tmp_path / "t3-1-5.derived.json").exists()
    assert not (tmp_path / "t3-1-5.jsonl").exists()
    assert list(tmp_path.iterdir()) == []
