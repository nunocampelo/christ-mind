"""End-to-end tests for the MCP tool surface, exercising the real wire path."""

import pytest
from mcp import Client

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
