import pytest

from application.retrieval import find_claims as find_claims_module
from application.retrieval.find_claims import find_claims, find_claims_batch
from domain.claims.models import Attribution, Claim, Mode, Polarity, Predicate


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


def test_batch_empty_list_returns_nothing():
    assert find_claims_batch([]) == []


def test_batch_skips_whitespace_only_queries():
    only_blanks = find_claims_batch(["", "   "])
    assert only_blanks == []

    with_blank = find_claims_batch(["forgiveness", "  "])
    forgiveness_only = find_claims_batch(["forgiveness"])
    assert {c.claim_id for c in with_blank} == {c.claim_id for c in forgiveness_only}


def test_batch_dedupes_by_claim_id():
    results = find_claims_batch(["forgiveness", "forgiveness"], global_limit=100)
    ids = [c.claim_id for c in results]
    assert ids == list(dict.fromkeys(ids))


def test_batch_enforces_global_limit():
    results = find_claims_batch(["the", "God", "peace"], global_limit=4)
    assert len(results) <= 4


def test_batch_interleaves_rather_than_concatenating():
    # With more than one matching query, a global budget smaller than one query's own
    # matches must still draw from the other queries -- not exhaust the first query.
    forgiveness = find_claims("forgiveness", limit=100)
    peace = find_claims("peace", limit=100)
    assert len(forgiveness) >= 2 and len(peace) >= 1

    budget = len(forgiveness)
    results = find_claims_batch(
        ["forgiveness", "peace"], limit_per_query=100, global_limit=budget
    )
    result_ids = {c.claim_id for c in results}
    peace_ids = {c.claim_id for c in peace}
    assert result_ids & peace_ids


def _mk(claim_id: str, subject: str, predicate: Predicate, object: str | None) -> Claim:
    return Claim(
        claim_id=claim_id,
        source_id="t1-1-1",
        subject=subject,
        predicate=predicate,
        object=object,
        verb_phrase="",
        polarity=Polarity.AFFIRMED,
        mode=Mode.ASSERTION,
        attribution=Attribution.COURSE,
        evidence_start=0,
        evidence_end=1,
    )


def test_definitional_match_survives_limit_despite_late_corpus_position(
    monkeypatch: pytest.MonkeyPatch,
):
    # The failure this increment fixes: the definitional subject match sits *past* `limit`
    # in corpus order, so a pre-ranking slice would drop it. Ranking must run before the
    # slice, so it is returned at limit=1.
    incidental = [_mk(f"inc{i}", "fear", Predicate.OTHER, "x") for i in range(5)]
    definition = _mk("def", "x", Predicate.IS, "healing")
    corpus = incidental + [definition]  # definition is last in corpus order
    monkeypatch.setattr(find_claims_module, "list_claims", lambda: corpus)

    results = find_claims("x", limit=1)
    assert [c.claim_id for c in results] == ["def"]


def test_right_mindedness_definition_surfaces_from_real_corpus():
    # The concrete regression: "right-mindedness IS healing" (t2-2-13) must be ranked into
    # the small per-query limit the agent uses, not dropped by corpus position.
    results = find_claims("right-mindedness", limit=5)
    assert any(
        c.source_id == "t2-2-13" and c.subject.lower() == "right-mindedness"
        for c in results
    )
