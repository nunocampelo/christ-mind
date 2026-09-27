from pydantic import BaseModel


class ClaimResult(BaseModel):
    claim_id: str
    source_id: str
    book: str
    chapter: int
    verse: int | None
    section: int | None
    paragraph: int | None
    edition: str
    subject: str
    predicate: str
    object: str | None
    verb_phrase: str
    polarity: str
    mode: str
    attribution: str
    evidence: str
    evidence_start: int
    evidence_end: int
