"""Typed, persistable run records for the fidelity harness, and the readable rendering of
them. Kept out of `run.py` so the structured shape (what the `.json` artifact holds) is
defined once as pydantic models -- never a loose `dict` -- and the `.txt` summary is derived
from the same records the `.json` serializes, so the two can't drift.

A layer's result is one of three explicitly distinct states, never conflated:
`UNAUTHORED` (the gold is a placeholder), `NOT_RUN` (gold authored but no prediction was
supplied -- absent input, not a measured all-missing model output), and `SCORED` (authored
gold scored against a real prediction, including an authored-empty gold scored against an
invented prediction, which legitimately yields false positives).
"""

from enum import StrEnum

from pydantic import BaseModel

from evaluation.claims.fidelity.score_fidelity import (
    ConditionScore,
    DimensionScore,
    FidelityReport,
    ReferenceScore,
)
from evaluation.claims.score import ClaimScore, ScoreReport


class LayerState(StrEnum):
    UNAUTHORED = "unauthored"
    NOT_RUN = "not_run"
    SCORED = "scored"


class DimensionLine(BaseModel):
    """A dimension's counts with precision/recall carried as `float | None` so an absent
    denominator serializes as JSON null (rendered `n/a`), kept distinct from a real 0.0."""

    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float | None
    recall: float | None

    @classmethod
    def of(cls, score: DimensionScore) -> "DimensionLine":
        return cls(
            true_positives=score.true_positives,
            false_positives=score.false_positives,
            false_negatives=score.false_negatives,
            precision=score.precision,
            recall=score.recall,
        )


class ClaimTier(BaseModel):
    true_positives: int
    false_positives: int
    false_negatives: int
    precision: float | None
    recall: float | None

    @classmethod
    def of(cls, score: ClaimScore) -> "ClaimTier":
        predicted = score.true_positives + score.false_positives
        expected = score.true_positives + score.false_negatives
        return cls(
            true_positives=score.true_positives,
            false_positives=score.false_positives,
            false_negatives=score.false_negatives,
            precision=score.true_positives / predicted if predicted else None,
            recall=score.true_positives / expected if expected else None,
        )


class LiteralReport(BaseModel):
    """The complete literal tier. `strict` is the primary accuracy metric; `loose` and
    `relaxed` are diagnostics, and the mismatch counts attribute the loose-strict gap."""

    loose: ClaimTier
    strict: ClaimTier
    relaxed: ClaimTier
    polarity_mismatches: int
    mode_mismatches: int
    attribution_mismatches: int

    @classmethod
    def of(cls, report: ScoreReport) -> "LiteralReport":
        return cls(
            loose=ClaimTier.of(report.loose),
            strict=ClaimTier.of(report.strict),
            relaxed=ClaimTier.of(report.relaxed),
            polarity_mismatches=report.polarity_mismatches,
            mode_mismatches=report.mode_mismatches,
            attribution_mismatches=report.attribution_mismatches,
        )


class ConditionReport(BaseModel):
    presence: DimensionLine
    content_matches: int
    scope_matches: int
    attachment_matches: int
    aligned: int
    fully_correct: int

    @classmethod
    def of(cls, score: ConditionScore) -> "ConditionReport":
        return cls(
            presence=DimensionLine.of(score.presence),
            content_matches=score.content_matches,
            scope_matches=score.scope_matches,
            attachment_matches=score.attachment_matches,
            aligned=score.aligned,
            fully_correct=score.fully_correct,
        )


class ReferenceReport(BaseModel):
    presence: DimensionLine
    referent_matches: int
    aligned: int
    abstention: int
    unsupported_resolution: int
    fully_correct: int

    @classmethod
    def of(cls, score: ReferenceScore) -> "ReferenceReport":
        return cls(
            presence=DimensionLine.of(score.presence),
            referent_matches=score.referent_matches,
            aligned=score.aligned,
            abstention=score.abstention,
            unsupported_resolution=score.unsupported_resolution,
            fully_correct=score.fully_correct,
        )


class DerivedReport(BaseModel):
    chosen_variant_id: str | None
    qualification: DimensionLine
    requirement: DimensionLine
    description: DimensionLine
    condition: ConditionReport
    reference: ReferenceReport
    unsupported: int

    @classmethod
    def of(cls, report: FidelityReport) -> "DerivedReport":
        return cls(
            chosen_variant_id=report.chosen_variant_id,
            qualification=DimensionLine.of(report.qualification),
            requirement=DimensionLine.of(report.requirement),
            description=DimensionLine.of(report.description),
            condition=ConditionReport.of(report.condition),
            reference=ReferenceReport.of(report.reference),
            unsupported=report.unsupported,
        )


class SourceRun(BaseModel):
    """One passage's result. `literal_state`/`derived_state` are independent -- a passage can
    have a SCORED literal layer and an UNAUTHORED derived one, or vice versa. A report is
    present only for a SCORED layer; the other two states carry no numbers to avoid reading a
    placeholder or an absent prediction as a measured zero."""

    source_id: str
    literal_state: LayerState
    derived_state: LayerState
    literal: LiteralReport | None = None
    derived: DerivedReport | None = None


class LayerCoverage(BaseModel):
    authored: int
    total: int


class RunRecord(BaseModel):
    schema_version: int
    split: str
    literal_coverage: LayerCoverage
    derived_coverage: LayerCoverage
    sources: list[SourceRun] = []


def _rate(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def _dimension_rate(line: DimensionLine) -> str:
    return (
        f"P {_rate(line.precision)}  R {_rate(line.recall)}  "
        f"(tp {line.true_positives}, fp {line.false_positives}, fn {line.false_negatives})"
    )


def _claim_tier(line: ClaimTier) -> str:
    return (
        f"P {_rate(line.precision)}  R {_rate(line.recall)}  "
        f"(tp {line.true_positives}, fp {line.false_positives}, fn {line.false_negatives})"
    )


def literal_lines(report: LiteralReport) -> list[str]:
    return [
        f"  literal strict (primary)  {_claim_tier(report.strict)}",
        f"  literal loose             {_claim_tier(report.loose)}",
        f"  literal relaxed (diag)    {_claim_tier(report.relaxed)}",
        f"    mismatches  polarity {report.polarity_mismatches}  mode {report.mode_mismatches}  "
        f"attribution {report.attribution_mismatches}",
    ]


def derived_lines(report: DerivedReport) -> list[str]:
    c, r = report.condition, report.reference
    return [
        f"  variant        {report.chosen_variant_id}",
        f"  qualification  {_dimension_rate(report.qualification)}",
        f"  requirement    {_dimension_rate(report.requirement)}",
        f"  description    {_dimension_rate(report.description)}",
        f"  condition      {_dimension_rate(c.presence)}",
        f"    content {c.content_matches}/{c.aligned}  scope {c.scope_matches}/{c.aligned}  "
        f"attachment {c.attachment_matches}/{c.aligned}",
        f"  reference      {_dimension_rate(r.presence)}",
        f"    referent {r.referent_matches}/{r.aligned}  abstention {r.abstention}  "
        f"unsupported_resolution {r.unsupported_resolution}",
        f"  unsupported inference  {report.unsupported}",
    ]


def source_lines(run: SourceRun) -> list[str]:
    lines = [f"\n  {run.source_id}:  literal {run.literal_state}  derived {run.derived_state}"]
    if run.literal is not None:
        lines += literal_lines(run.literal)
    if run.derived is not None:
        lines += derived_lines(run.derived)
    return lines


def run_lines(record: RunRecord) -> list[str]:
    lc, dc = record.literal_coverage, record.derived_coverage
    lines = [
        f"split {record.split}: "
        f"literal {lc.authored}/{lc.total} authored, derived {dc.authored}/{dc.total} authored",
    ]
    for run in record.sources:
        lines += source_lines(run)
    return lines
