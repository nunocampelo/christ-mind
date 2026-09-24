from application.retrieval.find_claims_for_entity import find_claims_for_entity
from infrastructure.database.claims import list_claims
from infrastructure.database.resolutions import entity_for_mention


def test_returns_claims_across_all_of_the_entitys_surface_forms():
    # "the ego" resolves to an entity with several forms (ego, the EGO, his ego, ...);
    # the join must return claims naming ANY of them, not just the exact string.
    entity = entity_for_mention("the ego")
    assert entity is not None and len(entity.mentions) > 1

    results = find_claims_for_entity("the ego", limit=1000)
    exact = [
        c for c in list_claims() if c.subject == "the ego" or c.object == "the ego"
    ]

    assert len(results) > len(exact)
    # Every returned claim names one of the entity's forms as subject or object.
    assert all(
        c.subject in entity.mentions or c.object in entity.mentions for c in results
    )


def test_resolving_by_any_member_form_gives_the_same_claims():
    by_the_ego = {c.claim_id for c in find_claims_for_entity("the ego", limit=1000)}
    by_ego = {c.claim_id for c in find_claims_for_entity("ego", limit=1000)}

    assert by_the_ego == by_ego


def test_a_form_the_resolver_never_merged_returns_its_own_claims():
    # A singleton entity (or unseen form) falls back to just that form's claims.
    results = find_claims_for_entity("love", limit=1000)

    assert all(c.subject == "love" or c.object == "love" for c in results)


def test_respects_limit():
    assert len(find_claims_for_entity("the ego", limit=5)) <= 5


def test_empty_mention_returns_nothing():
    assert find_claims_for_entity("") == []
    assert find_claims_for_entity("   ") == []
