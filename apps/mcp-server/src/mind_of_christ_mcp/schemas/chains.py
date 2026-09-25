from pydantic import BaseModel

from mind_of_christ_mcp.schemas.claims import ClaimResult


class ClaimChain(BaseModel):
    links: list[ClaimResult]


class ChainResult(BaseModel):
    """A synthesized path of stored claims. `inferred` is True at this aggregate level
    and never on a `ClaimResult`: each link stays an individual, Course-attributed,
    cited claim, but the *connection* between them is this tool's inference, not
    something the Course states. Chains are shortest-first."""

    inferred: bool
    subject_mention: str
    predicate: str
    chains: list[ClaimChain]
