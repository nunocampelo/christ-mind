"""Calibration harness: validate the LLM judge against human-approved verdicts.

Re-judges each FROZEN fixture `--repeats` times and joins the judge's pass/fail against the
fixture's human verdict, per criterion. Reports false positives (judge pass, human fail),
false negatives (judge fail, human pass), parse failures (`not_evaluated`), and stability --
how often the judge's own verdict flips across repeats of the SAME fixture, plus the mean
within-fixture score spread. The judge needs no live stack (it only completes against the
fixtures), so this runs without Docker/Postgres, unlike `capture_flagged.py`.

Only the requested split is evaluated, and it defaults to `tune`: the `holdout` split must be
asked for explicitly (`--holdout`), so its numbers aren't exposed while a rubric is being
tuned. A real fixture and the controls derived from it must share a split (checked at load),
so an edit of a tuning answer never leaks into holdout. Keep every criterion advisory until
this validation says which, with what threshold and failure policy, is safe to graduate.

Run from the repo root:
    .venv/bin/python -m evaluation.blackbox.calibration.run --fixtures <path.jsonl>
    .venv/bin/python -m evaluation.blackbox.calibration.run --fixtures <path.jsonl> --holdout
"""

import argparse
import hashlib
import json
import statistics
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from infrastructure.config.env import load_env
from pydantic import BaseModel

from evaluation.blackbox.calibration.fixtures import Fixture, load_fixtures, read_header
from evaluation.blackbox.evaluator import Evaluator
from evaluation.blackbox.llm_judge import (
    PASS_THRESHOLD,
    PROMPT_VERSION,
    make_llm_judge,
    prompt_hash,
)
from evaluation.blackbox.run import _resolve_model

_RESULTS_DIR = Path(__file__).resolve().parent / "results"


class TrialOutcome(BaseModel):
    """One criterion's result on one repeat of one fixture, kept so a reviewer can see exactly
    which trials disagreed rather than only the aggregate."""

    model_config = {"frozen": True}
    fixture_id: str
    criterion: str
    human: str
    judge_status: str
    judge_score: float | None
    # The judge's typed reason when judge_status is not_evaluated, so a reviewer sees WHY a
    # judgment was unavailable (provider vs parse vs incomplete coverage) rather than only that
    # it was. Empty for a real pass/fail, or for an out-of-scope not_evaluated with no reason.
    failure_reason: str = ""


class CriterionStats(BaseModel):
    model_config = {"frozen": True}
    judged: int
    agree: int
    false_positive: int
    false_negative: int
    # The causes of an unavailable judgment, kept separate so a before/after comparison isn't
    # confounded by lumping a flaky provider call in with a malformed reply or incomplete
    # grounding coverage. `parse_failure` also absorbs a missing scalar field (reply came back,
    # field absent). `unscored` is a not_evaluated the judge raised DELIBERATELY with no failure
    # reason -- an out-of-scope criterion (premature_abstention off `sufficient`) or nothing to
    # ground -- not a failure at all; separated so it never inflates parse_failure. None of
    # these counts as a false positive or negative.
    provider_failure: int
    parse_failure: int
    incomplete_coverage: int
    unscored: int
    agreement_rate: float | None
    # Stability is WITHIN a fixture across repeats, never pooled across fixtures (different
    # fixtures legitimately get different scores -- pooling their spread measures the fixtures,
    # not the judge). `verdict_flips` counts fixtures whose judge status was not identical on
    # every repeat; `mean_within_fixture_stdev` averages each fixture's own score stdev.
    verdict_flips: int
    fixtures_with_multiple_repeats: int
    mean_within_fixture_stdev: float | None


class SplitReport(BaseModel):
    model_config = {"frozen": True}
    split: str
    fixtures: int
    repeats: int
    criteria: dict[str, CriterionStats]
    trials: list[TrialOutcome]


def _evaluate(
    judge: Evaluator, fixtures: list[Fixture], repeats: int
) -> tuple[dict[str, CriterionStats], list[TrialOutcome]]:
    fp: Counter[str] = Counter()
    fn: Counter[str] = Counter()
    agree: Counter[str] = Counter()
    provider_fail: Counter[str] = Counter()
    parse_fail: Counter[str] = Counter()
    incomplete: Counter[str] = Counter()
    unscored: Counter[str] = Counter()
    judged: Counter[str] = Counter()
    # Per (criterion, fixture): the judge statuses and scores seen across repeats.
    per_fixture_status: dict[str, dict[str, list[str]]] = {}
    per_fixture_scores: dict[str, dict[str, list[float]]] = {}
    trials: list[TrialOutcome] = []

    for fixture in fixtures:
        case = fixture.case.to_case()
        for _ in range(repeats):
            for result in judge.evaluate(case, fixture.response):
                human = fixture.verdicts.get(result.name)
                if human is None or human.verdict == "not_applicable":
                    continue
                judged[result.name] += 1
                trials.append(
                    TrialOutcome(
                        fixture_id=fixture.id,
                        criterion=result.name,
                        human=human.verdict,
                        judge_status=result.status,
                        judge_score=result.score,
                        failure_reason=result.failure_reason or "",
                    )
                )
                per_fixture_status.setdefault(result.name, {}).setdefault(
                    fixture.id, []
                ).append(result.status)
                if result.score is not None:
                    per_fixture_scores.setdefault(result.name, {}).setdefault(
                        fixture.id, []
                    ).append(result.score)
                if result.status == "not_evaluated":
                    if result.failure_reason == "provider_failure":
                        provider_fail[result.name] += 1
                    elif result.failure_reason == "incomplete_coverage":
                        incomplete[result.name] += 1
                    elif result.failure_reason == "parse_failure":
                        parse_fail[result.name] += 1
                    else:
                        unscored[result.name] += 1
                elif result.status == human.verdict:
                    agree[result.name] += 1
                elif result.status == "pass" and human.verdict == "fail":
                    fp[result.name] += 1
                else:
                    fn[result.name] += 1

    report: dict[str, CriterionStats] = {}
    for name in sorted(judged):
        n = judged[name]
        statuses = per_fixture_status.get(name, {})
        flips = sum(1 for s in statuses.values() if len(set(s)) > 1)
        multi = {
            fid: scores
            for fid, scores in per_fixture_scores.get(name, {}).items()
            if len(scores) > 1
        }
        within = [statistics.pstdev(scores) for scores in multi.values()]
        report[name] = CriterionStats(
            judged=n,
            agree=agree[name],
            false_positive=fp[name],
            false_negative=fn[name],
            provider_failure=provider_fail[name],
            parse_failure=parse_fail[name],
            incomplete_coverage=incomplete[name],
            unscored=unscored[name],
            agreement_rate=round(agree[name] / n, 3) if n else None,
            verdict_flips=flips,
            fixtures_with_multiple_repeats=len(multi),
            mean_within_fixture_stdev=(
                round(statistics.fmean(within), 3) if within else None
            ),
        )
    return report, trials


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", required=True, type=Path, help="fixtures JSONL")
    parser.add_argument(
        "--holdout",
        action="store_true",
        help="evaluate the holdout split instead of tune (default)",
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=5,
        help="times to re-judge each frozen fixture (stability sample)",
    )
    args = parser.parse_args()

    load_env()
    fixtures = load_fixtures(args.fixtures)
    _reject_unapproved(fixtures)
    _reject_split_leakage(fixtures)

    split = "holdout" if args.holdout else "tune"
    subset = [f for f in fixtures if f.split == split]
    if not subset:
        raise SystemExit(f"no fixtures in the {split!r} split")

    judge = make_llm_judge()
    criteria, trials = _evaluate(judge, subset, args.repeats)
    report = SplitReport(
        split=split,
        fixtures=len(subset),
        repeats=args.repeats,
        criteria=criteria,
        trials=trials,
    )

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    header = {
        "type": "header",
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "judge_model": _resolve_model(),
        "judge_prompt_version": PROMPT_VERSION,
        "judge_prompt_hash": prompt_hash(),
        "pass_threshold": PASS_THRESHOLD,
        "fixtures_file": args.fixtures.name,
        "fixtures_sha256": hashlib.sha256(args.fixtures.read_bytes()).hexdigest(),
        "fixtures_header": read_header(args.fixtures),
        "split": split,
        "repeats": args.repeats,
    }

    _RESULTS_DIR.mkdir(exist_ok=True)
    out = _RESULTS_DIR / f"{run_id}.jsonl"
    with out.open("w") as f:
        f.write(json.dumps(header) + "\n")
        f.write(report.model_dump_json() + "\n")

    print(f"\n[{split}] {report.fixtures} fixtures x {args.repeats} repeats")
    for name, stats in report.criteria.items():
        print(
            f"  {name}: judged {stats.judged} agree {stats.agreement_rate} "
            f"FP {stats.false_positive} FN {stats.false_negative} "
            f"provider_fail {stats.provider_failure} parse_fail {stats.parse_failure} "
            f"incomplete {stats.incomplete_coverage} unscored {stats.unscored} "
            f"flips {stats.verdict_flips} "
            f"within_stdev {stats.mean_within_fixture_stdev}"
        )
    print(f"\nwrote {out}")


def _reject_unapproved(fixtures: list[Fixture]) -> None:
    """Draft fixtures carry verdicts proposed by the judge under test; scoring the judge
    against its own unreviewed proposals is circular. Fail loud before any judge call."""
    unapproved = [f.id for f in fixtures if not f.approved_by.strip()]
    if unapproved:
        raise SystemExit(
            f"{len(unapproved)} fixture(s) lack approved_by (unreviewed drafts); "
            f"approve them before calibrating: {unapproved}"
        )


def _reject_split_leakage(fixtures: list[Fixture]) -> None:
    """A control and the real fixture it was edited from must share a split, or tuning on one
    leaks into the other's reported reliability."""
    split_of = {f.id: f.split for f in fixtures}
    leaked = [
        f.id
        for f in fixtures
        if f.derivation is not None
        and split_of.get(f.derivation.derived_from) not in (None, f.split)
    ]
    if leaked:
        raise SystemExit(
            f"{len(leaked)} control(s) are in a different split than their baseline "
            f"(split leakage): {leaked}"
        )


if __name__ == "__main__":
    main()
