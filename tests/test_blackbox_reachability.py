"""Tests for `evaluation.blackbox.reachability`. Exercises the tokenizer against real
corpus behavior via `find_claims`, so a corpus/ranking change surfaces here."""

from evaluation.blackbox.reachability import (
    is_lexically_reachable,
    plausible_query_terms,
)


def test_plausible_terms_are_content_words_only():
    # Stopwords, question words, and light discourse markers are stripped so the
    # plausible set contains only tokens a plausible mapper could emit as a
    # retrieval query. Order preserved.
    assert plausible_query_terms("What is the Course all about?") == [
        "course",
        "the course",
    ]


def test_plausible_terms_include_bigrams_and_leading_the():
    terms = plausible_query_terms("How does God think? What is the Mind of God?")
    # Content unigrams
    assert "god" in terms and "think" in terms and "mind" in terms
    # Contiguous bigrams
    assert "god think" in terms and "mind god" in terms
    # Leading-the variants
    assert "the god" in terms and "the mind" in terms
    # Stopwords never appear as unigrams
    assert "how" not in terms and "of" not in terms and "does" not in terms


def test_plausible_terms_preserve_hyphenated_compounds():
    # A corpus subject like "right-mindedness" would be unreachable if the
    # tokenizer split on the hyphen -- the mapper never emits "right" or
    # "mindedness" alone as a retrieval query for that concept.
    terms = plausible_query_terms("What is right-mindedness in the Course?")
    assert "right-mindedness" in terms


def test_lexically_reachable_true_for_course_about_case():
    # Both `must_include_any_claim_ids` from gold's course-about-006 -- subject is
    # "the course", question shares "course". The ranker fix means "the course"
    # reaches these in top-12.
    for cid in ("44e9f68768054c02", "934b7f695826e53c"):
        assert is_lexically_reachable(cid, "What is the Course all about?")


def test_lexically_unreachable_for_mind_of_god_case():
    # gold's mind-of-god-004b: none of the required claims' surface subjects
    # ("God's Miracles", "His Thoughts", "knows His Children"...) share tokens
    # with the question, so the plausible query set cannot reach them.
    question = "How does God think? What is the Mind of God?"
    for cid in (
        "efdccd0ac72007aa",
        "eb3114c3c10e65c7",
        "f99fd11eb731987c",
        "53c77a24b278b916",
        "ab816dad26ee5551",
    ):
        assert not is_lexically_reachable(cid, question)


def test_lexically_reachable_returns_false_for_empty_question():
    assert not is_lexically_reachable("any-id", "?!.")
