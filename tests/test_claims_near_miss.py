import json
from dataclasses import replace
from pathlib import Path

import pytest

import evaluation.claims.near_miss as near_miss
from domain.claims.models import Attribution, Claim, Mode, Polarity, Predicate
from domain.sources.models import Source
from evaluation.claims.near_miss import report
from evaluation.claims.run import Split

SOURCE = Source(id="t1-1-1", book="T", chapter=1, text="a b c d e f g h i j")

# Placeholder claim_id: near_miss keys claims by signature and recomputes the id
# when reading a run line, so the fixture's id is never compared. `_write_run`
# deliberately omits claim_id from the line to exercise that recompute path.
GOLD = Claim(
    claim_id="gold",
    source_id="t1-1-1",
    subject="love",
    predicate=Predicate.CAUSES,
    object="miracles",
    verb_phrase="causes",
    polarity=Polarity.AFFIRMED,
    mode=Mode.ASSERTION,
    attribution=Attribution.COURSE,
    evidence_start=0,
    evidence_end=5,
)


def _write_run(tmp_path: Path, claims: list[Claim]) -> Path:
    lines: list[dict[str, object]] = [{"type": "header", "split": "dev"}]
    for claim in claims:
        lines.append(
            {
                "type": "claim",
                "source_id": claim.source_id,
                "subject": claim.subject,
                "verb_phrase": claim.verb_phrase,
                "object": claim.object,
                "predicate": claim.predicate,
                "polarity": claim.polarity,
                "mode": claim.mode,
                "attribution": claim.attribution,
                "evidence": SOURCE.text[claim.evidence_start : claim.evidence_end],
                "evidence_start": claim.evidence_start,
                "evidence_end": claim.evidence_end,
            }
        )
    path = tmp_path / "run.jsonl"
    path.write_text(
        "".join(json.dumps(line, ensure_ascii=False) + "\n" for line in lines)
    )
    return path


@pytest.fixture
def stub_gold(monkeypatch: pytest.MonkeyPatch):
    def _use(gold: list[Claim]) -> None:
        # The dev split spans two gold files; return the claims for the first
        # file only, so the total gold set is exactly `gold`.
        first_path = near_miss.GOLD_FILES[Split.DEV][0]
        monkeypatch.setattr(
            near_miss,
            "load_gold_claims",
            lambda path, sources: gold if path == first_path else [],
        )

    return _use


def test_reports_nearest_overlapping_prediction_and_its_differing_fields(
    tmp_path: Path, stub_gold
):
    stub_gold([GOLD])
    reversed_pred = replace(GOLD, subject="miracles", object="love")

    text = report(_write_run(tmp_path, [reversed_pred]), sources=[SOURCE])

    assert "1 near-miss gold claims" in text
    assert "gold: love | causes | miracles" in text
    assert "near: miracles | causes | love" in text
    assert "differs on: subject, object" in text
    assert "subject: 1" in text
    assert "object: 1" in text


def test_prediction_overlapping_no_gold_is_listed_separately(
    tmp_path: Path, stub_gold
):
    stub_gold([GOLD])
    extra = replace(
        GOLD, subject="fear", object="attack", evidence_start=15, evidence_end=19
    )

    text = report(_write_run(tmp_path, [GOLD, extra]), sources=[SOURCE])

    assert "0 near-miss gold claims" in text
    assert "Predictions overlapping no gold evidence (1)" in text
    assert "fear | causes | attack" in text
