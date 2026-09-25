from pathlib import Path

import pytest

from evaluation.mapping.gold import (
    GoldSituation,
    GoldSituationError,
    load_gold_situations,
)
from evaluation.mapping.score import score_mapping, score_situation

DEV_GOLD = Path("evaluation/mapping/gold/situations.jsonl")
HOLDOUT_GOLD = Path("evaluation/mapping/gold/situations_holdout.jsonl")


def test_committed_gold_loads():
    dev = load_gold_situations(DEV_GOLD)
    holdout = load_gold_situations(HOLDOUT_GOLD)
    assert len(dev) >= 8
    assert holdout
    assert all(g.concepts for g in dev + holdout)


@pytest.mark.parametrize(
    "line",
    [
        '{"situation": "x"}',
        '{"concepts": ["anger"]}',
        '{"situation": "", "concepts": ["anger"]}',
        '{"situation": "x", "concepts": []}',
        '{"situation": "x", "concepts": "anger"}',
        '{"situation": "x", "concepts": ["anger", 3]}',
        "not json",
    ],
)
def test_malformed_gold_fails_loudly(tmp_path: Path, line: str):
    path = tmp_path / "bad.jsonl"
    path.write_text(line + "\n")
    with pytest.raises(GoldSituationError):
        load_gold_situations(path)


def test_score_situation_counts_overlap_case_insensitively():
    gold = GoldSituation(
        situation="s", concepts=frozenset({"anger", "criticism", "judgment"})
    )
    score = score_situation(["Anger", " criticism ", "fear"], gold)
    assert score.true_positives == 2
    assert score.predicted == 3
    assert score.expected == 3
    assert score.precision == pytest.approx(2 / 3)
    assert score.recall == pytest.approx(2 / 3)


def test_score_mapping_macro_averages_per_situation():
    perfect = GoldSituation(situation="a", concepts=frozenset({"anger"}))
    missed = GoldSituation(situation="b", concepts=frozenset({"guilt", "fear"}))
    report = score_mapping(
        [
            (perfect, ["anger"]),
            (missed, ["guilt", "wrong"]),
        ]
    )
    # situation a: P 1.0 R 1.0 ; situation b: P 0.5 R 0.5 -> macro P/R 0.75
    assert report.precision == pytest.approx(0.75)
    assert report.recall == pytest.approx(0.75)
    assert report.f1 == pytest.approx(0.75)
