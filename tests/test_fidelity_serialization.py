from dataclasses import replace

import pytest
from pydantic import ValidationError

from domain.claims.models import Attribution, Mode, Polarity, Predicate
from domain.derivation.identity import compute_annotation_id
from domain.derivation.models import (
    AuthoringStatus,
    DerivedEntry,
    DerivedGold,
    DerivedKind,
    DerivedValidationError,
    PropositionSig,
    ResolutionStatus,
    Support,
    Variant,
)
from domain.derivation.serialization import (
    SCHEMA_VERSION,
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
        attaches_to=PropositionSig(
            "forgiveness",
            Predicate.IS,
            "an empty gesture",
            Polarity.AFFIRMED,
            Mode.ASSERTION,
            Attribution.COURSE,
        ),
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
    return PropositionSigLine(
        subject="forgiveness",
        predicate=Predicate.IS,
        object="x",
        polarity=Polarity.AFFIRMED,
        mode=Mode.ASSERTION,
        attribution=Attribution.COURSE,
    )


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
            schema_version=SCHEMA_VERSION,
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
            schema_version=SCHEMA_VERSION,
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


def test_nonempty_old_schema_version_fails_loud():
    # F2: a nonempty sidecar at an older version is not silently read under today's rules
    # (a v1 proposition has no qualifiers) -- it fails with an actionable schema error.
    current = DerivedGoldFile.from_gold(_gold()).model_dump_json()
    stale = current.replace(f'"schema_version":{SCHEMA_VERSION}', '"schema_version":1')
    assert stale != current
    with pytest.raises(ValidationError, match="schema_version"):
        DerivedGoldFile.model_validate_json(stale)


def test_empty_placeholder_at_other_version_still_loads():
    # The fail-loud rule targets nonempty stale gold; an empty placeholder has nothing to
    # misread, so bumping its version in place is the whole migration.
    file = DerivedGoldFile(
        schema_version=1,
        source_id="t3-1-5",
        literal_status=AuthoringStatus.UNAUTHORED,
        derived_status=AuthoringStatus.UNAUTHORED,
    )
    assert file.to_gold().shared == ()


def test_blank_semantic_field_rejected_on_load():
    # F2: the blank-field invariant holds at the sidecar boundary too, not only at direct
    # dataclass construction -- a JSON entry with a whitespace-only field fails to load.
    good = DerivedGoldFile.from_gold(_gold()).model_dump_json()
    blanked = good.replace('"mention":"this"', '"mention":"   "')
    assert blanked != good
    with pytest.raises(ValidationError):
        DerivedGoldFile.model_validate_json(blanked)


def _occurrence(source_id: str) -> DerivedEntry:
    base = DerivedEntry(
        annotation_id="",
        source_id=source_id,
        kind=DerivedKind.OCCURRENCE,
        evidence="an empty gesture",
        support=Support.INTERPRETED,
        base_concept="forgiveness",
    )
    return replace(base, annotation_id=compute_annotation_id(base))


@pytest.mark.parametrize("where", ["shared", "winning_variant", "losing_variant"])
def test_foreign_entry_rejected_on_serialization(where):
    # F4: an entry owned by another passage must raise when serialized -- including one in a
    # variant that would never win scoring, so a foreign entry cannot hide in a losing
    # reading. from_gold validates before the per-entry source field is dropped.
    native = _occurrence("t3-1-5")
    foreign = _occurrence("other")
    gold = DerivedGold(
        source_id="t3-1-5",
        literal_status=AuthoringStatus.AUTHORED,
        derived_status=AuthoringStatus.AUTHORED,
        shared=(foreign,) if where == "shared" else (),
        variants=(
            Variant("a", (foreign if where == "winning_variant" else native,)),
            Variant("z", (foreign if where == "losing_variant" else native,)),
        ),
    )
    with pytest.raises(DerivedValidationError, match="does not own passage"):
        DerivedGoldFile.from_gold(gold)
