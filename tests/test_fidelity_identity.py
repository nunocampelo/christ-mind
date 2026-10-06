from dataclasses import replace

import pytest

from domain.claims.models import Attribution, Mode, Polarity, Predicate
from domain.derivation.identity import _ABSENT, _SEPARATOR, compute_annotation_id
from domain.derivation.models import (
    DerivedEntry,
    DerivedKind,
    DerivedValidationError,
    PropositionSig,
    ResolutionStatus,
    Support,
)


def _prop(
    polarity: Polarity = Polarity.AFFIRMED,
    mode: Mode = Mode.ASSERTION,
    attribution: Attribution = Attribution.COURSE,
) -> PropositionSig:
    return PropositionSig(
        "forgiveness", Predicate.IS, "an empty gesture", polarity, mode, attribution
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
        attaches_to=_prop(),
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


def test_proposition_qualifier_changes_the_fingerprint():
    # F1: polarity/mode/attribution on the attached proposition participate in the
    # FINGERPRINT (not only _sig_eq) -- asserted directly, so a change that updates the
    # scorer's equality but forgets identity._sig still fails here.
    base = replace(_condition("unless it entails correction", "s"), attaches_to=_prop())
    negated = replace(base, attaches_to=_prop(polarity=Polarity.NEGATED))
    normative = replace(base, attaches_to=_prop(mode=Mode.NORMATIVE))
    ego = replace(base, attaches_to=_prop(attribution=Attribution.EGO))
    ids = {
        compute_annotation_id(base),
        compute_annotation_id(negated),
        compute_annotation_id(normative),
        compute_annotation_id(ego),
    }
    assert len(ids) == 4


def _reference(mention: str | None) -> DerivedEntry:
    return DerivedEntry(
        annotation_id="",
        source_id="t3-1-5",
        kind=DerivedKind.RESOLVED_REFERENCE,
        evidence="Without this",
        support=Support.INTERPRETED,
        resolution=ResolutionStatus.UNRESOLVED,
        mention=mention,
    )


@pytest.mark.parametrize("blank", ["", " ", "\t"])
def test_blank_semantic_field_rejected_at_construction(blank):
    # F2: a blank/whitespace field is rejected, not read as "present but empty". None stays
    # legitimate (an UNRESOLVED reference has no referent).
    with pytest.raises(DerivedValidationError):
        _reference(mention=blank)
    assert _reference(mention=None).mention is None


def test_explicit_null_cannot_collide_with_sentinel_or_empty():
    # F2: None, a string equal to the absent-sentinel, and a string equal to the field
    # separator must all produce DISTINCT fingerprints -- the presence tag, not truthiness,
    # is what keeps them apart. (Blank "" never reaches here; it is rejected above.)
    referent_none = DerivedEntry(
        annotation_id="",
        source_id="t3-1-5",
        kind=DerivedKind.RESOLVED_REFERENCE,
        evidence="Without this",
        support=Support.INTERPRETED,
        resolution=ResolutionStatus.RESOLVED,
        mention="this",
        referent="correction",
    )
    referent_sentinel = replace(referent_none, referent=_ABSENT)
    referent_separator = replace(referent_none, referent=_SEPARATOR)
    ids = {
        compute_annotation_id(replace(referent_none, resolution=ResolutionStatus.UNRESOLVED, referent=None)),
        compute_annotation_id(referent_none),
        compute_annotation_id(referent_sentinel),
        compute_annotation_id(referent_separator),
    }
    assert len(ids) == 4


def test_fingerprint_stable_across_reconstruction():
    # F2: the id depends only on content, so rebuilding the same entry yields the same id.
    a = _condition("unless it entails correction", "s")
    b = _condition("unless it entails correction", "s")
    assert compute_annotation_id(a) == compute_annotation_id(b)
