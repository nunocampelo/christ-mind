"""The meta-question detector's contract: fires only when the Course itself is the object of
inquiry, and always yields the canonical query term "course"."""

import pytest

from mind_of_christ_agent.domain.meta_question import (
    is_meta_question,
    meta_query_terms,
)

_FIRES = [
    "What is the Course all about?",
    "What is the Course about?",
    "What is the Course?",
    "what is the course",
    "What does the Course teach?",
    "What is the purpose of the Course?",
    "What is the aim of the Course?",
    "What is A Course in Miracles about?",
    "Tell me about the Course.",
    "What is this teaching about?",
]

# Content questions (Course named, but a concept is the real subject), applying-to-situation
# questions, life situations, and outside-corpus questions must all NOT fire.
_DOES_NOT_FIRE = [
    "What does the Course say about forgiveness?",
    "What is the Course's position on forgiveness?",
    "How can the Course help me with fear?",
    "How are love and fear related in the Course?",
    "What does the Course teach about the mind?",
    "What is forgiveness?",
    "I keep getting angry whenever my coworker criticizes my work.",
    "What is Workbook Lesson 1 and how do I practice it?",
    "Who transcribed the Course and in what year?",
]


@pytest.mark.parametrize("q", _FIRES)
def test_fires_on_course_as_object(q: str):
    assert is_meta_question(q)
    assert meta_query_terms(q) == ["course"]


@pytest.mark.parametrize("q", _DOES_NOT_FIRE)
def test_does_not_fire_otherwise(q: str):
    assert not is_meta_question(q)
    assert meta_query_terms(q) == []


def test_referent_maps_to_course_not_its_own_word():
    # "this teaching" fires, but the query is the canonical "course" (which surfaces t1-0-1),
    # never "teaching" (which does not).
    assert meta_query_terms("What is this teaching about?") == ["course"]
