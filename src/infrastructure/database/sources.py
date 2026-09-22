"""Aggregates every source repository behind one `list_sources()`.

`application/retrieval` depends on this single signature, not on which
repositories back it, so a new corpus (or a real datastore replacing one of
these) is wired in here without `application/` or `domain/` changing shape.
"""

from domain.sources.models import Source
from infrastructure.database.sources_acim import list_acim_sources
from infrastructure.database.sources_bible import list_bible_sources


def list_sources() -> tuple[Source, ...]:
    return list_bible_sources() + list_acim_sources()
