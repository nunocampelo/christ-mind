"""Look up source passages by their exact id -- the inverse of `find_sources`, for when a
reference (a `t1-1-31`-style id) is already known and the passage text is wanted. Kept
transport-free so it's unit-testable directly.
"""

from collections.abc import Sequence

from application.retrieval.evidence import source_for_id
from domain.sources.models import Source


def get_sources(source_ids: Sequence[str]) -> list[Source]:
    """Return the sources for the given ids, in the order asked, silently omitting any id
    that isn't a known source. Duplicates in the input collapse to one result each."""
    seen: set[str] = set()
    found: list[Source] = []
    for source_id in source_ids:
        key = source_id.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        source = source_for_id(key)
        if source is not None:
            found.append(source)
    return found
