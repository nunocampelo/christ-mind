"""An MCP client that speaks to mind-of-christ-mcp over stdio.

The agent talks to the deterministic tools across the *real* MCP transport -- it
launches the server as a subprocess and drives it over stdio, rather than importing
`application.retrieval` directly. Forking the retrieval path would make the component
test cover something production never runs; this keeps the boundary honest.

`stdio_client` and `ClientSession` are both async context managers, so the client is
too: `async with McpClient() as client: ...` owns the subprocess for the block.
"""

import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import CallToolResult, Tool


class McpClientError(Exception):
    """A call to the MCP server failed. The server's message isn't interpolated in --
    it can carry the user's situation or an internal path -- but the original is
    preserved by chaining."""


_SERVER_PARAMS = StdioServerParameters(
    command=sys.executable,
    args=["-m", "mind_of_christ_mcp.server"],
)


class McpClient:
    def __init__(self, session: ClientSession):
        self._session = session

    async def list_tools(self) -> list[Tool]:
        return (await self._session.list_tools()).tools

    async def call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> CallToolResult:
        result = await self._session.call_tool(name, arguments)
        if not isinstance(result, CallToolResult):
            raise McpClientError("MCP server returned an unexpected result type")
        return result


@asynccontextmanager
async def connect() -> AsyncIterator[McpClient]:
    async with stdio_client(_SERVER_PARAMS) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield McpClient(session)
