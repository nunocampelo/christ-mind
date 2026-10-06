"""Bundle and source invariants for a `DerivedGold`, defined once here so the loader, the
writer, and the scorer cannot disagree about what a well-formed gold is. Each guard raises
`DerivedValidationError`; callers run them at serialization load/write and at direct scoring
rather than re-implementing the rule.
"""

from domain.derivation.identity import compute_annotation_id
from domain.derivation.models import DerivedGold, DerivedValidationError, Variant


def check_sources(gold: DerivedGold) -> None:
    """Every shared and variant entry must belong to the gold's own passage -- including
    entries in variants that would never win scoring, so a foreign entry can't hide in a
    losing reading. The entry's source field is dropped at serialization (`from_gold`), so
    this runs before that discards the evidence of a mismatch."""
    for entry in gold.shared:
        if entry.source_id != gold.source_id:
            raise DerivedValidationError(
                f"shared entry source {entry.source_id!r} does not own passage {gold.source_id!r}"
            )
    for variant in gold.variants:
        for entry in variant.entries:
            if entry.source_id != gold.source_id:
                raise DerivedValidationError(
                    f"variant {variant.variant_id!r} entry source {entry.source_id!r} does not "
                    f"own passage {gold.source_id!r}"
                )


def check_bundle_uniqueness(gold: DerivedGold) -> None:
    """No duplicate entry within an effective bundle (shared + one variant), by recomputed
    annotation id -- repeats within shared, within a variant, or across the two are rejected.
    Reuse of one entry across *different* variants is legitimate (each is its own bundle) and
    is not flagged. Variant ids must be nonblank and unique. Malformed gold fails here rather
    than being silently deduplicated, which would conceal an authoring mistake and could turn
    two identical predictions into two true positives."""
    seen_variant_ids: set[str] = set()
    for variant in gold.variants:
        if not variant.variant_id.strip():
            raise DerivedValidationError("variant id is blank")
        if variant.variant_id in seen_variant_ids:
            raise DerivedValidationError(f"duplicate variant id {variant.variant_id!r}")
        seen_variant_ids.add(variant.variant_id)

    shared_ids = [compute_annotation_id(e) for e in gold.shared]
    _reject_repeat(shared_ids, "shared entries")
    for variant in gold.variants or (Variant(variant_id="only"),):
        bundle = shared_ids + [compute_annotation_id(e) for e in variant.entries]
        _reject_repeat(bundle, f"variant {variant.variant_id!r} bundle")


def _reject_repeat(ids: list[str], where: str) -> None:
    seen: set[str] = set()
    for annotation_id in ids:
        if annotation_id in seen:
            raise DerivedValidationError(f"duplicate entry {annotation_id} in {where}")
        seen.add(annotation_id)


def check_gold(gold: DerivedGold) -> None:
    check_sources(gold)
    check_bundle_uniqueness(gold)
