"""Deterministic graph projection over stored claims (increment B of plan 0030).

Turns the authoritative claims + entity resolution into a navigable projection: one
directed edge per *drawable* claim, plus the claims that participate but cannot be drawn
(missing object, or an endpoint that is not a usable surface form), kept inspectable
rather than dropped. Entities, claims, and sources stay authoritative; everything here is
a derived artifact that can be rebuilt byte-for-byte from the same snapshot.

Transport-free and independent of Cytoscape's wire format (that conversion is the
frontend adapter's job), so it is unit-testable directly against the repository
boundary, like `chain_claims`/`describe_entity`. The contract this implements is fixed in
`docs/graph-explorer-inspection.md`.

Only mechanical status is asserted here -- endpoint eligibility and the claim->passage
join. Concept validity and contextual meaning are not automatable and are deferred to the
manual review (increment D); nothing in this module presents eligibility as semantic
validity.
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from enum import StrEnum

from domain.claims.models import Claim
from domain.entities.models import Entity

Resolver = Callable[[str], Entity | None]


class ExclusionReason(StrEnum):
    MISSING_OBJECT = "missing_object"
    SUBJECT_NOT_DRAWABLE = "subject_not_drawable"
    OBJECT_NOT_DRAWABLE = "object_not_drawable"


@dataclass(frozen=True)
class ProjectionNode:
    """A drawable endpoint. `entity_id` is the resolved catalog id, or `None` when the
    surface form stands as its own singleton (the resolver never merged it). `label` is a
    deterministic presentation choice among `expressions`, never a canonical name."""

    node_id: str
    label: str
    entity_id: str | None
    expressions: tuple[str, ...]


@dataclass(frozen=True)
class ProjectionEdge:
    """One directed edge, identified by its claim. Carries every semantic field so the
    frontend can show polarity/mode/attribution before selection; `verb_phrase` is the
    text's own wording and is never reversed even when `predicate` normalization flipped
    direction."""

    claim: Claim
    source_node_id: str
    target_node_id: str


@dataclass(frozen=True)
class NonProjectableClaim:
    """A claim that participates but cannot be drawn as a concept-to-concept edge. Kept so
    the relationship list can show it with its original wording and the reason, rather
    than manufacturing an endpoint node."""

    claim: Claim
    reason: ExclusionReason


@dataclass(frozen=True)
class Projection:
    nodes: tuple[ProjectionNode, ...]
    edges: tuple[ProjectionEdge, ...]
    non_projectable: tuple[NonProjectableClaim, ...]


def _node_id(mention: str, entity: Entity | None) -> str:
    """Stable node identity. A merged mention keys on its entity id so every form of the
    same entity lands on one node; a singleton keys on its own surface form. Prefixed so a
    singleton form can never collide with an entity id."""
    return f"e:{entity.entity_id}" if entity is not None else f"m:{mention}"


def _choose_label(expressions: Iterable[str]) -> str:
    """Shortest expression, lexicographic tie-break -- deterministic and stable under
    re-export regardless of resolver member ordering."""
    return min(expressions, key=lambda e: (len(e), e))


def build_projection(
    claims: Iterable[Claim],
    resolve: Resolver,
) -> Projection:
    """Project `claims` into nodes/edges/non-projectable records.

    `resolve` maps a surface form to its `Entity` or `None` (the repository's
    `entity_for_mention`, injected so this stays transport- and storage-free). A claim is
    drawn iff it has an object and both endpoints are non-empty surface forms; otherwise it
    is recorded as non-projectable with its reason. Output ordering is deterministic:
    nodes by `node_id`, edges and non-projectable by `claim_id`.
    """
    nodes: dict[str, ProjectionNode] = {}
    edges: list[ProjectionEdge] = []
    non_projectable: list[NonProjectableClaim] = []

    def register(mention: str) -> str:
        entity = resolve(mention)
        node_id = _node_id(mention, entity)
        if node_id not in nodes:
            expressions = tuple(sorted(entity.mentions)) if entity is not None else (mention,)
            nodes[node_id] = ProjectionNode(
                node_id=node_id,
                label=_choose_label(expressions),
                entity_id=entity.entity_id if entity is not None else None,
                expressions=expressions,
            )
        return node_id

    for claim in claims:
        # Register every usable endpoint up front, independent of drawability, so a concept
        # that only ever appears in non-projectable claims still gets a node -- otherwise it
        # can't be searched and its claims can't be reached through the explorer at all.
        subject_drawable = bool(claim.subject.strip())
        object_drawable = claim.object is not None and bool(claim.object.strip())
        if subject_drawable:
            register(claim.subject)
        if object_drawable:
            assert claim.object is not None  # narrowed by object_drawable
            register(claim.object)

        if not subject_drawable:
            non_projectable.append(
                NonProjectableClaim(claim, ExclusionReason.SUBJECT_NOT_DRAWABLE)
            )
            continue
        if claim.object is None:
            non_projectable.append(
                NonProjectableClaim(claim, ExclusionReason.MISSING_OBJECT)
            )
            continue
        if not claim.object.strip():
            non_projectable.append(
                NonProjectableClaim(claim, ExclusionReason.OBJECT_NOT_DRAWABLE)
            )
            continue
        edges.append(
            ProjectionEdge(
                claim=claim,
                source_node_id=register(claim.subject),
                target_node_id=register(claim.object),
            )
        )

    return Projection(
        nodes=tuple(sorted(nodes.values(), key=lambda n: n.node_id)),
        edges=tuple(sorted(edges, key=lambda e: e.claim.claim_id)),
        non_projectable=tuple(
            sorted(non_projectable, key=lambda n: n.claim.claim_id)
        ),
    )
