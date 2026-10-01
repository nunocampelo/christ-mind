from application.retrieval.describe_entity import CHANNEL, describe_entity
from infrastructure.database.claims import list_claims
from infrastructure.database.resolutions import entity_for_mention

_THINKING = frozenset({"thinking"})


def test_empty_mention_returns_nothing():
    assert describe_entity("", _THINKING) == []
    assert describe_entity("   ", _THINKING) == []


def test_respects_limit():
    assert len(describe_entity("God", _THINKING, limit=5)) <= 5


def test_returns_only_claims_incident_to_the_entity():
    entity = entity_for_mention("God")
    assert entity is not None
    forms = entity.mentions
    results = describe_entity("God", _THINKING, limit=1000)
    assert results
    assert all(
        r.claim.subject in forms
        or (r.claim.object is not None and r.claim.object in forms)
        for r in results
    )


def test_gathers_full_candidate_set_before_ranking():
    # The real fix: every God-incident claim is a candidate before the limit, so a
    # relational claim characterization would bury can still rank up. The unbounded call
    # must return exactly the incident set, not a pre-limited slice.
    entity = entity_for_mention("God")
    assert entity is not None
    forms = entity.mentions
    incident = {
        c.claim_id
        for c in list_claims()
        if c.subject in forms or (c.object is not None and c.object in forms)
    }
    returned = {
        r.claim.claim_id for r in describe_entity("God", _THINKING, limit=len(incident))
    }
    assert returned == incident


def test_thinking_question_surfaces_the_knowing_targets_within_default_limit():
    # Integration diagnostic (corpus-specific): the two "God knows ..." claims the
    # mind-of-god-004b gate needs must appear within the default selection budget, which
    # characterization ranking (predicate=other scored 0) buried at rank ~54/56.
    top = [r.claim.claim_id for r in describe_entity("God", _THINKING, limit=20)]
    assert any(cid.startswith("f99fd11e") for cid in top)
    assert any(cid.startswith("53c77a24") for cid in top)


def test_object_qualifier_survives_selection():
    # 53c77a24 is "God knows you ONLY IN PEACE" -- describe_entity returns whole Claims,
    # so the qualifier must not be flattened to a bare God->knows->you edge.
    match = next(
        r
        for r in describe_entity("God", _THINKING, limit=1000)
        if r.claim.claim_id.startswith("53c77a24")
    )
    assert match.claim.object == "you only in peace"


def test_aspect_changes_the_ordering():
    # Same entity, different aspect -> different ordering. A thinking question must not
    # rank identically to a creating question.
    thinking = [r.claim.claim_id for r in describe_entity("God", _THINKING, limit=20)]
    creating = [
        r.claim.claim_id
        for r in describe_entity("God", frozenset({"creating"}), limit=20)
    ]
    assert thinking != creating


def test_trace_records_channel_entity_and_rank():
    results = describe_entity("God", _THINKING, limit=5)
    entity = entity_for_mention("God")
    assert entity is not None
    for i, r in enumerate(results):
        assert r.rank == i
        assert r.seed_mention == "God"
        assert r.resolved_entity_id == entity.entity_id
        assert r.requested_aspects == ("thinking",)
    # A "God knows ..." claim carries its aspect match location; the channel is fixed.
    knows = next(r for r in results if r.claim.claim_id.startswith("f99fd11e"))
    assert knows.matched_aspect == "verb_phrase"


def test_channel_constant_is_entity_relation():
    assert CHANNEL == "entity_relation"
