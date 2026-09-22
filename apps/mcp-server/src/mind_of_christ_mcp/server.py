"""MCP server exposing the Mind of Christ knowledge system as tools.

Run directly for local stdio testing:

    python -m mind_of_christ_mcp.server
"""

from mcp.server.mcpserver import MCPServer

from application.retrieval.find_sources import find_sources as _find_sources

from mind_of_christ_mcp.schemas.sources import SourceResult

mcp = MCPServer(name="mind-of-christ")


@mcp.tool()
def find_sources(query: str, limit: int = 5) -> list[SourceResult]:
    """Find source passages relevant to a query (keyword, concept, or theme)."""
    results = _find_sources(query, limit=limit)
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


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
