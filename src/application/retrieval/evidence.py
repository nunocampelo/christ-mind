"""Resolve a claim's evidence offsets back to the quoted source text.

A `Claim` stores its evidence as offsets into `Source.text`, not the quote itself
(see `domain/claims/identity.py`). Turning those offsets back into text needs the
sources, which come from `infrastructure`, so this lives in the application layer
rather than in an app's thin wire adapter (`server.py`), which takes no
infrastructure dependency.
"""

from domain.claims.models import Claim
from domain.sources.models import Source
from infrastructure.database.sources import list_sources


class EvidenceResolutionError(Exception):
    pass


_SOURCES_BY_ID: dict[str, Source] = {source.id: source for source in list_sources()}


def evidence_text(claim: Claim) -> str:
    source = _SOURCES_BY_ID.get(claim.source_id)
    if source is None:
        raise EvidenceResolutionError("claim references an unknown source")
    if not 0 <= claim.evidence_start <= claim.evidence_end <= len(source.text):
        raise EvidenceResolutionError("claim evidence offsets fall outside the source text")
    return source.text[claim.evidence_start : claim.evidence_end]
