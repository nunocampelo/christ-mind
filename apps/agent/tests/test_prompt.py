"""Regression guards on the two prose-producing prompts. The content contract (no
unsupported interpretation, insufficient-evidence honesty) is enforced by the model, not
unit-assertable; these tests just ensure a future edit doesn't silently drop one of the
two prompts' clauses, since both paths must carry the identical contract.
"""

import pytest

from mind_of_christ_agent.application.answer import CitedClaim
from mind_of_christ_agent.domain.prompt import (
    ANSWER_SYSTEM_PROMPT,
    DECISION_SYSTEM_PROMPT,
    answer_user_prompt,
)

PROSE_PROMPTS = [DECISION_SYSTEM_PROMPT, ANSWER_SYSTEM_PROMPT]
IDS = ["decision", "answer"]


@pytest.mark.parametrize("prompt", PROSE_PROMPTS, ids=IDS)
def test_carries_the_evidence_boundary_rule(prompt: str):
    assert "must be supported by" in prompt
    assert "conversational framing" in prompt


@pytest.mark.parametrize("prompt", PROSE_PROMPTS, ids=IDS)
def test_carries_the_insufficient_evidence_contract(prompt: str):
    assert "don't sufficiently address" in prompt
    assert "never substitute generic advice" in prompt


@pytest.mark.parametrize("prompt", PROSE_PROMPTS, ids=IDS)
def test_preserves_the_cited_vs_synthesis_distinction(prompt: str):
    assert "single statement from the Course" in prompt


@pytest.mark.parametrize("prompt", PROSE_PROMPTS, ids=IDS)
def test_forbids_transferring_the_questions_framing_onto_the_claims(prompt: str):
    assert "transfer a property or relationship from the person's question" in prompt


@pytest.mark.parametrize("prompt", PROSE_PROMPTS, ids=IDS)
def test_carries_the_polarity_preservation_rule(prompt: str):
    assert "Preserve polarity exactly" in prompt
    assert "evidence span is authoritative" in prompt


def _cited(polarity: str) -> CitedClaim:
    return CitedClaim(
        claim_id="c1",
        source_id="t1-1-86",
        subject="God",
        predicate="is",
        object="partial",
        verb_phrase="is",
        polarity=polarity,
        evidence="God is NOT partial.",
    )


def test_negated_claim_renders_with_marker_and_evidence():
    rendered = answer_user_prompt("describe God", [_cited("negated")], [])

    # The affirmative-reading proposition is flagged and the negation-bearing evidence is
    # shown, so the model cannot render "God is partial" as the Course's claim.
    assert "[NEGATED]" in rendered
    assert "God is NOT partial." in rendered


def test_affirmed_claim_renders_without_the_negated_marker():
    rendered = answer_user_prompt("describe God", [_cited("affirmed")], [])

    assert "[NEGATED]" not in rendered
