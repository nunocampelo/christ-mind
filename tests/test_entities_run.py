import json
from datetime import UTC, datetime
from pathlib import Path

import evaluation.entities.run as run_module
from evaluation.entities.gold import GoldPair
from evaluation.entities.run import LexicalBaseline, run
from domain.entities.serialization import EntityLine
from evaluation.entities.run_format import ResolutionHeader

GOLD = [
    GoldPair("ego", "the ego", same=True),  # normalise-equal -> merged, tp
    GoldPair("God's Will", "Will of God", same=True),  # not equal -> apart, fn
    GoldPair("God", "Son of God", same=False),  # not equal -> apart, ok
]


def _run(record: bool, all_mentions: list[str]):
    return run(
        resolver=LexicalBaseline(),
        resolver_name="baseline",
        resolver_prompt_version=None,
        gold=GOLD,
        all_mentions=all_mentions,
        record=record,
        now=datetime(2026, 9, 24, tzinfo=UTC),
    )


def test_baseline_scores_normalised_equal_pairs_only():
    outcome = _run(record=False, all_mentions=[])

    assert outcome.report.score.true_positives == 1
    assert outcome.report.score.false_negatives == 1
    assert outcome.report.score.false_positives == 0
    assert outcome.path is None


def test_unscored_run_resolves_only_the_gold_mentions_when_not_recording():
    # When not recording, all_mentions is ignored: only the gold's own mentions are
    # resolved, so an unrelated corpus form never enters the partition.
    outcome = _run(record=False, all_mentions=["something unrelated"])
    resolved = {m for e in outcome.result.entities for m in e.mentions}

    assert "something unrelated" not in resolved
    assert "ego" in resolved


def test_record_writes_a_readable_run_file(tmp_path: Path, monkeypatch):
    corpus = tmp_path / "corpus.jsonl"
    corpus.write_text(
        json.dumps({"type": "header", "run_id": "SRC", "passages_sha256": "abc"})
        + "\n"
    )
    monkeypatch.setattr(run_module, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(run_module, "CORPUS_RUN", corpus)

    # The whole universe is resolved when recording; the gold subset is still scored.
    outcome = _run(record=True, all_mentions=["ego", "the ego", "fear", "mind"])

    assert outcome.path is not None
    lines = outcome.path.read_text().splitlines()
    header = ResolutionHeader.model_validate_json(lines[0])
    entities = [EntityLine.model_validate_json(line) for line in lines[1:]]

    assert header.source_run_id == "SRC"
    assert header.passages_sha256 == "abc"
    assert header.resolver == "baseline"
    assert header.entities == len(entities)
    assert header.score is not None and header.score.true_positives == 1
    # "ego"/"the ego" merged by the baseline; "fear" and "mind" are singletons.
    members = {frozenset(e.mentions) for e in entities}
    assert frozenset({"ego", "the ego"}) in members
    assert frozenset({"fear"}) in members
