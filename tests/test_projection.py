"""Unit tests for the deterministic graph projection and artifact (plan 0030, B).

The repository boundary (`entity_for_mention`, `source_for_id`) is injected or
monkeypatched; the application layer under test is not. Assertions are exact -- a
projection that silently dropped, merged, or reordered a claim would pass a truthiness
check but fail these.
"""

import application.projection.artifact as artifact_module
from application.projection.artifact import SCHEMA_VERSION, build_artifact, serialize
from application.projection.build_projection import (
    ExclusionReason,
    build_projection,
)
from domain.claims.models import Attribution, Claim, Mode, Polarity, Predicate
from domain.entities.models import Entity
from domain.sources.models import Source


def _claim(
    claim_id: str,
    subject: str,
    object: str | None,
    *,
    predicate: Predicate = Predicate.IS,
    polarity: Polarity = Polarity.AFFIRMED,
    mode: Mode = Mode.ASSERTION,
    attribution: Attribution = Attribution.COURSE,
    verb_phrase: str = "is",
    source_id: str = "src-1",
    start: int = 0,
    end: int = 3,
) -> Claim:
    return Claim(
        claim_id=claim_id,
        source_id=source_id,
        subject=subject,
        predicate=predicate,
        object=object,
        verb_phrase=verb_phrase,
        polarity=polarity,
        mode=mode,
        attribution=attribution,
        evidence_start=start,
        evidence_end=end,
    )


def _resolver(groups: dict[str, Entity]):
    """A mention -> Entity map; absent mentions resolve to None (own singleton),
    matching the real `entity_for_mention`."""
    return lambda mention: groups.get(mention)


# --- build_projection ------------------------------------------------------------


def test_missing_object_is_non_projectable_not_dropped():
    claims = [_claim("c1", "God", None, verb_phrase="WOULD be mocked")]
    proj = build_projection(claims, _resolver({}))
    assert proj.edges == ()
    assert len(proj.non_projectable) == 1
    assert proj.non_projectable[0].reason == ExclusionReason.MISSING_OBJECT
    assert proj.non_projectable[0].claim.claim_id == "c1"


def test_is_claim_does_not_merge_distinct_entities():
    claims = [_claim("c1", "God", "God's Thoughts", predicate=Predicate.IS)]
    proj = build_projection(claims, _resolver({}))
    assert len(proj.nodes) == 2
    assert {n.label for n in proj.nodes} == {"God", "God's Thoughts"}
    # one directed edge, no symmetric/inferred partner
    assert len(proj.edges) == 1
    assert proj.edges[0].source_node_id != proj.edges[0].target_node_id


def test_case_variants_merge_onto_one_entity_node():
    god = Entity(entity_id="god-id", mentions=frozenset({"GOD", "God"}))
    claims = [
        _claim("c1", "God", "life"),
        _claim("c2", "GOD", "peace"),
    ]
    proj = build_projection(claims, _resolver({"God": god, "GOD": god}))
    god_nodes = [n for n in proj.nodes if n.entity_id == "god-id"]
    assert len(god_nodes) == 1
    assert proj.edges[0].source_node_id == proj.edges[1].source_node_id
    # deterministic label: shortest then lexicographic -> "GOD" (both len 3, 'G'<'o')
    assert god_nodes[0].label == "GOD"


def test_parallel_edges_and_self_loop_retained():
    claims = [
        _claim("c1", "a", "b"),
        _claim("c2", "a", "b"),  # parallel: same endpoints, different claim
        _claim("c3", "a", "a"),  # self-loop
    ]
    proj = build_projection(claims, _resolver({}))
    assert len(proj.edges) == 3
    self_loops = [e for e in proj.edges if e.source_node_id == e.target_node_id]
    assert len(self_loops) == 1


def test_output_is_deterministically_ordered():
    claims = [_claim("c3", "a", "b"), _claim("c1", "x", "y"), _claim("c2", "m", "n")]
    proj = build_projection(claims, _resolver({}))
    assert [e.claim.claim_id for e in proj.edges] == ["c1", "c2", "c3"]
    assert list(proj.nodes) == sorted(proj.nodes, key=lambda n: n.node_id)


# --- build_artifact --------------------------------------------------------------


def _install_sources(monkeypatch, sources: dict[str, Source]):
    monkeypatch.setattr(artifact_module, "source_for_id", lambda sid: sources.get(sid))


def test_coverage_accounts_for_every_claim(monkeypatch):
    src = Source(id="src-1", book="ACIM", chapter=1, text="abc", section=0, paragraph=1)
    _install_sources(monkeypatch, {"src-1": src})
    claims = [
        _claim("c1", "a", "b"),
        _claim("c2", "a", None),
    ]
    proj = build_projection(claims, _resolver({}))
    art = build_artifact(proj, claim_count=len(claims), resolution_entity_count=0, source_count=1)
    assert art.counts.edges + art.counts.non_projectable == len(claims)
    assert art.counts.non_projectable_by_reason == {ExclusionReason.MISSING_OBJECT: 1}


def test_semantic_fields_survive_to_edge_record(monkeypatch):
    src = Source(id="src-1", book="ACIM", chapter=1, text="abc", section=0, paragraph=1)
    _install_sources(monkeypatch, {"src-1": src})
    claim = _claim(
        "c1", "ego", "real",
        predicate=Predicate.IS,
        polarity=Polarity.NEGATED,
        mode=Mode.CONDITIONAL,
        attribution=Attribution.EGO,
        verb_phrase="is thought to be",
    )
    proj = build_projection([claim], _resolver({}))
    art = build_artifact(proj, claim_count=1, resolution_entity_count=0, source_count=1)
    edge = art.edges[0]
    assert edge.polarity == Polarity.NEGATED
    assert edge.mode == Mode.CONDITIONAL
    assert edge.attribution == Attribution.EGO
    assert edge.verb_phrase == "is thought to be"


def test_astral_unicode_evidence_segments_slice_correctly(monkeypatch):
    # An astral char (👁, one code point, surrogate pair in UTF-16) precedes the clause.
    text = "👁 fear is real"
    start = text.index("fear")
    end = start + len("fear")
    src = Source(id="src-1", book="ACIM", chapter=1, text=text, section=0, paragraph=1)
    _install_sources(monkeypatch, {"src-1": src})
    claim = _claim("c1", "fear", "real", start=start, end=end)
    proj = build_projection([claim], _resolver({}))
    art = build_artifact(proj, claim_count=1, resolution_entity_count=0, source_count=1)
    seg = art.passages[0].evidence
    assert seg.clause == "fear"
    assert seg.before + seg.clause + seg.after == text


def test_export_is_byte_identical_on_repeat(monkeypatch):
    src = Source(id="src-1", book="ACIM", chapter=1, text="abcdef", section=0, paragraph=1)
    _install_sources(monkeypatch, {"src-1": src})
    claims = [_claim("c1", "a", "b"), _claim("c2", "c", "d", start=2, end=5)]
    proj = build_projection(claims, _resolver({}))
    a1 = serialize(build_artifact(proj, claim_count=2, resolution_entity_count=0, source_count=1))
    a2 = serialize(build_artifact(proj, claim_count=2, resolution_entity_count=0, source_count=1))
    assert a1 == a2
    assert SCHEMA_VERSION in a1


def test_unknown_source_fails_export(monkeypatch):
    _install_sources(monkeypatch, {})  # no sources at all
    proj = build_projection([_claim("c1", "a", "b")], _resolver({}))
    try:
        build_artifact(proj, claim_count=1, resolution_entity_count=0, source_count=0)
    except artifact_module.EvidenceResolutionError:
        return
    raise AssertionError("expected EvidenceResolutionError for an unknown source")
