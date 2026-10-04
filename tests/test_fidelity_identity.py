from dataclasses import replace

from domain.claims.models import Predicate
from domain.derivation.identity import compute_annotation_id
from domain.derivation.models import (
    DerivedEntry,
    DerivedKind,
    PropositionSig,
    ResolutionStatus,
    Support,
)


def _condition(evidence: str, scope: str) -> DerivedEntry:
    return DerivedEntry(
        annotation_id="",
        source_id="t3-1-5",
        kind=DerivedKind.CONDITION,
        evidence=evidence,
        support=Support.INTERPRETED,
        condition_text="unless it entails correction",
        scope=scope,
        attaches_to=PropositionSig("forgiveness", Predicate.IS, "an empty gesture"),
    )


def test_deterministic():
    entry = _condition("unless it entails correction", "when correction is absent")
    assert compute_annotation_id(entry) == compute_annotation_id(entry)


def test_offset_independent_same_quote_same_id():
    # The id keys on the quote, not where it sits, so a span that moved yields the same id.
    a = _condition("unless it entails correction", "when correction is absent")
    b = _condition("unless it entails correction", "when correction is absent")
    assert compute_annotation_id(a) == compute_annotation_id(b)


def test_substantive_change_yields_new_id():
    base = _condition("unless it entails correction", "when correction is absent")
    scope_changed = replace(base, scope="a different scope")
    resolution_changed = replace(base, resolution=ResolutionStatus.UNRESOLVED)
    support_changed = replace(base, support=Support.LITERAL)
    assert compute_annotation_id(base) != compute_annotation_id(scope_changed)
    assert compute_annotation_id(base) != compute_annotation_id(resolution_changed)
    assert compute_annotation_id(base) != compute_annotation_id(support_changed)


def test_a_field_on_the_wrong_kind_does_not_change_the_id():
    # A CONDITION entry's id ignores description/reference fields it doesn't use.
    base = _condition("unless it entails correction", "when correction is absent")
    with_stray = replace(base, description_text="irrelevant", referent="irrelevant")
    assert compute_annotation_id(base) == compute_annotation_id(with_stray)
