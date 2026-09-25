"""Deterministic cross-passage claim chaining (roadmap increment #8).

Walks a single predicate across stored claims: `fear --causes--> X --causes--> Y`,
hopping a link's object -> its entity -> the next link's subject via the same
resolution join `find_claims_for_entity` uses. Nothing is stored -- the chain is
computed per call and is an *inference over* stored claims, never a stored claim
itself. That invariant is the whole point of #8: the links stay individual,
`course`-attributed claims with their own `source_id`; only the connection between
them is synthesized, and the caller labels the aggregate `inferred`.

Kept transport-free like `find_claims`/`find_claims_for_entity`, so it is unit-tested
directly against the repository boundary with no MCP transport in the loop.

Two rules differ between the seed link and the ones that extend it:

- The **seed** (hop 0) need only match the requested predicate. It may be `ego`- or
  `hypothetical`-attributed, or `negated`: a query can legitimately start from "the
  ego believes X causes Y" and show where the Course's own claims lead from there.
- Every **extension** (hop 1+) must be `affirmed` AND `course`-attributed AND match
  the predicate. A `negated` claim is a non-edge, not merely non-terminal ("X does NOT
  cause Y" is never a causal step), and an `ego`/`others`/`hypothetical` claim cannot
  become an inferential edge as though the Course asserted it.
"""

from dataclasses import dataclass

from domain.claims.models import Attribution, Claim, Polarity, Predicate
from infrastructure.database.claims import list_claims
from infrastructure.database.resolutions import entity_for_mention


@dataclass(frozen=True)
class ClaimChain:
    """One synthesized path of stored claims, seed first. `links[i]`'s object entity
    is `links[i+1]`'s subject entity. Ordering across chains and the shortest-first
    contract are the walker's job, not this type's."""

    links: tuple[Claim, ...]


def chain_claims(
    subject_mention: str,
    predicate: Predicate,
    max_hops: int = 3,
    limit: int = 10,
) -> list[ClaimChain]:
    """Every chain of up to `max_hops` links from `subject_mention`'s entity, each
    link asserting `predicate`, shortest chains first, capped at `limit`.

    Breadth-first, so shorter chains precede longer ones and `max_hops` reads as a
    depth bound; ties at a depth are broken by `claim_id` so an identical corpus
    always yields identical output regardless of storage order. The cycle guard is
    path-local: a claim may not revisit an entity already on the *current* path
    (`A -> B -> C -> A` stops), but two chains converging on one entity
    (`A -> B -> D` and `A -> C -> D`) both survive, which a global visited set would
    wrongly suppress. Empty/blank mention -> [] by design, like `find_claims`.
    """
    if not subject_mention.strip():
        return []

    seed_entity = _entity_key(subject_mention)
    if seed_entity is None:  # unreachable for a non-blank mention; narrows for the type checker
        return []
    claims = list_claims()

    chains: list[ClaimChain] = []
    # A frontier entry is the path so far, the entity its head reaches out from, and
    # the set of entity keys it has touched -- so the cycle guard stays local to each
    # path rather than shared across them.
    frontier: list[_Partial] = [_Partial(path=(), head=seed_entity, visited=frozenset({seed_entity}))]

    for hop in range(max_hops):
        next_frontier: list[_Partial] = []
        for partial in frontier:
            if partial.head is None:
                continue
            for claim in _sorted(_extensions(claims, partial.head, predicate, seed=hop == 0)):
                obj_entity = _entity_key(claim.object)
                extended = (*partial.path, claim)
                chains.append(ClaimChain(links=extended))
                # A link that lands back on an entity already in this path is kept as
                # a terminal link but never extended, so `A -> B -> A` stops rather
                # than looping. Terminal links (no object) likewise don't extend.
                if obj_entity is None or obj_entity in partial.visited:
                    continue
                next_frontier.append(
                    _Partial(path=extended, head=obj_entity, visited=partial.visited | {obj_entity})
                )
        frontier = next_frontier

    chains.sort(key=lambda c: (len(c.links), tuple(link.claim_id for link in c.links)))
    return chains[:limit]


@dataclass(frozen=True)
class _Partial:
    path: tuple[Claim, ...]
    head: str | None
    visited: frozenset[str]


def _extensions(
    claims: tuple[Claim, ...],
    from_entity: str,
    predicate: Predicate,
    seed: bool,
) -> list[Claim]:
    """Claims of `predicate` whose subject resolves to `from_entity` and that may
    extend a chain. The seed link need only match the predicate; every later link
    must additionally be affirmed and course-attributed."""
    out = []
    for claim in claims:
        if claim.predicate != predicate:
            continue
        if _entity_key(claim.subject) != from_entity:
            continue
        if not seed and (
            claim.polarity != Polarity.AFFIRMED
            or claim.attribution != Attribution.COURSE
        ):
            continue
        out.append(claim)
    return out


def _sorted(claims: list[Claim]) -> list[Claim]:
    return sorted(claims, key=lambda c: c.claim_id)


def _entity_key(mention: str | None) -> str | None:
    """The stable key a mention chains on: its entity id when the resolver merged it,
    else the mention itself (a singleton still chains). None passes through so a
    claim with no object is a terminal link, never an outgoing hop."""
    if mention is None:
        return None
    entity = entity_for_mention(mention)
    return entity.entity_id if entity is not None else mention
