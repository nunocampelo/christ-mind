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
    assert "don't directly address" in prompt
    assert "never substitute generic advice" in prompt


@pytest.mark.parametrize("prompt", PROSE_PROMPTS, ids=IDS)
def test_forbids_offering_to_look_further(prompt: str):
    # The agent has already searched; it must not close by offering to search more.
    assert "Do not\noffer to look further" in prompt or "Do not offer to look further" in prompt.replace(
        "\n", " "
    )


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


@pytest.mark.parametrize("prompt", PROSE_PROMPTS, ids=IDS)
def test_carries_the_inline_marker_contract(prompt: str):
    assert "[<claim_id>]" in prompt
    assert "exact claim_id" in prompt


@pytest.mark.parametrize("prompt", PROSE_PROMPTS, ids=IDS)
def test_bans_the_retrieval_meta_voice(prompt: str):
    # The voice must not narrate the machinery; these phrases are listed as forbidden.
    for banned in ("the cited claims", "the retrieved claims", "the evidence supports"):
        assert banned in prompt


@pytest.mark.parametrize("prompt", PROSE_PROMPTS, ids=IDS)
def test_carries_the_boundary_voice_template(prompt: str):
    # The epistemic-boundary sentence must stay in the teaching's register, with a positive
    # example to imitate -- not only phrases to avoid.
    assert "the teaching speaking for itself" in prompt
    assert "they don't yet give us enough to describe its nature more fully" in prompt


def test_decision_prompt_forbids_repeating_a_zero_result_call():
    # Only the decision prompt governs tool-calling; the answer prompt doesn't call tools.
    flat = DECISION_SYSTEM_PROMPT.replace("\n", " ")
    assert "the corpus does not hold that target" in flat
    assert "do NOT chase it with reworded terms" in flat


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


def test_rendered_claim_line_exposes_the_claim_id_for_citing():
    # The model cites by claim_id, so it must appear in the rendered evidence line.
    rendered = answer_user_prompt("describe God", [_cited("affirmed")], [])

    assert "claim_id=c1" in rendered
