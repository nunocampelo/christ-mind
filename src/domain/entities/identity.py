"""The deterministic fingerprint that identifies an entity.

An entity id is derived from its member surface forms, not assigned: the same set of
mentions always fingerprints to the same id, so a resolution recomputed over the same
partition is byte-identical. Members are sorted before hashing so member order never
affects the id (a set has no order; two runs that discover the same members in a
different sequence must still agree). Mirrors `domain/claims/identity.py`.
"""

import hashlib
from collections.abc import Iterable

# The separator must not occur in any member's text, so member boundaries can't be
# forged (two members "ab"+"c" must not fingerprint like "a"+"bc").
_SEPARATOR = "\x00"


def entity_signature(mentions: Iterable[str]) -> str:
    return _SEPARATOR.join(sorted(mentions))


def compute_entity_id(mentions: Iterable[str]) -> str:
    signature = entity_signature(mentions)
    return hashlib.sha256(signature.encode("utf-8")).hexdigest()[:16]
