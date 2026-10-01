"""Frozen calibration fixtures: a judged answer paired with a human-approved verdict.

A fixture pins everything the judge sees (the case fields it reads + the full frozen
`BlackBoxResponse`, including each claim's source paragraph) alongside a per-criterion human
verdict with an evidence-based reason. Re-judging a fixture therefore measures the judge, not
answer drift. Controls are fixtures derived by a single minimal edit of a real frozen answer
(`derived_from` + `edit` record the baseline and the one change), so a judge disagreement is
attributable to that edit. The committed verdict is the human-approved one; `drafted_by`
records what proposed it before approval.
"""

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from evaluation.blackbox.evaluator import BlackBoxResponse
from evaluation.blackbox.gold import (
    BEHAVIOR_VOCABULARY,
    CORPUS_REALITIES,
    BlackBoxCase,
)

Verdict = Literal["pass", "fail", "not_applicable"]


class CriterionVerdict(BaseModel):
    model_config = {"frozen": True}
    verdict: Verdict
    reason: str


class FrozenCase(BaseModel):
    """The subset of `BlackBoxCase` the judge reads, in a serializable form. The judge never
    sees `must_include_*`/`may_include_*` (those gate the deterministic evaluator, not the
    judge), so a fixture need not carry them."""

    model_config = {"frozen": True}
    id: str
    question: str
    intent: str
    corpus_reality: str
    expected_behavior: list[str]
    prohibited_behavior: list[str]

    @classmethod
    def of(cls, case: BlackBoxCase) -> "FrozenCase":
        return cls(
            id=case.id,
            question=case.question,
            intent=case.intent,
            corpus_reality=case.corpus_reality,
            expected_behavior=sorted(case.expected_behavior),
            prohibited_behavior=sorted(case.prohibited_behavior),
        )

    def to_case(self) -> BlackBoxCase:
        if self.corpus_reality not in CORPUS_REALITIES:
            raise FixtureError("fixture carries an unknown corpus_reality")
        expected = frozenset(self.expected_behavior)
        prohibited = frozenset(self.prohibited_behavior)
        if (expected | prohibited) - BEHAVIOR_VOCABULARY:
            raise FixtureError("fixture carries an unknown behaviour token")
        empty: frozenset[str] = frozenset()
        return BlackBoxCase(
            id=self.id,
            question=self.question,
            intent=self.intent,
            corpus_reality=self.corpus_reality,
            expected_behavior=expected,
            prohibited_behavior=prohibited,
            must_include_source_ids=empty,
            must_include_any_source_ids=empty,
            may_include_source_ids=empty,
            must_include_claim_ids=empty,
            must_include_any_claim_ids=empty,
            may_include_claim_ids=empty,
        )


class Derivation(BaseModel):
    """How a control was made: the baseline fixture id and the single minimal edit applied."""

    model_config = {"frozen": True}
    derived_from: str
    edit: str


class Fixture(BaseModel):
    model_config = {"frozen": True}
    id: str
    role: Literal["real", "positive_control", "negative_control"]
    split: Literal["tune", "holdout"]
    case: FrozenCase
    response: BlackBoxResponse
    verdicts: dict[str, CriterionVerdict]
    derivation: Derivation | None = None
    drafted_by: str = ""
    approved_by: str = ""


class FixtureError(ValueError):
    """A fixtures file is malformed. Message is static: a fixture can carry answer text and
    source paragraphs, so the offending content is never interpolated into the error."""


def load_fixtures(path: Path) -> list[Fixture]:
    fixtures: list[Fixture] = []
    seen: set[str] = set()
    for line_number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        if _is_header(line):
            continue
        try:
            fixture = Fixture.model_validate_json(line)
        except ValueError as e:
            raise FixtureError(f"invalid fixture on line {line_number}") from e
        if fixture.id in seen:
            raise FixtureError(f"duplicate fixture id on line {line_number}")
        seen.add(fixture.id)
        fixtures.append(fixture)
    return fixtures


def dump_fixtures(
    fixtures: list[Fixture], path: Path, header: dict[str, object] | None = None
) -> None:
    with path.open("w") as f:
        if header is not None:
            f.write(json.dumps({"type": "header", **header}) + "\n")
        for fixture in fixtures:
            f.write(fixture.model_dump_json() + "\n")


def read_header(path: Path) -> dict[str, object]:
    """Fixture files may carry a leading `{"type":"header",...}` line of provenance; return it
    if present, else an empty dict."""
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        if isinstance(obj, dict) and obj.get("type") == "header":
            return obj
        return {}
    return {}


def _is_header(line: str) -> bool:
    obj = json.loads(line)
    return isinstance(obj, dict) and obj.get("type") == "header"
