"""The deterministic fingerprint that identifies a derived-gold entry.

Keyed on the source, the exact evidence quote, the kind, the support/resolution status, and
the kind's own canonical content -- never on a predicted `claim_id`, a timestamp, a note, or
variant membership. So the same reading of the same span always yields the same id (stable
under re-serialization and offset shifts), while a substantive content change yields a new
one. Mirrors `domain/claims/identity.py`.
"""

import hashlib

from domain.derivation.models import (
    DerivedEntry,
    DerivedKind,
    PropositionSig,
    ResolutionStatus,
    Support,
)

_NULL = "\x00NULL\x00"
_SEPARATOR = "\x00"


def _sig(proposition: PropositionSig | None) -> str:
    if proposition is None:
        return _NULL
    object_ = _NULL if proposition.object is None else proposition.object
    return f"{proposition.subject}\x01{proposition.predicate.value}\x01{object_}"


def _content_parts(entry: DerivedEntry) -> list[str]:
    """The kind-specific content that distinguishes two entries on the same span. Only the
    fields a kind actually uses contribute, so a populated field on the wrong kind can't
    change an id."""
    match entry.kind:
        case DerivedKind.CONDITION:
            return [entry.condition_text or _NULL, entry.scope or _NULL, _sig(entry.attaches_to)]
        case DerivedKind.RESOLVED_REFERENCE:
            return [entry.mention or _NULL, entry.referent or _NULL]
        case DerivedKind.OCCURRENCE:
            return [entry.base_concept or _NULL, entry.scope or _NULL]
        case DerivedKind.REQUIREMENT:
            return [_sig(entry.reframed_proposition), entry.reframed_mode or _NULL]
        case DerivedKind.DESCRIPTION:
            return [entry.description_text or _NULL, entry.describes or _NULL]


def annotation_signature(
    source_id: str,
    kind: DerivedKind,
    evidence: str,
    support: Support,
    resolution: ResolutionStatus,
    content_parts: list[str],
) -> str:
    parts = [source_id, kind.value, evidence, support.value, resolution.value, *content_parts]
    return _SEPARATOR.join(parts)


def compute_annotation_id(entry: DerivedEntry) -> str:
    signature = annotation_signature(
        source_id=entry.source_id,
        kind=entry.kind,
        evidence=entry.evidence,
        support=entry.support,
        resolution=entry.resolution,
        content_parts=_content_parts(entry),
    )
    return hashlib.sha256(signature.encode("utf-8")).hexdigest()[:16]
