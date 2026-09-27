import pytest

from application.retrieval import find_sources as find_sources_module
from application.retrieval.find_sources import find_sources
from application.retrieval.get_source import get_sources
from domain.sources.models import Source


def test_find_sources_matches_by_concept():
    results = find_sources("forgiveness")

    assert results
    assert any(source.id == "matt-6-14-15" for source in results)


def test_find_sources_matches_by_text():
    results = find_sources("meek")

    assert any(source.id == "matt-5-5" for source in results)


def test_find_sources_respects_limit():
    results = find_sources("the", limit=1)

    assert len(results) <= 1


def test_find_sources_empty_query_returns_nothing():
    assert find_sources("") == []


def test_find_sources_no_match_returns_empty():
    assert find_sources("xyzzy-nonexistent-term") == []


def test_find_sources_concept_match_is_case_insensitive(monkeypatch: pytest.MonkeyPatch):
    tagged = Source(
        id="cased-concept",
        book="ACIM",
        chapter=1,
        text="unrelated body text",
        concepts=("Forgiveness",),
    )
    monkeypatch.setattr(find_sources_module, "list_sources", lambda: (tagged,))

    results = find_sources("forgiveness")

    assert [s.id for s in results] == ["cased-concept"]


def test_get_sources_returns_requested_in_order():
    results = get_sources(["matt-5-5", "matt-6-14-15"])

    assert [s.id for s in results] == ["matt-5-5", "matt-6-14-15"]


def test_get_sources_omits_unknown_ids():
    results = get_sources(["matt-5-5", "not-a-real-id"])

    assert [s.id for s in results] == ["matt-5-5"]


def test_get_sources_dedupes_and_skips_blanks():
    results = get_sources(["matt-5-5", " matt-5-5 ", "", "  "])

    assert [s.id for s in results] == ["matt-5-5"]


def test_get_sources_empty_input_returns_empty():
    assert get_sources([]) == []
