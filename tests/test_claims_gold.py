from pathlib import Path

import pytest

from domain.claims.models import Attribution, Mode, Polarity, Predicate
from domain.sources.models import Source
from evaluation.claims.gold import GoldLabelError, load_gold_claims
from infrastructure.database.sources_acim import list_acim_sources

GOLD_DIR = Path(__file__).parent.parent / "evaluation/claims/gold"
GOLD_T1_1 = GOLD_DIR / "t1_1.jsonl"
GOLD_T1_1_HOLDOUT = GOLD_DIR / "t1_1_holdout.jsonl"

SOURCE = Source(id="s1", book="ACIM", chapter=1, text="Miracles are natural.")


def _write(tmp_path: Path, line: str) -> Path:
    path = tmp_path / "gold.jsonl"
    path.write_text(line + "\n")
    return path


def _line(evidence: str, source_id: str = "s1", predicate: str = "is") -> str:
    return (
        f'{{"source_id": "{source_id}", "subject": "miracles", '
        f'"predicate": "{predicate}", "object": "natural", "verb_phrase": "are", '
        f'"polarity": "affirmed", "mode": "assertion", "attribution": "course", '
        f'"evidence": "{evidence}"}}'
    )


def test_t1_1_gold_evidence_resolves_against_parsed_corpus():
    sources = list_acim_sources()
    texts = {source.id: source.text for source in sources}

    claims = load_gold_claims(GOLD_T1_1, sources)

    requirement = next(c for c in claims if c.predicate == Predicate.REQUIRES)
    assert requirement.source_id == "t1-1-7"
    assert requirement.object == "purification"
    assert (
        texts["t1-1-7"][requirement.evidence_start : requirement.evidence_end]
        == "purification is necessary first"
    )


def test_t1_1_gold_encodes_negation_and_normative_mode():
    claims = load_gold_claims(GOLD_T1_1, list_acim_sources())

    control = next(c for c in claims if c.object == "conscious control")
    assert control.polarity == Polarity.NEGATED
    assert control.mode == Mode.NORMATIVE


def test_t1_1_holdout_covers_twenty_principles_disjoint_from_dev():
    sources = list_acim_sources()

    dev_ids = {c.source_id for c in load_gold_claims(GOLD_T1_1, sources)}
    holdout_ids = {c.source_id for c in load_gold_claims(GOLD_T1_1_HOLDOUT, sources)}

    assert len(dev_ids) == 15
    assert len(holdout_ids) == 5
    assert dev_ids.isdisjoint(holdout_ids)


def test_t1_1_holdout_attributes_rejected_beliefs_to_others():
    claims = load_gold_claims(GOLD_T1_1_HOLDOUT, list_acim_sources())

    darkness = next(c for c in claims if c.subject == "darkness")
    assert darkness.source_id == "t1-1-22"
    assert darkness.attribution == Attribution.OTHERS


def test_load_gold_claims_resolves_evidence_offsets(tmp_path: Path):
    path = _write(tmp_path, _line("natural"))

    [claim] = load_gold_claims(path, [SOURCE])

    assert (claim.evidence_start, claim.evidence_end) == (13, 20)


@pytest.mark.parametrize(
    "line",
    [
        _line("supernatural"),
        _line("a"),
        _line("natural", source_id="missing"),
        _line("natural", predicate="is_not"),
        '{"source_id": "s1"}',
        "not json",
    ],
    ids=[
        "evidence-not-in-text",
        "evidence-ambiguous",
        "unknown-source",
        "unknown-predicate",
        "missing-fields",
        "malformed-json",
    ],
)
def test_load_gold_claims_rejects_invalid_labels(tmp_path: Path, line: str):
    with pytest.raises(GoldLabelError):
        load_gold_claims(_write(tmp_path, line), [SOURCE])
