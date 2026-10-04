"""Runs the fidelity scorer over the derived-gold split and records the run.

    python -m evaluation.claims.fidelity.run --oracle          # synthetic-fixture sanity
    python -m evaluation.claims.fidelity.run                   # dev split
    python -m evaluation.claims.fidelity.run --report          # reserved report split

Stage 1 is a scaffold: the gold passages are selected and frozen but UNAUTHORED, so a real
run scores nothing and the header reports coverage (authored / total). The oracle feeds a
nonempty synthetic fixture back as its own prediction, exercising the scorer end-to-end
without needing authored gold.
"""

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from domain.claims.models import Claim
from domain.derivation.models import (
    AuthoringStatus,
    DerivedEntry,
    DerivedGold,
    DerivedKind,
    ResolutionStatus,
)
from domain.derivation.serialization import DerivedGoldFile
from domain.sources.models import Source
from evaluation.claims.fidelity.fixtures import OracleCase, oracle_cases
from evaluation.claims.fidelity.score_fidelity import (
    DimensionScore,
    FidelityReport,
    Prediction,
    score_fidelity,
)
from evaluation.claims.gold import load_gold_claims
from evaluation.claims.score import ScoreReport
from infrastructure.database.sources_acim import list_acim_sources

GOLD_DIR = Path(__file__).parent / "gold"
RUNS_DIR = Path(__file__).parent / "runs"


class Split(StrEnum):
    DEV = "dev"
    REPORT = "report"


# Frozen before tuning. Hypotheses only -- derived layers stay UNAUTHORED until Stage 1b.
SPLIT_SOURCES: dict[Split, tuple[str, ...]] = {
    Split.DEV: ("t3-1-5", "t3-1-6", "t3-4-4", "t1-1-3", "t1-1-56"),
    Split.REPORT: ("t2-3-9", "t1-1-65", "t2-1-13", "t4-5-10"),
}


@dataclass(frozen=True)
class Coverage:
    authored: int
    total: int


def _load_gold(source_id: str) -> DerivedGold:
    path = GOLD_DIR / f"{source_id}.derived.json"
    return DerivedGoldFile.model_validate_json(path.read_text()).to_gold()


def _score_rate(score: DimensionScore) -> str:
    def fmt(value: float | None) -> str:
        return "n/a" if value is None else f"{value:.3f}"

    return (
        f"P {fmt(score.precision)}  R {fmt(score.recall)}  "
        f"(tp {score.true_positives}, fp {score.false_positives}, fn {score.false_negatives})"
    )


def _report_lines(report: FidelityReport) -> list[str]:
    c, r = report.condition, report.reference
    return [
        f"  variant        {report.chosen_variant_id}",
        f"  literal loose  {_score_rate_claim(report.literal)}",
        f"  qualification  {_score_rate(report.qualification)}",
        f"  requirement    {_score_rate(report.requirement)}",
        f"  description    {_score_rate(report.description)}",
        f"  condition      {_score_rate(c.presence)}",
        f"    content {c.content_matches}/{c.aligned}  scope {c.scope_matches}/{c.aligned}  "
        f"attachment {c.attachment_matches}/{c.aligned}",
        f"  reference      {_score_rate(r.presence)}",
        f"    referent {r.referent_matches}/{r.aligned}  abstention {r.abstention}  "
        f"unsupported_resolution {r.unsupported_resolution}",
        f"  unsupported inference  {report.unsupported}",
    ]


def _score_rate_claim(report: ScoreReport) -> str:
    s = report.loose
    return f"P {s.precision:.3f}  R {s.recall:.3f}  (tp {s.true_positives}, fp {s.false_positives})"


class OracleError(AssertionError):
    """Feeding gold back as its own prediction did not score perfectly -- a round-trip or
    scorer regression. Raised so the oracle command fails loudly instead of only printing."""


def _assert_perfect(
    case_name: str, report: FidelityReport, gold: DerivedGold, claims: Sequence[Claim]
) -> None:
    """Assert the self-prediction scores exactly as the gold structure demands -- expected
    counts are computed FROM the gold (how many entries of each kind, how many resolved vs
    unresolved references, how many literal claims), independent of the scorer's matching, so
    an accidentally empty or over-counting report cannot pass."""
    entries = _all_entries(gold)

    def fail(msg: str) -> None:
        raise OracleError(f"{case_name}: {msg}")

    def kind_count(kind: DerivedKind) -> int:
        return sum(e.kind is kind for e in entries)

    def check(name: str, score: DimensionScore, expected_items: int) -> None:
        if (score.true_positives, score.false_positives, score.false_negatives) != (
            expected_items,
            0,
            0,
        ):
            fail(f"{name} expected tp={expected_items}, fp=0, fn=0, got {score}")

    check("qualification", report.qualification, kind_count(DerivedKind.OCCURRENCE))
    check("requirement", report.requirement, kind_count(DerivedKind.REQUIREMENT))
    check("description", report.description, kind_count(DerivedKind.DESCRIPTION))
    check("condition", report.condition.presence, kind_count(DerivedKind.CONDITION))
    check("reference", report.reference.presence, kind_count(DerivedKind.RESOLVED_REFERENCE))

    conditions = kind_count(DerivedKind.CONDITION)
    c = report.condition
    if (c.content_matches, c.scope_matches, c.attachment_matches) != (
        conditions,
        conditions,
        conditions,
    ):
        fail(f"condition field counts not all {conditions}: {c}")

    resolved = sum(
        e.kind is DerivedKind.RESOLVED_REFERENCE and e.resolution is ResolutionStatus.RESOLVED
        for e in entries
    )
    unresolved = sum(
        e.kind is DerivedKind.RESOLVED_REFERENCE and e.resolution is ResolutionStatus.UNRESOLVED
        for e in entries
    )
    if report.reference.referent_matches != resolved:
        fail(f"reference referent_matches expected {resolved}, got {report.reference.referent_matches}")
    if report.reference.abstention != unresolved:
        fail(f"reference abstention expected {unresolved}, got {report.reference.abstention}")
    if report.reference.unsupported_resolution != 0:
        fail("self-prediction produced an unsupported resolution")

    if report.unsupported != 0:
        fail(f"unsupported inference should be 0, got {report.unsupported}")

    expected_claims = len(claims)
    for tier_name, tier in (
        ("loose", report.literal.loose),
        ("strict", report.literal.strict),
        ("relaxed", report.literal.relaxed),
    ):
        if (tier.true_positives, tier.false_positives, tier.false_negatives) != (
            expected_claims,
            0,
            0,
        ):
            fail(f"literal {tier_name} expected tp={expected_claims}, fp=0, fn=0, got {tier}")


def run_oracle(sources: Sequence[Source]) -> list[str]:
    by_id = {s.id: s for s in sources}
    lines = ["oracle (synthetic fixtures) -- feeding gold back as the prediction"]
    exercised: set[str] = set()
    for case in oracle_cases():
        source = by_id[case.source_id]
        prediction = Prediction(source_id=case.source_id, entries=_all_entries(case.gold))
        report = score_fidelity(
            predicted=prediction,
            predicted_claims=case.claims,
            gold=case.gold,
            gold_claims=case.claims,
            source=source,
        )
        _assert_perfect(case.name, report, case.gold, case.claims)
        exercised |= _exercised(case)
        lines.append(f"\n[{case.name}]")
        lines += _report_lines(report)

    required = {
        "occurrence",
        "requirement",
        "description",
        "condition",
        "referent",
        "abstention",
        "literal",
    }
    missing = required - exercised
    if missing:
        raise OracleError(f"oracle fixtures exercise no {sorted(missing)} items -- cannot vouch for them")

    lines.append("\noracle OK: every dimension exercised and perfect, abstention honoured")
    return lines


def _exercised(case: OracleCase) -> set[str]:
    seen: set[str] = set()
    for e in _all_entries(case.gold):
        if e.kind is DerivedKind.OCCURRENCE:
            seen.add("occurrence")
        elif e.kind is DerivedKind.REQUIREMENT:
            seen.add("requirement")
        elif e.kind is DerivedKind.DESCRIPTION:
            seen.add("description")
        elif e.kind is DerivedKind.CONDITION:
            seen.add("condition")
        elif e.kind is DerivedKind.RESOLVED_REFERENCE:
            seen.add("abstention" if e.resolution is ResolutionStatus.UNRESOLVED else "referent")
    if case.claims:
        seen.add("literal")
    return seen


def _all_entries(gold: DerivedGold) -> tuple[DerivedEntry, ...]:
    first = gold.variants[0].entries if gold.variants else ()
    return gold.shared + first


def _coverage(split: Split) -> Coverage:
    ids = SPLIT_SOURCES[split]
    authored = sum(
        _load_gold(sid).derived_status is AuthoringStatus.AUTHORED for sid in ids
    )
    return Coverage(authored=authored, total=len(ids))


def run_split(split: Split, sources: Sequence[Source]) -> list[str]:
    by_id = {s.id: s for s in sources}
    coverage = _coverage(split)
    lines = [f"split {split}: coverage {coverage.authored} authored / {coverage.total} total"]
    for source_id in SPLIT_SOURCES[split]:
        gold = _load_gold(source_id)
        if gold.derived_status is AuthoringStatus.UNAUTHORED:
            lines.append(f"  {source_id}: UNAUTHORED -- skipped (not scored)")
            continue
        source = by_id[source_id]
        gold_claims = load_gold_claims(GOLD_DIR / f"{source_id}.jsonl", sources)
        # A derived-only run with no deriver has no prediction yet; Stage 2 wires one in.
        prediction = Prediction(source_id=source_id)
        report = score_fidelity(prediction, (), gold, gold_claims, source)
        lines.append(f"\n  {source_id}:")
        lines += [f"  {line}" for line in _report_lines(report)]
    return lines


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Score a derived layer against the fidelity gold.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--oracle", action="store_true", help="synthetic-fixture sanity check")
    group.add_argument(
        "--report", action="store_true", help="score the reserved report split; not for tuning"
    )
    args = parser.parse_args(argv)

    sources = list_acim_sources()

    if args.oracle:
        lines = run_oracle(sources)
    else:
        lines = run_split(Split.REPORT if args.report else Split.DEV, sources)

    summary = "\n".join(lines)
    print(summary)

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    (RUNS_DIR / f"{run_id}.txt").write_text(summary + "\n")


if __name__ == "__main__":
    main()
