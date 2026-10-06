"""The on-disk shape of a passage's derived gold sidecar (`<source_id>.derived.json`).

A pydantic model so a renamed or dropped field fails at validation, not silently. Separate
from the literal `.jsonl` (which stays `ClaimLine`) precisely so literal and derived evolve
independently. `annotation_id` is written for readability but never trusted on load:
`to_gold` recomputes the fingerprint from the signature, exactly as `ClaimLine.to_claim`
does for `claim_id`.
"""

from dataclasses import fields, replace
from enum import StrEnum

from pydantic import BaseModel, model_validator

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
from domain.derivation.validation import check_gold

# Bumped when the on-disk shape or the signature it feeds changes. v2 added the required
# polarity/mode/attribution qualifiers on a proposition triple; a nonempty v1 sidecar lacks
# them, so loading it would silently invent a reading -- it is rejected instead.
SCHEMA_VERSION = 2


class ContentField(StrEnum):
    """The kind-specific content fields of `DerivedEntry`, named once so the per-kind rules
    below can't drift from the dataclass under a rename (the module-load check asserts every
    value is a real `DerivedEntry` field)."""

    CONDITION_TEXT = "condition_text"
    SCOPE = "scope"
    ATTACHES_TO = "attaches_to"
    MENTION = "mention"
    REFERENT = "referent"
    BASE_CONCEPT = "base_concept"
    REFRAMED_PROPOSITION = "reframed_proposition"
    REFRAMED_MODE = "reframed_mode"
    DESCRIPTION_TEXT = "description_text"
    DESCRIBES = "describes"


_DERIVED_ENTRY_FIELDS = {f.name for f in fields(DerivedEntry)}
assert {f.value for f in ContentField} <= _DERIVED_ENTRY_FIELDS, (
    "ContentField has a value that is not a DerivedEntry field -- a rename drifted"
)

# The content fields each kind is allowed to carry. A field outside its kind's set is
# rejected rather than silently ignored, so a malformed annotation fails at load.
_ALLOWED_FIELDS: dict[DerivedKind, frozenset[ContentField]] = {
    DerivedKind.CONDITION: frozenset(
        {ContentField.CONDITION_TEXT, ContentField.SCOPE, ContentField.ATTACHES_TO}
    ),
    DerivedKind.RESOLVED_REFERENCE: frozenset({ContentField.MENTION, ContentField.REFERENT}),
    DerivedKind.OCCURRENCE: frozenset({ContentField.BASE_CONCEPT, ContentField.SCOPE}),
    DerivedKind.REQUIREMENT: frozenset(
        {ContentField.REFRAMED_PROPOSITION, ContentField.REFRAMED_MODE}
    ),
    DerivedKind.DESCRIPTION: frozenset(
        {ContentField.DESCRIPTION_TEXT, ContentField.DESCRIBES}
    ),
}
# Fields that must be present for a well-formed annotation of each kind. A RESOLVED_REFERENCE
# additionally requires `referent` only when it claims to be RESOLVED (see the validator).
_REQUIRED_FIELDS: dict[DerivedKind, frozenset[ContentField]] = {
    DerivedKind.CONDITION: frozenset({ContentField.CONDITION_TEXT, ContentField.ATTACHES_TO}),
    DerivedKind.RESOLVED_REFERENCE: frozenset({ContentField.MENTION}),
    DerivedKind.OCCURRENCE: frozenset({ContentField.BASE_CONCEPT}),
    DerivedKind.REQUIREMENT: frozenset({ContentField.REFRAMED_PROPOSITION}),
    DerivedKind.DESCRIPTION: frozenset({ContentField.DESCRIPTION_TEXT, ContentField.DESCRIBES}),
}
_CONTENT_FIELDS = frozenset(ContentField)


class PropositionSigLine(BaseModel):
    subject: str
    predicate: Predicate
    object: str | None = None
    polarity: Polarity
    mode: Mode
    attribution: Attribution

    @classmethod
    def from_sig(cls, sig: PropositionSig) -> "PropositionSigLine":
        return cls(
            subject=sig.subject,
            predicate=sig.predicate,
            object=sig.object,
            polarity=sig.polarity,
            mode=sig.mode,
            attribution=sig.attribution,
        )

    def to_sig(self) -> PropositionSig:
        return PropositionSig(
            subject=self.subject,
            predicate=self.predicate,
            object=self.object,
            polarity=self.polarity,
            mode=self.mode,
            attribution=self.attribution,
        )


class DerivedEntryLine(BaseModel):
    annotation_id: str | None = None
    kind: DerivedKind
    evidence: str
    support: Support
    resolution: ResolutionStatus = ResolutionStatus.RESOLVED
    condition_text: str | None = None
    scope: str | None = None
    attaches_to: PropositionSigLine | None = None
    mention: str | None = None
    referent: str | None = None
    base_concept: str | None = None
    reframed_proposition: PropositionSigLine | None = None
    reframed_mode: str | None = None
    description_text: str | None = None
    describes: str | None = None

    @model_validator(mode="after")
    def _check_fields_match_kind(self) -> "DerivedEntryLine":
        allowed = _ALLOWED_FIELDS[self.kind]
        for name in _CONTENT_FIELDS - allowed:
            if getattr(self, name.value) is not None:
                raise ValueError(f"{self.kind} entry must not set {name.value!r}")
        for name in _REQUIRED_FIELDS[self.kind]:
            if getattr(self, name.value) is None:
                raise ValueError(f"{self.kind} entry is missing required {name.value!r}")
        if self.kind is DerivedKind.RESOLVED_REFERENCE:
            if self.resolution is ResolutionStatus.RESOLVED and self.referent is None:
                raise ValueError("resolved reference must set 'referent'")
            if self.resolution is ResolutionStatus.UNRESOLVED and self.referent is not None:
                raise ValueError("unresolved reference must not set 'referent'")
        return self

    @classmethod
    def from_entry(cls, entry: DerivedEntry) -> "DerivedEntryLine":
        return cls(
            annotation_id=entry.annotation_id,
            kind=entry.kind,
            evidence=entry.evidence,
            support=entry.support,
            resolution=entry.resolution,
            condition_text=entry.condition_text,
            scope=entry.scope,
            attaches_to=(
                PropositionSigLine.from_sig(entry.attaches_to)
                if entry.attaches_to is not None
                else None
            ),
            mention=entry.mention,
            referent=entry.referent,
            base_concept=entry.base_concept,
            reframed_proposition=(
                PropositionSigLine.from_sig(entry.reframed_proposition)
                if entry.reframed_proposition is not None
                else None
            ),
            reframed_mode=entry.reframed_mode,
            description_text=entry.description_text,
            describes=entry.describes,
        )

    def to_entry(self, source_id: str) -> DerivedEntry:
        entry = DerivedEntry(
            annotation_id="",
            source_id=source_id,
            kind=self.kind,
            evidence=self.evidence,
            support=self.support,
            resolution=self.resolution,
            condition_text=self.condition_text,
            scope=self.scope,
            attaches_to=self.attaches_to.to_sig() if self.attaches_to is not None else None,
            mention=self.mention,
            referent=self.referent,
            base_concept=self.base_concept,
            reframed_proposition=(
                self.reframed_proposition.to_sig()
                if self.reframed_proposition is not None
                else None
            ),
            reframed_mode=self.reframed_mode,
            description_text=self.description_text,
            describes=self.describes,
        )
        return _with_id(entry)


class VariantLine(BaseModel):
    variant_id: str
    entries: list[DerivedEntryLine] = []

    @classmethod
    def from_variant(cls, variant: Variant) -> "VariantLine":
        return cls(
            variant_id=variant.variant_id,
            entries=[DerivedEntryLine.from_entry(e) for e in variant.entries],
        )

    def to_variant(self, source_id: str) -> Variant:
        return Variant(
            variant_id=self.variant_id,
            entries=tuple(line.to_entry(source_id) for line in self.entries),
        )


class DerivedGoldFile(BaseModel):
    schema_version: int
    source_id: str
    literal_status: AuthoringStatus
    derived_status: AuthoringStatus
    shared: list[DerivedEntryLine] = []
    variants: list[VariantLine] = []
    exhaustive: bool = False
    adjudication_history: list[tuple[str, str]] = []

    @model_validator(mode="after")
    def _check_schema_version(self) -> "DerivedGoldFile":
        """Fail loud on an outdated sidecar that carries entries rather than silently reading
        it under the current rules (a v1 proposition has no qualifiers, so loading it would
        invent a polarity/mode/attribution). An empty placeholder has nothing to misread, so
        the author can just bump its version in place."""
        if self.schema_version != SCHEMA_VERSION and (self.shared or self.variants):
            raise ValueError(
                f"sidecar schema_version {self.schema_version} != {SCHEMA_VERSION}; "
                "re-author this nonempty gold against the current schema"
            )
        return self

    @model_validator(mode="after")
    def _check_describes_links_resolve(self) -> "DerivedGoldFile":
        """A DESCRIPTION's `describes` must name a NON-DESCRIPTION entry present in its own
        coherent variant (shared + that variant's entries): no dangling links across readings,
        and no description-to-description link -- the scorer matches descriptions after the
        other kinds, which requires their targets to be non-descriptions (no link cycle)."""
        gold = self.to_gold()
        shared = {e.annotation_id: e for e in gold.shared}
        for variant in gold.variants or (Variant(variant_id="only"),):
            available = {**shared, **{e.annotation_id: e for e in variant.entries}}
            for entry in (*gold.shared, *variant.entries):
                if entry.describes is None:
                    continue
                target = available.get(entry.describes)
                if target is None:
                    raise ValueError(
                        f"describes link {entry.describes!r} resolves to no entry in "
                        f"variant {variant.variant_id!r}"
                    )
                if target.kind is DerivedKind.DESCRIPTION:
                    raise ValueError(
                        f"describes link {entry.describes!r} targets a description; "
                        "a description must attach to a non-description entry"
                    )
        return self

    @classmethod
    def from_gold(cls, gold: DerivedGold) -> "DerivedGoldFile":
        """Validate every entry's source and bundle uniqueness against the in-memory gold
        before the per-entry source field is dropped on serialization -- a foreign entry must
        surface here, not be rewritten as if it owned the passage."""
        check_gold(gold)
        return cls(
            schema_version=SCHEMA_VERSION,
            source_id=gold.source_id,
            literal_status=gold.literal_status,
            derived_status=gold.derived_status,
            shared=[DerivedEntryLine.from_entry(e) for e in gold.shared],
            variants=[VariantLine.from_variant(v) for v in gold.variants],
            exhaustive=gold.exhaustive,
            adjudication_history=list(gold.adjudication_history),
        )

    def to_gold(self) -> DerivedGold:
        gold = DerivedGold(
            source_id=self.source_id,
            literal_status=self.literal_status,
            derived_status=self.derived_status,
            shared=tuple(line.to_entry(self.source_id) for line in self.shared),
            variants=tuple(v.to_variant(self.source_id) for v in self.variants),
            exhaustive=self.exhaustive,
            adjudication_history=tuple(self.adjudication_history),
        )
        check_gold(gold)
        return gold


def _with_id(entry: DerivedEntry) -> DerivedEntry:
    return replace(entry, annotation_id=compute_annotation_id(entry))
