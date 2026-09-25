"""The agent's request and answer DTOs.

The answer keeps the invariant every layer above depends on: what the Course *says*
(cited claims, each carrying a `source_id`) stays distinct from what *follows* from
what it says (inferred chains, whose links stay Course-attributed but whose connection
is the chaining tool's inference). These are never collapsed into one flat list -- the
A2A artifact and the chat UI both render the distinction, so it is fixed here in the
first slice that produces it.
"""

from typing import Literal

from pydantic import BaseModel


class CitedClaim(BaseModel):
    model_config = {"frozen": True}
    claim_id: str
    source_id: str
    subject: str
    predicate: str
    object: str | None
    verb_phrase: str
    polarity: str
    evidence: str


class InferredChain(BaseModel):
    """One walked path. `inferred` is always True: the links are cited, Course-attributed
    claims, but the connection between them is the chain tool's inference."""

    model_config = {"frozen": True}
    inferred: Literal[True] = True
    links: list[CitedClaim]


class AgentRequest(BaseModel):
    model_config = {"frozen": True}
    situation: str
    max_steps: int = 6


class AgentAnswer(BaseModel):
    model_config = {"frozen": True}
    text: str
    concepts: list[str]
    cited_claims: list[CitedClaim]
    inferred_chains: list[InferredChain]
