from pathlib import Path

import pytest

from evaluation.blackbox.gold import (
    BlackBoxCaseError,
    load_cases,
)

DEV_GOLD = Path("evaluation/blackbox/gold/cases.jsonl")
HOLDOUT_GOLD = Path("evaluation/blackbox/gold/cases_holdout.jsonl")


def test_committed_gold_loads():
    dev = load_cases(DEV_GOLD)
    holdout = load_cases(HOLDOUT_GOLD)
    assert len(dev) >= 12
    assert holdout
    ids = [c.id for c in dev + holdout]
    assert len(ids) == len(set(ids))


def test_outside_cases_expect_no_required_evidence():
    for case in load_cases(DEV_GOLD) + load_cases(HOLDOUT_GOLD):
        if case.corpus_reality == "outside":
            assert not case.must_include_source_ids
            assert not case.must_include_claim_ids


@pytest.mark.parametrize(
    "line",
    [
        '{"question": "q", "intent": "x", "corpus_reality": "adequate"}',
        '{"id": "a", "intent": "x", "corpus_reality": "adequate"}',
        '{"id": "", "question": "q", "intent": "x", "corpus_reality": "adequate"}',
        '{"id": "a", "question": "q", "intent": "x", "corpus_reality": "elsewhere"}',
        '{"id": "a", "question": "q", "intent": "x", "corpus_reality": "adequate", "expected_behavior": ["not_a_real_token"]}',
        '{"id": "a", "question": "q", "intent": "x", "corpus_reality": "adequate", "must_include_source_ids": "t1-0-1"}',
    ],
)
def test_malformed_case_fails_loudly(tmp_path: Path, line: str):
    path = tmp_path / "cases.jsonl"
    path.write_text(line + "\n")
    with pytest.raises(BlackBoxCaseError):
        load_cases(path)


def test_duplicate_id_fails(tmp_path: Path):
    good = '{"id": "dup", "question": "q", "intent": "x", "corpus_reality": "adequate"}'
    path = tmp_path / "cases.jsonl"
    path.write_text(good + "\n" + good + "\n")
    with pytest.raises(BlackBoxCaseError):
        load_cases(path)
