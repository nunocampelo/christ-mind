"""Unit tests for the relational-question detector. The exact-wording concern from the
first A/B -- "does the narrow pattern actually fire on the known target question?" -- is
resolved here, before any live run: `test_fires_on_the_target_question` locks that
"How does God think?" produces a probe for God/thinking.
"""

from mind_of_christ_agent.domain.relational_question import (
    RelationalProbe,
    relational_probe,
)


def test_fires_on_the_target_question():
    # mind-of-god-004b's EXACT gold wording -- two sentences. The first live A/B silently
    # no-op'd because the single-clause patterns, anchored start-to-end, matched neither the
    # joined string (they swallowed the second sentence into the target); clause-splitting is
    # what makes the real case route. Lock the gold text verbatim, not a trimmed version.
    probe = relational_probe("How does God think? What is the Mind of God?")
    assert probe is not None
    assert probe.target == "God"
    assert probe.aspects == ("thinking",)


def test_a_trailing_second_sentence_is_not_swallowed_into_the_target():
    # The specific regression: "God think? What is the Mind of" must never be the target.
    probe = relational_probe("How does God think? And then what?")
    assert probe is not None
    assert probe.target == "God"


def test_how_does_x_maps_verb_to_aspect():
    assert relational_probe("how does God create?") == RelationalProbe(
        target="God", aspects=("creating",), reason="how-does: create"
    )
    assert relational_probe("How does the ego attack me") is not None


def test_how_does_keeps_the_article_in_the_target():
    # describe_entity resolves surface forms, so "the ego" and "ego" land on one entity;
    # the detector hands the mention through as written rather than stripping the article.
    probe = relational_probe("how does the ego attack?")
    assert probe is not None
    assert probe.target == "the ego"


def test_unknown_verb_yields_a_target_with_no_aspect():
    # The question still routes to the entity (so the channel gets its participation
    # ranking), but no aspect weight is invented for a verb the map doesn't cover.
    probe = relational_probe("how does God relate?")
    assert probe is not None
    assert probe.target == "God"
    assert probe.aspects == ()


def test_possessive_mind_of_x_maps_to_thinking():
    probe = relational_probe("What is the Mind of God?")
    assert probe is not None
    assert probe.target == "God"
    assert probe.aspects == ("thinking",)
    assert probe.reason == "aspect-of: mind"


def test_possessive_will_of_x_maps_to_willing():
    probe = relational_probe("what is the Will of God")
    assert probe is not None
    assert probe.aspects == ("willing",)


def test_bare_definitional_question_is_not_relational():
    # "what is the ego?" is concept_question's job (a definitional subject), not a
    # relational probe -- the detector must stay out of its lane so the A/B is interpretable.
    assert relational_probe("What is the ego?") is None
    assert relational_probe("what is salvation?") is None


def test_content_and_other_framings_do_not_fire():
    assert relational_probe("What does the Course say about forgiveness?") is None
    assert relational_probe("I can't forgive my friend") is None
    assert relational_probe("tell me about God") is None
