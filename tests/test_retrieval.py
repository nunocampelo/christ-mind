import pytest

from application.retrieval import find_sources as find_sources_module
from application.retrieval.find_sources import find_sources
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
