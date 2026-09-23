"""The deterministic fingerprint that identifies a claim.

A claim id identifies a particular assertion extracted from a particular source
span, not merely the span: several claims routinely share one evidence quote,
and it is the rest of the signature -- above all `polarity` -- that tells them
apart. The id is anchored by the evidence *quote*, not its offsets, because the
quote is already guaranteed to occur once in the passage while offsets shift
under any harmless edit to the source text.
"""

import hashlib

from domain.claims.models import Attribution, Mode, Polarity, Predicate

# A null object must not hash equal to an empty-string object, and the separator
# must not occur in any field's text, so field boundaries can't be forged.
_NULL_OBJECT = "\x00NULL\x00"
_SEPARATOR = "\x00"


def claim_signature(
    source_id: str,
    evidence: str,
    subject: str,
    predicate: Predicate,
    object: str | None,
    polarity: Polarity,
    mode: Mode,
    attribution: Attribution,
) -> str:
    parts = [
        source_id,
        evidence,
        subject,
        predicate.value,
        _NULL_OBJECT if object is None else object,
        polarity.value,
        mode.value,
        attribution.value,
    ]
    return _SEPARATOR.join(parts)


def compute_claim_id(
    source_id: str,
    evidence: str,
    subject: str,
    predicate: Predicate,
    object: str | None,
    polarity: Polarity,
    mode: Mode,
    attribution: Attribution,
) -> str:
    signature = claim_signature(
        source_id=source_id,
        evidence=evidence,
        subject=subject,
        predicate=predicate,
        object=object,
        polarity=polarity,
        mode=mode,
        attribution=attribution,
    )
    return hashlib.sha256(signature.encode("utf-8")).hexdigest()[:16]
