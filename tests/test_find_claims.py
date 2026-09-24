from application.retrieval.find_claims import find_claims


def _matches(claim, needle: str) -> bool:
    return (
        needle in claim.subject.lower()
        or (claim.object is not None and needle in claim.object.lower())
        or needle in claim.verb_phrase.lower()
    )


def test_every_result_actually_matches_the_needle():
    results = find_claims("forgiveness", limit=100)

    assert results
    assert all(_matches(claim, "forgiveness") for claim in results)


def test_matches_are_case_insensitive():
    lower = find_claims("miracle", limit=100)
    upper = find_claims("MIRACLE", limit=100)

    assert {c.claim_id for c in lower} == {c.claim_id for c in upper}
    assert lower


def test_respects_limit():
    assert len(find_claims("the", limit=3)) <= 3


def test_empty_query_returns_nothing():
    assert find_claims("") == []
    assert find_claims("   ") == []


def test_no_match_returns_empty():
    assert find_claims("xyzzy-nonexistent-term") == []
