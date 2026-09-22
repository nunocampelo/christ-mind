"""Tool implementations, kept independent of the MCP transport layer so they
can be unit tested directly.
"""

from .data import SOURCES, Source


def find_sources(query: str, limit: int = 5) -> list[Source]:
    """Return sources whose text or tagged concepts match the query.

    Simple case-insensitive substring match over text and concept tags.
    Placeholder for a real retrieval implementation (embeddings, full-text
    search, etc.) behind the same signature.
    """
    if not query.strip():
        return []

    needle = query.strip().lower()
    matches = [
        source
        for source in SOURCES
        if needle in source.text.lower()
        or any(needle in concept for concept in source.concepts)
    ]
    return matches[:limit]
