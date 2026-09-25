"""End-to-end tests for the MCP tool surface, exercising the real wire path."""

import pytest
from mcp import Client

import mind_of_christ_mcp.server as server
from mind_of_christ_mcp.schemas.chains import ChainResult
from mind_of_christ_mcp.schemas.claims import ClaimResult
from mind_of_christ_mcp.schemas.situations import SituationConcepts
from mind_of_christ_mcp.schemas.sources import SourceResult
from mind_of_christ_mcp.server import mcp


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_find_sources_tool_matches_by_concept():
    async with Client(mcp) as client:
        result = await client.call_tool("find_sources", {"query": "forgiveness"})

    assert not result.is_error
    sources = [SourceResult(**item) for item in result.structured_content["result"]]
    assert sources
    assert any(source.id == "matt-6-14-15" for source in sources)


@pytest.mark.anyio
async def test_find_sources_tool_respects_limit():
    async with Client(mcp) as client:
        result = await client.call_tool("find_sources", {"query": "the", "limit": 1})

    sources = [SourceResult(**item) for item in result.structured_content["result"]]
    assert len(sources) <= 1


@pytest.mark.anyio
async def test_find_sources_tool_no_match_returns_empty():
    async with Client(mcp) as client:
        result = await client.call_tool("find_sources", {"query": "xyzzy-nonexistent-term"})

    assert result.structured_content["result"] == []


@pytest.mark.anyio
async def test_find_claims_tool_matches_by_subject_or_object():
    async with Client(mcp) as client:
        result = await client.call_tool("find_claims", {"query": "forgiveness"})

    assert not result.is_error
    claims = [ClaimResult(**item) for item in result.structured_content["result"]]
    assert claims
    assert all(
        "forgiveness" in claim.subject.lower()
        or (claim.object is not None and "forgiveness" in claim.object.lower())
        or "forgiveness" in claim.verb_phrase.lower()
        for claim in claims
    )


@pytest.mark.anyio
async def test_find_claims_tool_serializes_enums_as_values_and_carries_source():
    async with Client(mcp) as client:
        result = await client.call_tool("find_claims", {"query": "forgiveness", "limit": 1})

    item = result.structured_content["result"][0]
    # Enum fields cross the wire as their lowercase values, never Python member names.
    assert item["predicate"] == item["predicate"].lower()
    assert item["attribution"] in {"course", "ego", "others", "hypothetical"}
    assert item["source_id"]


@pytest.mark.anyio
async def test_find_claims_tool_carries_resolved_evidence_quote():
    async with Client(mcp) as client:
        result = await client.call_tool("find_claims", {"query": "peace", "limit": 5})

    claims = [ClaimResult(**item) for item in result.structured_content["result"]]
    assert claims
    for claim in claims:
        assert claim.evidence
        assert len(claim.evidence) == claim.evidence_end - claim.evidence_start


@pytest.mark.anyio
async def test_find_claims_tool_respects_limit():
    async with Client(mcp) as client:
        result = await client.call_tool("find_claims", {"query": "the", "limit": 1})

    claims = [ClaimResult(**item) for item in result.structured_content["result"]]
    assert len(claims) <= 1


@pytest.mark.anyio
async def test_find_claims_tool_no_match_returns_empty():
    async with Client(mcp) as client:
        result = await client.call_tool("find_claims", {"query": "xyzzy-nonexistent-term"})

    assert result.structured_content["result"] == []


@pytest.mark.anyio
async def test_find_claims_for_entity_tool_spans_the_entitys_forms():
    async with Client(mcp) as client:
        entity_result = await client.call_tool(
            "find_claims_for_entity", {"mention": "the ego", "limit": 1000}
        )
        exact_result = await client.call_tool(
            "find_claims", {"query": "the ego", "limit": 1000}
        )

    assert not entity_result.is_error
    entity_claims = [
        ClaimResult(**item) for item in entity_result.structured_content["result"]
    ]
    exact_claims = [
        ClaimResult(**item) for item in exact_result.structured_content["result"]
    ]
    # The entity join reaches claims about "ego", "the EGO", etc. that a plain
    # substring search for "the ego" never touches.
    assert len(entity_claims) > len(exact_claims)
    assert all(claim.source_id for claim in entity_claims)


@pytest.mark.anyio
async def test_find_claims_for_entity_tool_empty_mention_returns_empty():
    async with Client(mcp) as client:
        result = await client.call_tool("find_claims_for_entity", {"mention": ""})

    assert result.structured_content["result"] == []


@pytest.mark.anyio
async def test_chain_claims_tool_returns_inferred_path_of_stated_claims():
    async with Client(mcp) as client:
        result = await client.call_tool(
            "chain_claims",
            {"subject_mention": "mind", "predicate": "makes", "max_hops": 2},
        )

    assert not result.is_error
    chain_result = ChainResult(**result.structured_content)
    # The aggregate is inferred; the links it is inferred from are stated claims.
    assert chain_result.inferred is True
    assert chain_result.predicate == "makes"
    assert any(len(chain.links) >= 2 for chain in chain_result.chains)
    for chain in chain_result.chains:
        for link in chain.links:
            assert isinstance(link, ClaimResult)
            assert link.source_id
            # No inferential edge is negated or spoken by anyone but the Course --
            # only the seed (hop 0) is allowed to be either.
            for extension in chain.links[1:]:
                assert extension.polarity == "affirmed"
                assert extension.attribution == "course"


@pytest.mark.anyio
async def test_chain_claims_tool_shortest_first():
    async with Client(mcp) as client:
        result = await client.call_tool(
            "chain_claims",
            {"subject_mention": "mind", "predicate": "makes", "max_hops": 3},
        )

    chain_result = ChainResult(**result.structured_content)
    lengths = [len(chain.links) for chain in chain_result.chains]
    assert lengths == sorted(lengths)


@pytest.mark.anyio
async def test_chain_claims_tool_non_walkable_predicate_returns_empty():
    async with Client(mcp) as client:
        result = await client.call_tool(
            "chain_claims", {"subject_mention": "mind", "predicate": "undoes"}
        )

    chain_result = ChainResult(**result.structured_content)
    assert chain_result.inferred is True
    assert chain_result.chains == []


@pytest.mark.anyio
async def test_chain_claims_tool_empty_mention_returns_empty():
    async with Client(mcp) as client:
        result = await client.call_tool(
            "chain_claims", {"subject_mention": "", "predicate": "causes"}
        )

    chain_result = ChainResult(**result.structured_content)
    assert chain_result.chains == []


class _StubMapper:
    """A `SituationMapper` returning canned concepts, so the map_situation tool's wire
    path is exercised without calling the provider. Stubs the provider boundary, not
    the application layer -- `map_situation` still runs for real."""

    def __init__(self, concepts: list[str]):
        self.concepts = concepts
        self.calls: list[str] = []

    def map(self, free_text: str) -> list[str]:
        self.calls.append(free_text)
        return list(self.concepts)


@pytest.fixture
def stub_mapper(monkeypatch: pytest.MonkeyPatch) -> _StubMapper:
    stub = _StubMapper(["anger", "criticism", "judgment"])
    monkeypatch.setattr(server, "_mapper", stub)
    return stub


@pytest.mark.anyio
async def test_map_situation_tool_returns_concepts(stub_mapper: _StubMapper):
    async with Client(mcp) as client:
        result = await client.call_tool(
            "map_situation", {"situation": "my coworker keeps criticizing me"}
        )

    assert not result.is_error
    mapped = SituationConcepts(**result.structured_content)
    assert mapped.situation == "my coworker keeps criticizing me"
    assert mapped.concepts == ["anger", "criticism", "judgment"]
    assert stub_mapper.calls == ["my coworker keeps criticizing me"]


@pytest.mark.anyio
async def test_map_situation_tool_feeds_find_claims_for_entity(stub_mapper: _StubMapper):
    async with Client(mcp) as client:
        mapped_raw = await client.call_tool(
            "map_situation", {"situation": "criticized at work"}
        )
        mapped = SituationConcepts(**mapped_raw.structured_content)
        # The concepts are exactly the shape find_claims_for_entity takes: the mapper's
        # output composes into the retrieval tool over the wire, no reshaping.
        claims_raw = await client.call_tool(
            "find_claims_for_entity", {"mention": mapped.concepts[0]}
        )

    claims = [ClaimResult(**item) for item in claims_raw.structured_content["result"]]
    assert all(claim.source_id for claim in claims)
