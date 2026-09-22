from dataclasses import dataclass
from enum import StrEnum


class Predicate(StrEnum):
    IS = "is"
    # "X arises from Y" is stored as Y causes X, so causal edges have one direction.
    CAUSES = "causes"
    EXPRESSES = "expresses"
    REQUIRES = "requires"
    CONTRASTS_WITH = "contrasts_with"
    # Kept apart on purpose: the Course distinguishes what is made (by the ego,
    # in perception) from what is created (by spirit, in knowledge).
    MAKES = "makes"
    CREATES = "creates"
    UNDOES = "undoes"
    OTHER = "other"


class Polarity(StrEnum):
    AFFIRMED = "affirmed"
    # Negation lives only here, never as an IS_NOT-style predicate, so a
    # dropped "not" shows up as a polarity mismatch rather than a new edge type.
    NEGATED = "negated"


class Mode(StrEnum):
    ASSERTION = "assertion"
    NORMATIVE = "normative"
    CONDITIONAL = "conditional"
    QUESTION = "question"


class Attribution(StrEnum):
    COURSE = "course"
    EGO = "ego"
    OTHERS = "others"
    HYPOTHETICAL = "hypothetical"


@dataclass(frozen=True)
class Claim:
    """One thing a passage asserts, with the span of `Source.text` it rests on.

    `subject` and `object` are surface forms, not resolved entities, and
    `verb_phrase` keeps the text's own wording since `predicate` is lossy.
    """

    source_id: str
    subject: str
    predicate: Predicate
    object: str | None
    verb_phrase: str
    polarity: Polarity
    mode: Mode
    attribution: Attribution
    evidence_start: int
    evidence_end: int
