"""Aggregates per-case results into a run report. The headline is the gating pass rate
(the regression gate); advisory criteria are summarized separately, never folded into a
single quality number. Breakdowns by intent and by criterion make a run comparable to the
next one at the granularity that matters -- which *category* moved, not just the total.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from evaluation.blackbox.evaluator import CaseResult


@dataclass(frozen=True)
class BlackBoxReport:
    per_case: tuple[CaseResult, ...]

    @property
    def total(self) -> int:
        return len(self.per_case)

    @property
    def passed(self) -> int:
        return sum(1 for c in self.per_case if c.status == "pass")

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0

    def pass_rate_by_intent(self, intents: Sequence[str]) -> dict[str, tuple[int, int]]:
        """intent -> (passed, total). `intents` is aligned with `per_case` (a case carries
        no intent itself -- it comes from the gold case), so the caller zips them."""
        buckets: dict[str, list[int]] = {}
        for case, intent in zip(self.per_case, intents):
            passed, total = buckets.setdefault(intent, [0, 0])
            buckets[intent] = [passed + (case.status == "pass"), total + 1]
        return {intent: (p, t) for intent, (p, t) in buckets.items()}

    def advisory_means(self) -> dict[str, float]:
        """criterion name -> mean of its scored advisory results across cases (criteria
        that were `not_evaluated` or carry no score are excluded from their own mean)."""
        sums: dict[str, list[float]] = {}
        for case in self.per_case:
            for c in case.criteria:
                if c.kind == "advisory" and c.score is not None:
                    sums.setdefault(c.name, []).append(c.score)
        return {name: sum(vs) / len(vs) for name, vs in sums.items() if vs}


def score_cases(results: Sequence[CaseResult]) -> BlackBoxReport:
    return BlackBoxReport(per_case=tuple(results))
