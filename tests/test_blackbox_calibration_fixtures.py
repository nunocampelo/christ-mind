from pathlib import Path

import pytest

from evaluation.blackbox.calibration.fixtures import (
    CriterionVerdict,
    Fixture,
    FixtureError,
    FrozenCase,
    dump_fixtures,
    load_fixtures,
    read_header,
)
from evaluation.blackbox.evaluator import BlackBoxResponse
from evaluation.blackbox.gold import load_cases
from mind_of_christ_agent.application.answer import CitationDiagnostics, CitedClaim

DEV_GOLD = Path("evaluation/blackbox/gold/cases.jsonl")


def _response() -> BlackBoxResponse:
    return BlackBoxResponse(
        question="q",
        answer="a",
        cited_claims=[
            CitedClaim(
                claim_id="c1",
                source_id="s1",
                subject="x",
                predicate="p",
                object="o",
                verb_phrase="vp",
                polarity="affirmed",
                evidence="clause",
                evidence_context="the clause sits in a paragraph",
            )
        ],
        inferred_chains=[],
        citation_diagnostics=CitationDiagnostics(),
    )


def _fixture(fid: str = "real-x") -> Fixture:
    case = load_cases(DEV_GOLD)[0]
    return Fixture(
        id=fid,
        role="real",
        split="tune",
        case=FrozenCase.of(case),
        response=_response(),
        verdicts={
            "semantic_grounding": CriterionVerdict(verdict="pass", reason="supported")
        },
        drafted_by="llm_judge (unapproved)",
        approved_by="reviewer",
    )


def test_frozen_case_round_trips_the_judge_visible_fields():
    case = load_cases(DEV_GOLD)[0]
    back = FrozenCase.of(case).to_case()
    assert back.id == case.id
    assert back.intent == case.intent
    assert back.corpus_reality == case.corpus_reality
    assert back.expected_behavior == case.expected_behavior
    assert back.prohibited_behavior == case.prohibited_behavior


def test_fixture_round_trips_the_full_source_paragraph(tmp_path: Path):
    path = tmp_path / "fx.jsonl"
    dump_fixtures([_fixture()], path)
    loaded = load_fixtures(path)
    assert [f.id for f in loaded] == ["real-x"]
    assert (
        loaded[0].response.cited_claims[0].evidence_context
        == "the clause sits in a paragraph"
    )
    assert loaded[0].verdicts["semantic_grounding"].verdict == "pass"


def test_loader_skips_a_header_line_and_read_header_returns_it(tmp_path: Path):
    path = tmp_path / "fx.jsonl"
    dump_fixtures([_fixture()], path)
    path.write_text('{"type": "header", "note": "drafted"}\n' + path.read_text())
    assert [f.id for f in load_fixtures(path)] == ["real-x"]
    assert read_header(path)["note"] == "drafted"


def test_duplicate_fixture_id_fails_loudly(tmp_path: Path):
    path = tmp_path / "fx.jsonl"
    dump_fixtures([_fixture("dup"), _fixture("dup")], path)
    with pytest.raises(FixtureError):
        load_fixtures(path)


def test_unknown_behaviour_token_fails_on_rehydrate(tmp_path: Path):
    bad = _fixture().model_copy(
        update={"case": _fixture().case.model_copy(update={"expected_behavior": ["nope"]})}
    )
    with pytest.raises(FixtureError):
        bad.case.to_case()
