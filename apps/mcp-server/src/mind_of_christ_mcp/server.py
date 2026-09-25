"""MCP server exposing the Mind of Christ knowledge system as tools.

Run directly for local stdio testing:

    python -m mind_of_christ_mcp.server
"""

import sys

from loguru import logger
from mcp.server.mcpserver import MCPServer

from application.retrieval.evidence import evidence_text as _evidence_text
from application.retrieval.find_claims import find_claims as _find_claims
from application.retrieval.find_claims_for_entity import (
    find_claims_for_entity as _find_claims_for_entity,
)
from application.retrieval.find_sources import find_sources as _find_sources
from application.synthesis.chain_claims import ClaimChain as _ClaimChain
from application.synthesis.chain_claims import chain_claims as _chain_claims
from domain.claims.models import Claim, Predicate

from mind_of_christ_mcp.schemas.chains import ChainResult, ClaimChain
from mind_of_christ_mcp.schemas.claims import ClaimResult
from mind_of_christ_mcp.schemas.sources import SourceResult

mcp = MCPServer(name="mind-of-christ")


def _to_claim_result(claim: Claim) -> ClaimResult:
    return ClaimResult(
        claim_id=claim.claim_id,
        source_id=claim.source_id,
        subject=claim.subject,
        predicate=claim.predicate.value,
        object=claim.object,
        verb_phrase=claim.verb_phrase,
        polarity=claim.polarity.value,
        mode=claim.mode.value,
        attribution=claim.attribution.value,
        evidence=_evidence_text(claim),
        evidence_start=claim.evidence_start,
        evidence_end=claim.evidence_end,
    )


@mcp.tool()
def find_sources(query: str, limit: int = 5) -> list[SourceResult]:
    """Find source passages relevant to a query (keyword, concept, or theme)."""
    logger.bind(tool="find_sources", query=query, limit=limit).info("tool call")
    results = _find_sources(query, limit=limit)
    logger.bind(tool="find_sources", count=len(results)).info("tool result")
    return [
        SourceResult(
            id=source.id,
            book=source.book,
            chapter=source.chapter,
            text=source.text,
            verse=source.verse,
            section=source.section,
            paragraph=source.paragraph,
            concepts=list(source.concepts),
        )
        for source in results
    ]


@mcp.tool()
def find_claims(query: str, limit: int = 5) -> list[ClaimResult]:
    """Find claims (subject/predicate/object assertions extracted from the Course)
    whose subject, object, or verb phrase matches a query. Each result carries the
    source_id of the passage it was extracted from. Results are in extraction order,
    not ranked by relevance.
    """
    logger.bind(tool="find_claims", query=query, limit=limit).info("tool call")
    results = _find_claims(query, limit=limit)
    logger.bind(tool="find_claims", count=len(results)).info("tool result")
    return [_to_claim_result(claim) for claim in results]


@mcp.tool()
def find_claims_for_entity(mention: str, limit: int = 20) -> list[ClaimResult]:
    """Find every claim about the entity a mention belongs to. Surface forms that name
    the same thing (e.g. "the ego", "ego", "his ego") are resolved to one entity, so
    this returns claims whose subject or object is any of that entity's forms -- not
    just the exact string given. A mention the resolver never merged returns its own
    claims. Each result carries the source_id of the passage it came from.

    Results are characterization-ranked: claims with the entity in subject position,
    described by an attributive predicate, come first -- so this is the tool for "tell
    me about X". Ranking only reorders; `limit` alone governs what's dropped.
    """
    logger.bind(tool="find_claims_for_entity", mention=mention, limit=limit).info(
        "tool call"
    )
    results = _find_claims_for_entity(mention, limit=limit)
    logger.bind(tool="find_claims_for_entity", count=len(results)).info("tool result")
    return [_to_claim_result(claim) for claim in results]


# Predicates that read subject -> object as a directed step, so a chain of them
# means something. `undoes` is held out until its direction is confirmed (see the #8
# plan's open questions); non-directional predicates (`is`, `contrasts_with`) never
# chain.
_WALKABLE_PREDICATES = frozenset(
    {
        Predicate.CAUSES,
        Predicate.EXPRESSES,
        Predicate.REQUIRES,
        Predicate.MAKES,
        Predicate.CREATES,
    }
)


@mcp.tool()
def chain_claims(
    subject_mention: str, predicate: str, max_hops: int = 3, limit: int = 10
) -> ChainResult:
    """Follow one predicate across stored claims from a starting subject, e.g.
    "fear causes X, X causes Y, Y causes Z". Returns an INFERRED path: every link is
    an individual, Course-attributed, cited claim (each with its source_id), but the
    connection between them is this tool's inference, not something the Course states
    as a whole -- so `inferred` is always True. The same predicate is walked at every
    hop; the seed claim may report what the ego or others believe, but every later
    link must be an affirmed, Course-attributed claim. Chains come back shortest-first
    and are bounded by max_hops and limit as given (no auto-expansion). Walkable
    predicates: causes, expresses, requires, makes, creates.
    """
    logger.bind(
        tool="chain_claims",
        subject_mention=subject_mention,
        predicate=predicate,
        max_hops=max_hops,
        limit=limit,
    ).info("tool call")
    try:
        predicate_enum = Predicate(predicate)
    except ValueError:
        predicate_enum = Predicate.OTHER
    if predicate_enum not in _WALKABLE_PREDICATES:
        logger.bind(tool="chain_claims", predicate_walkable=False, count=0).info(
            "tool result"
        )
        return ChainResult(
            inferred=True, subject_mention=subject_mention, predicate=predicate, chains=[]
        )

    domain_chains = _chain_claims(
        subject_mention, predicate_enum, max_hops=max_hops, limit=limit
    )
    logger.bind(
        tool="chain_claims", predicate_walkable=True, count=len(domain_chains)
    ).info("tool result")
    return ChainResult(
        inferred=True,
        subject_mention=subject_mention,
        predicate=predicate_enum.value,
        chains=[_to_claim_chain(chain) for chain in domain_chains],
    )


def _to_claim_chain(chain: _ClaimChain) -> ClaimChain:
    return ClaimChain(links=[_to_claim_result(link) for link in chain.links])


def main() -> None:
    # stdout is the MCP JSON-RPC transport, so logs must go to stderr, which the
    # launching agent inherits (see the agent's mcp_client.stdio_client, errlog default).
    # {extra} renders the fields bound via logger.bind(...) at each call site.
    logger.remove()
    logger.add(
        sys.stderr,
        level="INFO",
        format=(
            "{time:YYYY-MM-DD HH:mm:ss} {level} {name} {message} {extra}"
        ),
    )
    logger.bind(server="mind-of-christ").info("server starting")
    mcp.run()


if __name__ == "__main__":
    main()
