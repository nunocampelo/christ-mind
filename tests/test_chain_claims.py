"""Unit tests for the deterministic claim-chain walker.

Everything is asserted by exact chain equality on a small hand-built fixture, not by
truthiness: a walker that silently drops or reorders a link would pass a `assert
chains` check but fail these. The repository boundary (`list_claims`,
`entity_for_mention`) is mocked -- the application layer under test is not.
"""

import application.synthesis.chain_claims as chain_module
from application.synthesis.chain_claims import ClaimChain, chain_claims
from domain.claims.models import Attribution, Claim, Mode, Polarity, Predicate
from domain.entities.models import Entity


def _claim(
    claim_id: str,
    subject: str,
    object: str | None,
    predicate: Predicate = Predicate.CAUSES,
    polarity: Polarity = Polarity.AFFIRMED,
    attribution: Attribution = Attribution.COURSE,
) -> Claim:
    return Claim(
        claim_id=claim_id,
        source_id=f"src-{claim_id}",
        subject=subject,
        predicate=predicate,
        object=object,
        verb_phrase="leads to",
        polarity=polarity,
        mode=Mode.ASSERTION,
        attribution=attribution,
        evidence_start=0,
        evidence_end=1,
    )


def _install(monkeypatch, claims, resolution=None):
    """Serve `claims` and a `mention -> Entity` resolution to the walker. Mentions
    absent from `resolution` resolve to themselves, matching the real repository."""
    resolution = resolution or {}
    monkeypatch.setattr(chain_module, "list_claims", lambda: tuple(claims))
    monkeypatch.setattr(
        chain_module, "entity_for_mention", lambda m: resolution.get(m)
    )


def test_walks_a_single_predicate_shortest_first(monkeypatch):
    a = _claim("a", "fear", "guilt")
    b = _claim("b", "guilt", "attack")
    c = _claim("c", "attack", "pain")
    _install(monkeypatch, [a, b, c])

    result = chain_claims("fear", Predicate.CAUSES, max_hops=3, limit=10)

    assert result == [
        ClaimChain(links=(a,)),
        ClaimChain(links=(a, b)),
        ClaimChain(links=(a, b, c)),
    ]


def test_wrong_predicate_claims_are_not_walked(monkeypatch):
    a = _claim("a", "fear", "guilt", predicate=Predicate.CAUSES)
    b = _claim("b", "guilt", "attack", predicate=Predicate.REQUIRES)
    _install(monkeypatch, [a, b])

    result = chain_claims("fear", Predicate.CAUSES, max_hops=3)

    assert result == [ClaimChain(links=(a,))]


def test_negated_link_does_not_extend(monkeypatch):
    a = _claim("a", "fear", "guilt")
    b = _claim("b", "guilt", "attack", polarity=Polarity.NEGATED)
    _install(monkeypatch, [a, b])

    result = chain_claims("fear", Predicate.CAUSES, max_hops=3)

    # "guilt does NOT cause attack" is a non-edge: the chain stops at guilt.
    assert result == [ClaimChain(links=(a,))]


def test_non_course_link_does_not_extend(monkeypatch):
    a = _claim("a", "fear", "guilt")
    b = _claim("b", "guilt", "attack", attribution=Attribution.EGO)
    _install(monkeypatch, [a, b])

    result = chain_claims("fear", Predicate.CAUSES, max_hops=3)

    assert result == [ClaimChain(links=(a,))]


def test_seed_may_be_non_course_but_extension_must_be_course(monkeypatch):
    # Seed is what the ego believes; the extension from there must be the Course's.
    seed = _claim("a", "fear", "guilt", attribution=Attribution.EGO)
    ext = _claim("b", "guilt", "attack")
    _install(monkeypatch, [seed, ext])

    result = chain_claims("fear", Predicate.CAUSES, max_hops=3)

    assert result == [ClaimChain(links=(seed,)), ClaimChain(links=(seed, ext))]


def test_per_path_cycle_guard_terminates(monkeypatch):
    a = _claim("a", "fear", "guilt")
    b = _claim("b", "guilt", "fear")  # closes A -> B -> A
    _install(monkeypatch, [a, b])

    result = chain_claims("fear", Predicate.CAUSES, max_hops=5)

    # b extends a once (guilt), but cannot re-enter fear; a is also its own 1-chain.
    assert result == [ClaimChain(links=(a,)), ClaimChain(links=(a, b))]


def test_two_chains_converging_on_one_entity_both_survive(monkeypatch):
    # A -> B -> D and A -> C -> D: a global visited set would drop the second.
    ab = _claim("ab", "fear", "guilt")
    ac = _claim("ac", "fear", "anger")
    bd = _claim("bd", "guilt", "pain")
    cd = _claim("cd", "anger", "pain")
    _install(monkeypatch, [ab, ac, bd, cd])

    result = chain_claims("fear", Predicate.CAUSES, max_hops=2, limit=10)

    assert ClaimChain(links=(ab, bd)) in result
    assert ClaimChain(links=(ac, cd)) in result


def test_resolution_join_hops_across_surface_forms(monkeypatch):
    # A link's object "guilt" and the next link's subject "the guilt" are one entity.
    a = _claim("a", "fear", "guilt")
    b = _claim("b", "the guilt", "attack")
    guilt = Entity(entity_id="e-guilt", mentions=frozenset({"guilt", "the guilt"}))
    _install(monkeypatch, [a, b], resolution={"guilt": guilt, "the guilt": guilt})

    result = chain_claims("fear", Predicate.CAUSES, max_hops=2)

    assert ClaimChain(links=(a, b)) in result


def test_max_hops_bounds_depth(monkeypatch):
    a = _claim("a", "fear", "guilt")
    b = _claim("b", "guilt", "attack")
    c = _claim("c", "attack", "pain")
    _install(monkeypatch, [a, b, c])

    result = chain_claims("fear", Predicate.CAUSES, max_hops=2)

    assert all(len(chain.links) <= 2 for chain in result)
    assert ClaimChain(links=(a, b, c)) not in result


def test_limit_caps_number_of_chains(monkeypatch):
    a = _claim("a", "fear", "guilt")
    b = _claim("b", "guilt", "attack")
    c = _claim("c", "attack", "pain")
    _install(monkeypatch, [a, b, c])

    assert len(chain_claims("fear", Predicate.CAUSES, max_hops=3, limit=2)) == 2


def test_tie_break_is_stable_regardless_of_storage_order(monkeypatch):
    a1 = _claim("a1", "fear", "guilt")
    a2 = _claim("a2", "fear", "anger")
    _install(monkeypatch, [a2, a1])
    forward = chain_claims("fear", Predicate.CAUSES, max_hops=1)
    _install(monkeypatch, [a1, a2])
    reversed_ = chain_claims("fear", Predicate.CAUSES, max_hops=1)

    assert forward == reversed_ == [ClaimChain(links=(a1,)), ClaimChain(links=(a2,))]


def test_empty_mention_returns_nothing(monkeypatch):
    _install(monkeypatch, [_claim("a", "fear", "guilt")])

    assert chain_claims("", Predicate.CAUSES) == []
    assert chain_claims("   ", Predicate.CAUSES) == []
