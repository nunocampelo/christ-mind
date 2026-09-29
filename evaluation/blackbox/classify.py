"""A/B/C failure classifier: turns the aggregate `19/21 passing` into an actionable
split -- how many failures are ranking-recoverable, how many are beyond lexical
reach, how many are synthesis. See `reachability.py` for the static probe this
combines with the run's retrieval trace.

    A -- lexically reachable, but this run's retrieval missed it (mapper/ranking)
    B -- not lexically reachable by any plausible query (beyond-lexical)
    C -- retrieved, but the answer never marker-cited it (synthesis)

B does NOT mean "embeddings will fix it" -- that is a separate hypothesis the
classifier never encodes. The hybrid-retrieval experiment (see plan
`hybrid-retrieval-semantic-channel.md`) showed B sub-splits into B1
semantic-recoverable (embeddings reach the evidence) and B2 graph/relational
(embeddings cannot, at any rank). That sub-split is a probe-derived diagnostic
layered ON TOP of this classifier, deliberately NOT computed here: distinguishing
B1 from B2 requires running the embedding model, and the eval must stay
model-independent and deterministic. Keep B meaning exactly "beyond lexical".

The classifier is advisory: it never flips a case's verdict, only annotates why a
required id was missing. A case with no `must_include_*` evidence yields
`not_evaluated`. A case where every required id was retrieved yields `pass` with
an empty detail. A case with unsatisfied ids yields `pass` with a compact detail
like `"A[cid1]; B[cid2,cid3]; C[cid4]"` -- the deterministic evaluator's
`required_evidence_present` is what gates the case, this one only explains it.

`response.cited_claims` doubles as the retrieval trace today: the orchestrator's
`_absorb` appends every claim from every tool call, whether the model marker-cites
it or not (see the invariant comment there). If that contract shifts, the
classifier must switch to an explicit retrieved-claims field on the answer, or C
cases will be misread as B/A.
"""

from evaluation.blackbox.evaluator import BlackBoxResponse, CriterionResult
from evaluation.blackbox.gold import BlackBoxCase
from evaluation.blackbox.reachability import (
    REACHABILITY_VERSION,
    is_lexically_reachable,
)


class FailureClassificationEvaluator:
    name = "failure_classification"

    def evaluate(
        self, case: BlackBoxCase, response: BlackBoxResponse
    ) -> list[CriterionResult]:
        required_ids = case.must_include_claim_ids | case.must_include_any_claim_ids
        if not required_ids:
            return [
                CriterionResult(
                    name="failure_classification",
                    kind="advisory",
                    status="not_evaluated",
                    detail="case names no required claim-level evidence",
                )
            ]

        retrieved = {c.claim_id for c in response.cited_claims}

        # `must_include_any` is satisfied by ANY of its ids being retrieved, so the
        # unsatisfied count treats the whole group as one required item that either
        # was or wasn't reached. `must_include` is per-id.
        unsatisfied: list[tuple[str, str]] = []  # (claim_id, class)
        for cid in sorted(case.must_include_claim_ids - retrieved):
            unsatisfied.append((cid, self._classify_missing(cid, case)))
        if case.must_include_any_claim_ids and not (
            case.must_include_any_claim_ids & retrieved
        ):
            for cid in sorted(case.must_include_any_claim_ids):
                unsatisfied.append((cid, self._classify_missing(cid, case)))

        # C: retrieved but the answer never marker-cited it. Only reported for the
        # strict `must_include_claim_ids` -- for `must_include_any`, the group is
        # satisfied as soon as one is retrieved and the specific id the prose leans
        # on is a synthesis choice, not a failure.
        c_ids = sorted(
            case.must_include_claim_ids
            & retrieved
            & set(response.citation_diagnostics.unused_claim_ids)
        )

        return [
            CriterionResult(
                name="failure_classification",
                kind="advisory",
                status="pass",
                detail=_format_detail(unsatisfied, c_ids),
            )
        ]

    def _classify_missing(self, claim_id: str, case: BlackBoxCase) -> str:
        return "A" if is_lexically_reachable(claim_id, case.question) else "B"


def _format_detail(unsatisfied: list[tuple[str, str]], c_ids: list[str]) -> str:
    if not unsatisfied and not c_ids:
        return f"v{REACHABILITY_VERSION}: all required evidence retrieved and cited"
    parts: list[str] = [f"v{REACHABILITY_VERSION}"]
    by_class: dict[str, list[str]] = {"A": [], "B": []}
    for cid, cls in unsatisfied:
        by_class[cls].append(cid)
    for cls in ("A", "B"):
        if by_class[cls]:
            parts.append(f"{cls}[{','.join(by_class[cls])}]")
    if c_ids:
        parts.append(f"C[{','.join(c_ids)}]")
    return " ".join(parts)


def make_failure_classification() -> FailureClassificationEvaluator:
    return FailureClassificationEvaluator()
