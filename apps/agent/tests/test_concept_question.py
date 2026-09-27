"""The concept-question detector's contract: fires only on bare-subject definitional
questions and returns the subject as a lowercase retrieval term."""

import pytest

from mind_of_christ_agent.domain.concept_question import concept_query_terms

_FIRES = [
    ("What is the ego?", "ego"),
    ("What is salvation?", "salvation"),
    ("What is guilt?", "guilt"),
    ("what is the Atonement", "atonement"),
    ("What are miracles?", "miracles"),
    ("Describe the Holy Spirit.", "holy spirit"),
    ("Define forgiveness", "forgiveness"),
    ("What's the ego?", "ego"),
]

_DOES_NOT_FIRE = [
    "How can I forgive my mother?",
    "How are love and fear related?",
    "What does the Course say about forgiveness?",
    "What is the Course's position on forgiveness?",
    "How does the ego relate to separation?",
    "I keep getting angry whenever my coworker criticizes me.",
    "Can you help me?",
    "What is the ego doing to me?",
]


@pytest.mark.parametrize("q,subject", _FIRES)
def test_fires_on_bare_subject_definition(q: str, subject: str):
    assert concept_query_terms(q) == [subject]


@pytest.mark.parametrize("q", _DOES_NOT_FIRE)
def test_silent_on_non_definitional(q: str):
    assert concept_query_terms(q) == []
