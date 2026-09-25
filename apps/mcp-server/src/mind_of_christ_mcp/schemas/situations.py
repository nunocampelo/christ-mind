from pydantic import BaseModel


class SituationConcepts(BaseModel):
    """The concept mentions a situation opens for retrieval. `concepts` are surface
    forms to feed into `find_claims_for_entity` / `chain_claims`; they are the claim
    space relevant to the situation, not a literal reading of its words, and a concept
    the corpus doesn't contain simply returns nothing downstream. This is a mapping of
    the user's situation, never the Course speaking."""

    situation: str
    concepts: list[str]
