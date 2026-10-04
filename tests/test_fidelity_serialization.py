from dataclasses import replace

import pytest
from pydantic import ValidationError

from domain.claims.models import Predicate
from domain.derivation.identity import compute_annotation_id
from domain.derivation.models import (
    AuthoringStatus,
    DerivedEntry,
    DerivedGold,
    DerivedKind,
    PropositionSig,
    ResolutionStatus,
    Support,
    Variant,
)
from domain.derivation.serialization import (
    DerivedEntryLine,
    DerivedGoldFile,
    PropositionSigLine,
    VariantLine,
)


def _gold() -> DerivedGold:
    condition = DerivedEntry(
        annotation_id="",
        source_id="t3-1-5",
        kind=DerivedKind.CONDITION,
        evidence="unless it entails correction",
        support=Support.INTERPRETED,
        condition_text="unless it entails correction",
        scope="when correction is absent",
        attaches_to=PropositionSig("forgiveness", Predicate.IS, "an empty gesture"),
    )
    reference = DerivedEntry(
        annotation_id="",
        source_id="t3-1-5",
        kind=DerivedKind.RESOLVED_REFERENCE,
        evidence="Without this",
        support=Support.INTERPRETED,
        resolution=ResolutionStatus.UNRESOLVED,
        mention="this",
    )
    return DerivedGold(
        source_id="t3-1-5",
        literal_status=AuthoringStatus.AUTHORED,
        derived_status=AuthoringStatus.AUTHORED,
        shared=(replace(condition, annotation_id=compute_annotation_id(condition)),),
        variants=(
            Variant("v1", (replace(reference, annotation_id=compute_annotation_id(reference)),)),
        ),
        exhaustive=True,
    )


def test_round_trip_preserves_structure():
    gold = _gold()
    restored = DerivedGoldFile.from_gold(gold).to_gold()
    assert restored == gold


def test_json_round_trip():
    gold = _gold()
    text = DerivedGoldFile.from_gold(gold).model_dump_json()
    restored = DerivedGoldFile.model_validate_json(text).to_gold()
    assert restored == gold


def test_annotation_id_recomputed_not_trusted_on_load():
    gold = _gold()
    file = DerivedGoldFile.from_gold(gold)
    # Corrupt the stored id; load must recompute it from the signature, not trust the file.
    file.shared[0].annotation_id = "deadbeefdeadbeef"
    restored = file.to_gold()
    assert restored.shared[0].annotation_id == gold.shared[0].annotation_id


def _attaches() -> PropositionSigLine:
    return PropositionSigLine(subject="forgiveness", predicate=Predicate.IS, object="x")


def test_condition_missing_required_field_rejected():
    with pytest.raises(ValidationError):
        DerivedEntryLine(
            kind=DerivedKind.CONDITION,
            evidence="unless it entails correction",
            support=Support.INTERPRETED,
            scope="when correction is absent",  # no condition_text, no attaches_to
        )


def test_entry_with_field_outside_its_kind_rejected():
    with pytest.raises(ValidationError):
        DerivedEntryLine(
            kind=DerivedKind.OCCURRENCE,
            evidence="Truth is always abundant",
            support=Support.INTERPRETED,
            base_concept="truth",
            condition_text="not allowed on an occurrence",
        )


def test_resolved_reference_requires_referent():
    with pytest.raises(ValidationError):
        DerivedEntryLine(
            kind=DerivedKind.RESOLVED_REFERENCE,
            evidence="Without this",
            support=Support.INTERPRETED,
            resolution=ResolutionStatus.RESOLVED,
            mention="this",  # resolved but no referent
        )


def test_unresolved_reference_must_not_set_referent():
    with pytest.raises(ValidationError):
        DerivedEntryLine(
            kind=DerivedKind.RESOLVED_REFERENCE,
            evidence="Without this",
            support=Support.INTERPRETED,
            resolution=ResolutionStatus.UNRESOLVED,
            mention="this",
            referent="correction",
        )


def test_dangling_describes_link_rejected():
    description = DerivedEntryLine(
        kind=DerivedKind.DESCRIPTION,
        evidence="an empty gesture",
        support=Support.INTERPRETED,
        description_text="empty gesture",
        describes="0000000000000000",  # resolves to no entry in the variant
    )
    with pytest.raises(ValidationError):
        DerivedGoldFile(
            source_id="t3-1-5",
            literal_status=AuthoringStatus.AUTHORED,
            derived_status=AuthoringStatus.AUTHORED,
            variants=[VariantLine(variant_id="v1", entries=[description])],
        )


def test_description_targeting_another_description_rejected():
    # A description must attach to a non-description entry; the scorer matches descriptions
    # last, against the correspondence the other kinds establish, so a description->description
    # link would have no resolved target.
    from domain.derivation.identity import compute_annotation_id
    from domain.derivation.models import DerivedEntry

    target = DerivedEntry(
        annotation_id="",
        source_id="t3-1-5",
        kind=DerivedKind.DESCRIPTION,
        evidence="an empty gesture",
        support=Support.INTERPRETED,
        description_text="target desc",
    )
    target_id = compute_annotation_id(target)
    pointer = DerivedEntryLine(
        kind=DerivedKind.DESCRIPTION,
        evidence="essentially judgemental",
        support=Support.INTERPRETED,
        description_text="pointer desc",
        describes=target_id,
    )
    with pytest.raises(ValidationError):
        DerivedGoldFile(
            source_id="t3-1-5",
            literal_status=AuthoringStatus.AUTHORED,
            derived_status=AuthoringStatus.AUTHORED,
            variants=[
                VariantLine(
                    variant_id="v1",
                    entries=[DerivedEntryLine.from_entry(target), pointer],
                )
            ],
        )
