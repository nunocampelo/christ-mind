"""The composition root: wire the real mapper, MCP client, and streaming LLM into an
orchestrator. The domain takes its dependencies as parameters, so this is the only
place that reaches for concrete infrastructure (`make_mapper`, `make_chat_stream`).
The MCP client is owned by the caller's `connect()` block and passed in.
"""

from infrastructure.llm.anthropic_proxy import make_chat_stream, make_mapper

from mind_of_christ_agent.domain.orchestrator import Orchestrator
from mind_of_christ_agent.infrastructure.mcp_client import McpClient


def build_orchestrator(mcp_client: McpClient) -> Orchestrator:
    return Orchestrator(
        mapper=make_mapper(),
        mcp_client=mcp_client,
        chat_stream=make_chat_stream(),
    )
