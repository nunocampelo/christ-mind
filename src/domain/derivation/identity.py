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

# Separators for joining signature parts (`_SEPARATOR`) and the fields of a proposition
# triple (`_FIELD`). A field is encoded with an explicit one-char presence tag so no real
# string -- not even one equal to an old sentinel, nor one containing a separator -- can be
# read as "absent": `_ABSENT` alone means None, `_PRESENT` + the verbatim value means a real
# string. Blank strings are rejected upstream (models._reject_blank), so a present value is
# never empty; the tag is what makes None vs "" vs any literal distinct and uncollidable.
_SEPARATOR = "\x00"
_FIELD = "\x01"
_ABSENT = "\x02"
_PRESENT = "\x03"


def _text(value: str | None) -> str:
    """Explicit presence-tagged None encoding -- never `value or _NULL`, which folds ""/None
    together and would also collide a literal equal to the sentinel with an actual None."""
    return _ABSENT if value is None else _PRESENT + value


def _sig(proposition: PropositionSig | None) -> str:
    if proposition is None:
        return _ABSENT
    return _PRESENT + _FIELD.join(
        (
            proposition.subject,
            proposition.predicate.value,
            _text(proposition.object),
            proposition.polarity.value,
            proposition.mode.value,
            proposition.attribution.value,
        )
    )


def _content_parts(entry: DerivedEntry) -> list[str]:
    """The kind-specific content that distinguishes two entries on the same span. Only the
    fields a kind actually uses contribute, so a populated field on the wrong kind can't
    change an id."""
    match entry.kind:
        case DerivedKind.CONDITION:
            return [_text(entry.condition_text), _text(entry.scope), _sig(entry.attaches_to)]
        case DerivedKind.RESOLVED_REFERENCE:
            return [_text(entry.mention), _text(entry.referent)]
        case DerivedKind.OCCURRENCE:
            return [_text(entry.base_concept), _text(entry.scope)]
        case DerivedKind.REQUIREMENT:
            return [_sig(entry.reframed_proposition), _text(entry.reframed_mode)]
        case DerivedKind.DESCRIPTION:
            return [_text(entry.description_text), _text(entry.describes)]


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
