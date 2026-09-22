"""MCP server exposing the Mind of Christ knowledge system as tools.

Run directly for local stdio testing:

    python -m mind_of_christ_mcp.server
"""

from mcp.server.mcpserver import MCPServer

from . import tools

mcp = MCPServer(name="mind-of-christ")


@mcp.tool()
def find_sources(query: str, limit: int = 5) -> list[dict]:
    """Find source passages relevant to a query (keyword, concept, or theme)."""
    results = tools.find_sources(query, limit=limit)
    return [
        {
            "id": source.id,
            "reference": source.reference,
            "text": source.text,
            "concepts": list(source.concepts),
        }
        for source in results
    ]


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
