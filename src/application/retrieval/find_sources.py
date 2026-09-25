"""Retrieval logic, kept independent of any transport layer so it can be
unit tested directly.
"""

from domain.sources.models import Source
from infrastructure.database.sources import list_sources


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
        for source in list_sources()
        if needle in source.text.lower()
        or any(needle in concept.lower() for concept in source.concepts)
    ]
    return matches[:limit]
