"""The inline-marker reader shared by the orchestrator's soft citation audit."""

from mind_of_christ_agent.domain.citations import extract_markers


def test_extracts_claim_ids_in_order_with_duplicates_kept():
    text = "God is the Giver of life. [t1-1-4] He gave them peace. [t2-1-3] [t1-1-4]"

    assert extract_markers(text) == ["t1-1-4", "t2-1-3", "t1-1-4"]


def test_ignores_bracketed_prose_that_is_not_a_claim_id():
    # A bracketed span with a space is ordinary prose, not a marker.
    text = "This is grounded [see below] and cited. [neg-1]"

    assert extract_markers(text) == ["neg-1"]


def test_no_markers_yields_empty():
    assert extract_markers("Peace is already yours.") == []
