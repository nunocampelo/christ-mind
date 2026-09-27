"""The deterministic, gating evaluator: the categorical invariants the corpus makes
objective, so an invented citation fails outright regardless of how good the prose reads.

Deliberately excludes semantic grounding ("does this passage actually support the claim") --
that is a judgment, and lives with the LLM judge as an advisory criterion. What is here is
only what code can decide alone: markers resolve, cited sources exist, no duplicates, the
answer isn't empty, and (when a case names required evidence) that evidence was surfaced.
"""

from evaluation.blackbox.evaluator import BlackBoxResponse, CriterionResult
from evaluation.blackbox.gold import BlackBoxCase
from infrastructure.database.claims import list_claims

_CORPUS_SOURCE_IDS = frozenset(claim.source_id for claim in list_claims())


def _gating(name: str, ok: bool, detail: str = "") -> CriterionResult:
    return CriterionResult(
        name=name, kind="gating", status="pass" if ok else "fail", detail=detail
    )


class DeterministicEvaluator:
    name = "deterministic"

    def evaluate(
        self, case: BlackBoxCase, response: BlackBoxResponse
    ) -> list[CriterionResult]:
        return [
            self._non_empty(response),
            self._citation_integrity(response),
            self._required_source_present(case, response),
        ]

    def _non_empty(self, response: BlackBoxResponse) -> CriterionResult:
        return _gating("non_empty", bool(response.answer.strip()), "answer is empty")

    def _citation_integrity(self, response: BlackBoxResponse) -> CriterionResult:
        fabricated = response.citation_diagnostics.unknown_ids
        cited_ids = [c.claim_id for c in response.cited_claims]
        duplicated = sorted({cid for cid in cited_ids if cited_ids.count(cid) > 1})
        unresolved = sorted(
            {
                c.source_id
                for c in response.cited_claims
                if c.source_id not in _CORPUS_SOURCE_IDS
            }
        )
        problems: list[str] = []
        if fabricated:
            problems.append(f"cited unknown claim_id(s): {sorted(fabricated)}")
        if duplicated:
            problems.append(f"duplicate cited claim_id(s): {duplicated}")
        if unresolved:
            problems.append(f"cited source_id(s) not in corpus: {unresolved}")
        return _gating("citation_integrity", not problems, "; ".join(problems))

    def _required_source_present(
        self, case: BlackBoxCase, response: BlackBoxResponse
    ) -> CriterionResult:
        if not case.must_include_source_ids:
            return CriterionResult(
                name="required_source_present",
                kind="gating",
                status="not_evaluated",
                detail="case names no required sources",
            )
        cited_sources = {c.source_id for c in response.cited_claims}
        missing = sorted(case.must_include_source_ids - cited_sources)
        return _gating(
            "required_source_present",
            not missing,
            f"required source(s) not surfaced: {missing}" if missing else "",
        )


def make_deterministic() -> DeterministicEvaluator:
    return DeterministicEvaluator()
