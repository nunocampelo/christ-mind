"""The versioned, byte-stable JSON artifact the `/graph` page loads (plan 0030).

One pydantic model tree so a renamed or dropped field fails at validation, not silently,
and the written/read shapes cannot drift -- the frontend adapter validates against the
same schema. Nothing here is a bare `dict`.

Two things are deliberate:

- **Evidence is exported as before/clause/after segments**, already sliced in Python's
  character coordinates. The frontend highlights by concatenating segments, never by
  re-slicing on offsets -- JS string indexing is UTF-16 code units, so a Python char
  offset would drift past any astral character. The offsets travel too, but only as
  provenance.
- **Metadata hashes the inputs, not the output.** Two exports from the same claim +
  resolution + source snapshot are byte-identical; a changed snapshot yields a changed
  `content_hash`, which the frontend uses to detect that a saved selection refers to a
  projection that no longer exists.
"""

import hashlib
import json

from pydantic import BaseModel

from application.projection.build_projection import (
    ExclusionReason,
    Projection,
    ProjectionEdge,
)
from application.retrieval.evidence import EvidenceResolutionError, source_for_id
from domain.claims.models import Attribution, Mode, Polarity, Predicate
from domain.sources.models import Source

SCHEMA_VERSION = "0030.graph-projection.1"


class EvidenceSegments(BaseModel):
    """Pre-sliced text around the quoted clause. Frontend highlights by rendering
    `before` + styled `clause` + `after`, never by re-slicing on the offsets, which are
    Python char coordinates and carried only as provenance."""

    before: str
    clause: str
    after: str
    evidence_start: int
    evidence_end: int


class PassageRef(BaseModel):
    """Full paragraph text lives only in `evidence` as `before`+`clause`+`after`; the
    frontend reconstructs the paragraph by concatenating them and highlights `clause`
    in place. A separate `text` field would duplicate exactly that (it bloated the
    artifact ~2x), so it is deliberately absent."""

    source_id: str
    book: str
    chapter: int
    verse: int | None
    section: int | None
    paragraph: int | None
    edition: str
    evidence: EvidenceSegments


class EdgeRecord(BaseModel):
    claim_id: str
    source_node_id: str
    target_node_id: str
    subject: str
    object: str
    predicate: Predicate
    verb_phrase: str
    polarity: Polarity
    mode: Mode
    attribution: Attribution
    source_id: str


class NodeRecord(BaseModel):
    node_id: str
    label: str
    entity_id: str | None
    expressions: list[str]


class NonProjectableRecord(BaseModel):
    claim_id: str
    subject: str
    object: str | None
    predicate: Predicate
    verb_phrase: str
    polarity: Polarity
    mode: Mode
    attribution: Attribution
    reason: ExclusionReason
    source_id: str


class CoverageCounts(BaseModel):
    input_claims: int
    nodes: int
    edges: int
    non_projectable: int
    non_projectable_by_reason: dict[ExclusionReason, int]
    # A node is `catalogued` when a surface form resolved to a baseline entity (even a
    # one-member one), `uncatalogued` when it stood as its own form. Among catalogued
    # nodes, `merged` ones have more than one observed expression -- the actual merges,
    # which the baseline resolver does rarely (see docs/graph-explorer-inspection.md).
    catalogued_nodes: int
    uncatalogued_nodes: int
    merged_nodes: int


class ArtifactMetadata(BaseModel):
    schema_version: str
    content_hash: str
    claim_count: int
    resolution_entity_count: int
    source_count: int


class GraphArtifact(BaseModel):
    metadata: ArtifactMetadata
    nodes: list[NodeRecord]
    edges: list[EdgeRecord]
    non_projectable: list[NonProjectableRecord]
    passages: list[PassageRef]
    counts: CoverageCounts


def _segments(source: Source, start: int, end: int) -> EvidenceSegments:
    if not 0 <= start <= end <= len(source.text):
        raise EvidenceResolutionError("claim evidence offsets fall outside the source text")
    return EvidenceSegments(
        before=source.text[:start],
        clause=source.text[start:end],
        after=source.text[end:],
        evidence_start=start,
        evidence_end=end,
    )


def _edge_record(edge: ProjectionEdge) -> EdgeRecord:
    c = edge.claim
    assert c.object is not None  # a drawn edge always has an object (build_projection guarantees)
    return EdgeRecord(
        claim_id=c.claim_id,
        source_node_id=edge.source_node_id,
        target_node_id=edge.target_node_id,
        subject=c.subject,
        object=c.object,
        predicate=c.predicate,
        verb_phrase=c.verb_phrase,
        polarity=c.polarity,
        mode=c.mode,
        attribution=c.attribution,
        source_id=c.source_id,
    )


def build_artifact(
    projection: Projection,
    claim_count: int,
    resolution_entity_count: int,
    source_count: int,
) -> GraphArtifact:
    """Assemble the validated artifact from a built `Projection`.

    Every edge and non-projectable claim must join to a source and have valid evidence
    offsets; a failure raises `EvidenceResolutionError` with the offending claim id rather
    than exporting a broken join. Passages are deduplicated and carry each referenced
    claim's evidence segments.
    """
    nodes = [
        NodeRecord(
            node_id=n.node_id,
            label=n.label,
            entity_id=n.entity_id,
            expressions=list(n.expressions),
        )
        for n in projection.nodes
    ]

    edges = [_edge_record(e) for e in projection.edges]

    non_projectable = [
        NonProjectableRecord(
            claim_id=n.claim.claim_id,
            subject=n.claim.subject,
            object=n.claim.object,
            predicate=n.claim.predicate,
            verb_phrase=n.claim.verb_phrase,
            polarity=n.claim.polarity,
            mode=n.claim.mode,
            attribution=n.claim.attribution,
            reason=n.reason,
            source_id=n.claim.source_id,
        )
        for n in projection.non_projectable
    ]

    passages = _passages_for(projection)

    reason_counts: dict[ExclusionReason, int] = {}
    for n in projection.non_projectable:
        reason_counts[n.reason] = reason_counts.get(n.reason, 0) + 1

    counts = CoverageCounts(
        input_claims=claim_count,
        nodes=len(nodes),
        edges=len(edges),
        non_projectable=len(non_projectable),
        non_projectable_by_reason=reason_counts,
        catalogued_nodes=sum(1 for n in projection.nodes if n.entity_id is not None),
        uncatalogued_nodes=sum(1 for n in projection.nodes if n.entity_id is None),
        merged_nodes=sum(1 for n in projection.nodes if len(n.expressions) > 1),
    )

    body = {
        "schema_version": SCHEMA_VERSION,
        "nodes": [n.model_dump() for n in nodes],
        "edges": [e.model_dump() for e in edges],
        "non_projectable": [n.model_dump() for n in non_projectable],
        "passages": [p.model_dump() for p in passages],
    }
    content_hash = hashlib.sha256(
        json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()

    metadata = ArtifactMetadata(
        schema_version=SCHEMA_VERSION,
        content_hash=content_hash,
        claim_count=claim_count,
        resolution_entity_count=resolution_entity_count,
        source_count=source_count,
    )
    return GraphArtifact(
        metadata=metadata,
        nodes=nodes,
        edges=edges,
        non_projectable=non_projectable,
        passages=passages,
        counts=counts,
    )


def _passages_for(projection: Projection) -> list[PassageRef]:
    """One `PassageRef` per (source_id, evidence span) a drawn or non-projectable claim
    references. Deduplicated and sorted deterministically so re-export is byte-stable."""
    seen: dict[tuple[str, int, int], PassageRef] = {}
    claims = [e.claim for e in projection.edges] + [
        n.claim for n in projection.non_projectable
    ]
    for claim in claims:
        key = (claim.source_id, claim.evidence_start, claim.evidence_end)
        if key in seen:
            continue
        source = source_for_id(claim.source_id)
        if source is None:
            raise EvidenceResolutionError("claim references an unknown source")
        seen[key] = PassageRef(
            source_id=source.id,
            book=source.book,
            chapter=source.chapter,
            verse=source.verse,
            section=source.section,
            paragraph=source.paragraph,
            edition=source.edition,
            evidence=_segments(source, claim.evidence_start, claim.evidence_end),
        )
    return [seen[k] for k in sorted(seen)]


def serialize(artifact: GraphArtifact) -> str:
    """Byte-stable JSON for committing under the frontend's public assets."""
    return json.dumps(
        artifact.model_dump(),
        sort_keys=True,
        ensure_ascii=False,
        indent=2,
    ) + "\n"
