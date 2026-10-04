"""The derived-gold representation: the target *interpretation* layer sitting on top of the
literal `Claim`s, kept as its own entities so literal and derived stay independently
inspectable (no new `Claim` field). A `DerivedEntry` records one interpretive move -- a
qualified occurrence, a resolved reference, a requirement reframing, a condition, a
description -- each with the exact span it rests on and whether that reading is literal or
interpreted.

Attachment between entries uses a `PropositionSig` or another entry's `annotation_id`, both
gold-owned: a derived entry never points at a predicted claim's id, so an extraction
difference surfaces as a measurable mismatch rather than a broken cross-file link.
"""

from dataclasses import dataclass, field
from enum import StrEnum

from domain.claims.models import Predicate


class DerivedKind(StrEnum):
    OCCURRENCE = "occurrence"
    RESOLVED_REFERENCE = "resolved_reference"
    REQUIREMENT = "requirement"
    DESCRIPTION = "description"
    CONDITION = "condition"


class Support(StrEnum):
    LITERAL = "literal"
    INTERPRETED = "interpreted"


class ResolutionStatus(StrEnum):
    RESOLVED = "resolved"
    # A genuinely ambiguous reading the author declined to resolve. The scorer must neither
    # reward inventing a resolution the gold withheld nor penalize matching the abstention.
    UNRESOLVED = "unresolved"


class AuthoringStatus(StrEnum):
    # The literal and derived layers carry this separately: an UNAUTHORED derived layer is a
    # placeholder, not a claim that nothing is supported, so the runner skips it rather than
    # scoring it as all false-negative.
    UNAUTHORED = "unauthored"
    AUTHORED = "authored"


@dataclass(frozen=True)
class PropositionSig:
    """A gold-owned handle on the proposition a condition/description/requirement attaches
    to -- the surface triple, never a predicted `claim_id`. Subject/object are stored
    pre-normalized by the author/tool; the scorer compares them as-is."""

    subject: str
    predicate: Predicate
    object: str | None


@dataclass(frozen=True)
class DerivedEntry:
    """One interpretive move. `annotation_id` is the content fingerprint from `identity.py`,
    not a surrogate key. Only the field group for `kind` is populated; the rest stay at
    their defaults (see `identity.annotation_signature`, which also enforces this).
    """

    annotation_id: str
    source_id: str
    kind: DerivedKind
    evidence: str
    support: Support
    resolution: ResolutionStatus = ResolutionStatus.RESOLVED

    # CONDITION
    condition_text: str | None = None
    scope: str | None = None
    attaches_to: PropositionSig | None = None

    # RESOLVED_REFERENCE
    mention: str | None = None
    referent: str | None = None

    # OCCURRENCE
    base_concept: str | None = None
    # (reuses `scope`)

    # REQUIREMENT
    reframed_proposition: PropositionSig | None = None
    reframed_mode: str | None = None

    # DESCRIPTION
    description_text: str | None = None
    describes: str | None = None  # a PropositionSig-free handle: the target annotation_id


@dataclass(frozen=True)
class Variant:
    """One coherent representation bundle. Accepting alternatives entry-by-entry could credit
    an internally contradictory mix; a variant is scored as a whole, entries matched
    one-to-one within it (see `evaluation.claims.fidelity.score_fidelity`)."""

    variant_id: str
    entries: tuple[DerivedEntry, ...] = ()


@dataclass(frozen=True)
class DerivedGold:
    """The derived gold for one passage. `shared` entries hold for every reading; `variants`
    are the mutually-exclusive alternative readings (a single-reading passage has exactly
    one variant). `exhaustive` says the author believes the derived layer is complete for
    this passage -- only then may an unmatched prediction count toward unsupported inference.
    """

    source_id: str
    literal_status: AuthoringStatus
    derived_status: AuthoringStatus
    shared: tuple[DerivedEntry, ...] = ()
    variants: tuple[Variant, ...] = ()
    exhaustive: bool = False
    # annotation_id (old) -> annotation_id (new), kept so a substantive revision stays
    # traceable across the new fingerprint it produces.
    adjudication_history: tuple[tuple[str, str], ...] = field(default_factory=tuple)
