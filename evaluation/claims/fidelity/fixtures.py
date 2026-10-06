"""Nonempty synthetic derived-gold cases, shared by the oracle run and the scorer tests.

The Stage 1 passages are UNAUTHORED, so these hand-built fixtures are what exercises the
scorer end-to-end. Each case names a REAL source (its evidence quotes are real substrings of
that passage) so anchoring succeeds, but the derived annotations are illustrative, not the
eventual authored gold.
"""

from collections.abc import Sequence
from dataclasses import dataclass, replace

from application.extraction.extract_claims import CandidateClaim, anchor_claim
from domain.claims.models import (
    Attribution,
    Claim,
    Mode,
    Polarity,
    Predicate,
)
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
from domain.sources.models import Source
from infrastructure.database.sources_acim import list_acim_sources

_SOURCES = {s.id: s for s in list_acim_sources()}


def _source(source_id: str) -> Source:
    return _SOURCES[source_id]


@dataclass(frozen=True)
class OracleCase:
    name: str
    source_id: str
    gold: DerivedGold
    claims: tuple[Claim, ...]


def entry(
    source_id: str,
    kind: DerivedKind,
    evidence: str,
    *,
    support: Support = Support.INTERPRETED,
    resolution: ResolutionStatus = ResolutionStatus.RESOLVED,
    condition_text: str | None = None,
    scope: str | None = None,
    attaches_to: PropositionSig | None = None,
    mention: str | None = None,
    referent: str | None = None,
    base_concept: str | None = None,
    reframed_proposition: PropositionSig | None = None,
    reframed_mode: str | None = None,
    description_text: str | None = None,
    describes: str | None = None,
) -> DerivedEntry:
    base = DerivedEntry(
        annotation_id="",
        source_id=source_id,
        kind=kind,
        evidence=evidence,
        support=support,
        resolution=resolution,
        condition_text=condition_text,
        scope=scope,
        attaches_to=attaches_to,
        mention=mention,
        referent=referent,
        base_concept=base_concept,
        reframed_proposition=reframed_proposition,
        reframed_mode=reframed_mode,
        description_text=description_text,
        describes=describes,
    )
    return replace(base, annotation_id=compute_annotation_id(base))


def _t315() -> OracleCase:
    sid = "t3-1-5"
    forgiveness = PropositionSig(
        "forgiveness",
        Predicate.IS,
        "an empty gesture",
        polarity=Polarity.AFFIRMED,
        mode=Mode.ASSERTION,
        attribution=Attribution.COURSE,
    )
    entries = (
        entry(
            sid,
            DerivedKind.CONDITION,
            "unless it entails correction",
            condition_text="unless it entails correction",
            scope="when correction is absent",
            attaches_to=forgiveness,
        ),
        entry(
            sid,
            DerivedKind.RESOLVED_REFERENCE,
            "Without this",
            mention="this",
            referent="correction",
        ),
        entry(
            sid,
            DerivedKind.OCCURRENCE,
            "Without this, it is essentially judgemental",
            base_concept="forgiveness",
            scope="when correction is absent",
        ),
    )
    gold = DerivedGold(
        source_id=sid,
        literal_status=AuthoringStatus.AUTHORED,
        derived_status=AuthoringStatus.AUTHORED,
        shared=entries,
        variants=(Variant(variant_id="v1"),),
        exhaustive=True,
    )
    return OracleCase(name="t3-1-5 condition+reference+occurrence", source_id=sid, gold=gold, claims=())


def _t44_unresolved() -> OracleCase:
    """A genuinely ambiguous reference the gold leaves UNRESOLVED, to exercise abstention."""
    sid = "t3-4-4"
    e = entry(
        sid,
        DerivedKind.RESOLVED_REFERENCE,
        "This establishes an unchanged state",
        mention="This",
        resolution=ResolutionStatus.UNRESOLVED,
    )
    gold = DerivedGold(
        source_id=sid,
        literal_status=AuthoringStatus.AUTHORED,
        derived_status=AuthoringStatus.AUTHORED,
        shared=(e,),
        variants=(Variant(variant_id="v1"),),
        exhaustive=True,
    )
    return OracleCase(name="t3-4-4 unresolved reference", source_id=sid, gold=gold, claims=())


def _claim(source_id: str, subject: str, verb: str, object_: str | None, evidence: str) -> Claim:
    return anchor_claim(
        _source(source_id),
        CandidateClaim(
            subject=subject,
            verb_phrase=verb,
            object=object_,
            predicate=Predicate.IS,
            polarity=Polarity.AFFIRMED,
            mode=Mode.ASSERTION,
            attribution=Attribution.COURSE,
            evidence=evidence,
        ),
    )


def _t316_requirement_description_literal() -> OracleCase:
    """Covers the requirement and description dimensions and a nonempty literal layer, which
    the other fixtures omit."""
    sid = "t3-1-6"
    forgiveness = PropositionSig(
        "forgiveness",
        Predicate.IS,
        "correction",
        polarity=Polarity.AFFIRMED,
        mode=Mode.ASSERTION,
        attribution=Attribution.COURSE,
    )
    requirement = entry(
        sid,
        DerivedKind.REQUIREMENT,
        "Miraculous forgiveness is ONLY correction",
        reframed_proposition=forgiveness,
        reframed_mode="assertion",
    )
    description = entry(
        sid,
        DerivedKind.DESCRIPTION,
        "It has NO element of judgement at all",
        description_text="has no element of judgement",
        describes=requirement.annotation_id,
    )
    gold = DerivedGold(
        source_id=sid,
        literal_status=AuthoringStatus.AUTHORED,
        derived_status=AuthoringStatus.AUTHORED,
        shared=(requirement, description),
        variants=(Variant(variant_id="v1"),),
        exhaustive=True,
    )
    claims = (
        _claim(sid, "Miraculous forgiveness", "is", "correction", "Miraculous forgiveness is ONLY correction"),
    )
    return OracleCase(name="t3-1-6 requirement+description+literal", source_id=sid, gold=gold, claims=claims)


def oracle_cases() -> Sequence[OracleCase]:
    return (_t315(), _t44_unresolved(), _t316_requirement_description_literal())
