import json
from pathlib import Path

import pytest

from evaluation.entities.gold import GoldPair, GoldPairError, load_gold_pairs


def _write(tmp_path: Path, lines: list[dict[str, object]]) -> Path:
    path = tmp_path / "pairs.jsonl"
    path.write_text("".join(json.dumps(line) + "\n" for line in lines))
    return path


def test_loads_pairs_anchored_to_the_mention_universe(tmp_path: Path):
    path = _write(
        tmp_path,
        [
            {"left": "ego", "right": "the ego", "same": True},
            {"left": "fear", "right": "the fear of God", "same": False},
        ],
    )

    pairs = load_gold_pairs(path, ["ego", "the ego", "fear", "the fear of God"])

    assert pairs == [
        GoldPair("ego", "the ego", True),
        GoldPair("fear", "the fear of God", False),
    ]


def test_a_mention_not_in_the_universe_fails_loudly(tmp_path: Path):
    path = _write(tmp_path, [{"left": "ego", "right": "the id", "same": True}])

    with pytest.raises(GoldPairError, match="line 1"):
        load_gold_pairs(path, ["ego", "the ego"])


def test_non_boolean_same_fails(tmp_path: Path):
    path = _write(tmp_path, [{"left": "ego", "right": "the ego", "same": "yes"}])

    with pytest.raises(GoldPairError, match="line 1"):
        load_gold_pairs(path, ["ego", "the ego"])


def test_a_pair_naming_one_mention_twice_fails(tmp_path: Path):
    path = _write(tmp_path, [{"left": "ego", "right": "ego", "same": True}])

    with pytest.raises(GoldPairError, match="line 1"):
        load_gold_pairs(path, ["ego"])
