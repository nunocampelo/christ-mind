"""The on-disk shape of a run file's claim line, shared by the writer and reader.

`run.py` builds a `ClaimLine` from an anchored `Claim` plus its evidence text and
serializes it; `near_miss.py` validates a parsed line back into a `ClaimLine`.
Keeping one model means a renamed or dropped field fails at validation instead of
silently as a missing dict key, and the written and read shapes can't drift.

`claim_id` is written for new runs but reconstruction never trusts it: a run file
written before the field existed simply lacks it, and `to_claim` recomputes the
fingerprint from the signature either way.
"""

from typing import Literal

from pydantic import BaseModel

from domain.claims.identity import compute_claim_id
from domain.claims.models import Attribution, Claim, Mode, Polarity, Predicate


class ClaimLine(BaseModel):
    type: Literal["claim"] = "claim"
    claim_id: str | None = None
    source_id: str
    subject: str
    verb_phrase: str
    object: str | None
    predicate: Predicate
    polarity: Polarity
    mode: Mode
    attribution: Attribution
    evidence: str
    evidence_start: int
    evidence_end: int

    @classmethod
    def from_claim(cls, claim: Claim, evidence: str) -> "ClaimLine":
        return cls(
            claim_id=claim.claim_id,
            source_id=claim.source_id,
            subject=claim.subject,
            verb_phrase=claim.verb_phrase,
            object=claim.object,
            predicate=claim.predicate,
            polarity=claim.polarity,
            mode=claim.mode,
            attribution=claim.attribution,
            evidence=evidence,
            evidence_start=claim.evidence_start,
            evidence_end=claim.evidence_end,
        )

    def to_claim(self) -> Claim:
        return Claim(
            claim_id=compute_claim_id(
                source_id=self.source_id,
                evidence=self.evidence,
                subject=self.subject,
                predicate=self.predicate,
                object=self.object,
                polarity=self.polarity,
                mode=self.mode,
                attribution=self.attribution,
            ),
            source_id=self.source_id,
            subject=self.subject,
            predicate=self.predicate,
            object=self.object,
            verb_phrase=self.verb_phrase,
            polarity=self.polarity,
            mode=self.mode,
            attribution=self.attribution,
            evidence_start=self.evidence_start,
            evidence_end=self.evidence_end,
        )
