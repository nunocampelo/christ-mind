"""The orchestrator's internal event stream, discriminated by `kind`.

These are NOT wire types: the A2A executor (a later slice) maps them to A2A frames,
and the CLI prints them. Keeping them transport-agnostic is why they live in the
agent's domain, not in any app's adapter. `FinalEvent.text` is the whole answer, equal
to the concatenation of every prior `TokenEvent.delta` -- an end-of-stream marker, not
extra content to append.
"""

from typing import Literal

from pydantic import BaseModel


class StepStatusEvent(BaseModel):
    model_config = {"frozen": True}
    kind: Literal["status"] = "status"
    text: str


class TokenEvent(BaseModel):
    model_config = {"frozen": True}
    kind: Literal["token"] = "token"
    delta: str


class FinalEvent(BaseModel):
    model_config = {"frozen": True}
    kind: Literal["final"] = "final"
    text: str


OrchestratorEvent = StepStatusEvent | TokenEvent | FinalEvent
