"""An MCP client that speaks to mind-of-christ-mcp over stdio.

The agent talks to the deterministic tools across the *real* MCP transport -- it
launches the server as a subprocess and drives it over stdio, rather than importing
`application.retrieval` directly. Forking the retrieval path would make the component
test cover something production never runs; this keeps the boundary honest.

`stdio_client` and `ClientSession` are both async context managers, so the client is
too: `async with McpClient() as client: ...` owns the subprocess for the block.
"""

import logging
import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from mcp.client.session import ClientSession
from mcp.client.stdio import (
    StdioServerParameters,
    get_default_environment,
    stdio_client,
)
from mcp.types import CallToolResult, Tool

logger = logging.getLogger(__name__)


class McpClientError(Exception):
    """A call to the MCP server failed. The server's message isn't interpolated in --
    it can carry the user's situation or an internal path -- but the original is
    preserved by chaining."""


# The stdio client scrubs the subprocess env to a safe baseline (PATH/HOME/...) when `env`
# is None, so a flag set in the agent's environment does NOT reach the server unless it is
# forwarded explicitly. Only the server-feature toggles the server reads are passed through
# -- not the whole parent env (proxy credentials etc. have no business in the tool
# subprocess). Add a key here when the server grows another env-read switch.
_FORWARDED_ENV = ("ENTITY_RELATION_ENABLED",)


def _subprocess_env() -> dict[str, str]:
    env = get_default_environment()
    for key in _FORWARDED_ENV:
        value = os.environ.get(key)
        if value is not None:
            env[key] = value
    return env


_SERVER_PARAMS = StdioServerParameters(
    command=sys.executable,
    args=["-m", "mind_of_christ_mcp.server"],
    env=_subprocess_env(),
)


class McpClient:
    def __init__(self, session: ClientSession):
        self._session = session

    async def list_tools(self) -> list[Tool]:
        return (await self._session.list_tools()).tools

    async def call_tool(
        self, name: str, arguments: dict[str, Any]
    ) -> CallToolResult:
        logger.info("MCP call: %s  args=%s", name, arguments)
        result = await self._session.call_tool(name, arguments)
        if not isinstance(result, CallToolResult):
            raise McpClientError("MCP server returned an unexpected result type")
        logger.info("MCP result: %s  %s", name, _result_summary(result))
        return result


def _result_summary(result: CallToolResult) -> str:
    payload = result.structured_content
    if not isinstance(payload, dict):
        return "no structured content"
    for key in ("result", "chains"):
        items = payload.get(key)
        if isinstance(items, list):
            return f"{len(items)} {key}"
    return f"keys={list(payload.keys())}"


@asynccontextmanager
async def connect() -> AsyncIterator[McpClient]:
    async with stdio_client(_SERVER_PARAMS) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield McpClient(session)
