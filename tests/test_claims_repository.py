import json
from pathlib import Path

import pytest

import infrastructure.database.claims as claims_module
from domain.claims.models import Attribution, Mode, Polarity, Predicate
from infrastructure.database.claims import list_claims


def test_list_claims_reconstructs_real_claims():
    claims = list_claims()

    assert len(claims) > 0
    # Every served item is an anchored Claim with a recomputed id and valid enums.
    sample = claims[0]
    assert len(sample.claim_id) == 16
    assert isinstance(sample.predicate, Predicate)
    assert isinstance(sample.attribution, Attribution)
    assert isinstance(sample.polarity, Polarity)
    assert isinstance(sample.mode, Mode)
    assert sample.source_id


@pytest.mark.parametrize(
    "source_id, object",
    [
        ("t1-1-86", "partial"),
        ("t3-4-8", "stranger to His Sons"),
        ("t4-1-12", "author of fear"),
    ],
)
def test_negated_claims_keep_their_negation_in_the_corpus(source_id: str, object: str):
    # These three read affirmative as subject-verb-object ("God is partial") but the
    # passage says the opposite ("God is NOT partial"). If a re-extraction ever stored
    # them AFFIRMED, the agent would report the negation of the Course -- lock it here.
    matches = [
        c
        for c in list_claims()
        if c.source_id == source_id and c.subject == "God" and c.object == object
    ]

    assert matches
    assert all(c.polarity is Polarity.NEGATED for c in matches)


def test_only_claim_lines_are_served_not_rejected_or_failed(tmp_path: Path, monkeypatch):
    data = tmp_path / "corpus.jsonl"
    data.write_text(
        "\n".join(
            json.dumps(line)
            for line in [
                {"type": "header", "split": "corpus"},
                {
                    "type": "claim",
                    "source_id": "t1-1",
                    "subject": "love",
                    "verb_phrase": "is",
                    "object": "all",
                    "predicate": "is",
                    "polarity": "affirmed",
                    "mode": "assertion",
                    "attribution": "course",
                    "evidence": "love is all",
                    "evidence_start": 0,
                    "evidence_end": 11,
                },
                {"type": "rejected", "source_id": "t1-1", "reason": "evidence_not_found"},
                {"type": "failed", "source_id": "t2-1"},
            ]
        )
    )
    monkeypatch.setattr(claims_module, "_DATA_FILE", data)

    claims = claims_module._load_claims()

    assert len(claims) == 1
    assert claims[0].subject == "love"


def test_missing_data_file_fails_loudly(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(claims_module, "_DATA_FILE", tmp_path / "absent.jsonl")

    with pytest.raises(FileNotFoundError, match="claim data file is missing"):
        claims_module._load_claims()
