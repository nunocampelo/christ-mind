"""Maps a user's free-text situation to candidate concept mentions (roadmap #9).

This is the one place an LLM enters the reasoning path. It is deliberately dumb: it
turns "I keep getting angry when criticized" into concept words like
`["anger", "criticism", "judgment"]` and nothing more -- never a claim, a cause, or
advice. The agent feeds those mentions into `find_claims_for_entity`/`chain_claims`,
so the model interprets only the situation while retrieval and chaining stay
deterministic and cited.

The output is a plain `list[str]` of surface forms, unconstrained by the corpus: a
mention the corpus doesn't contain simply returns nothing downstream, and that miss
is a measurable recall signal rather than an error. There is no `concept` type --
the mentions are the same shape `find_claims_for_entity` already takes.
"""

from dataclasses import dataclass
from typing import Literal, Protocol


class MappingFailedError(Exception):
    """Raised when a mapper gets a response it can't turn into concept mentions. Its
    message is static and the model text is never interpolated in, because that text
    can carry the user's situation verbatim; the original is preserved by chaining.
    """


@dataclass(frozen=True)
class ConversationTurn:
    """One prior turn, passed to the mapper so a follow-up ("how does that relate to
    forgiveness?") resolves "that" into retrievable concepts. Lives here, in the shared
    layer, because the mapper is what consumes it -- not in the agent app, which would
    reverse the package dependency."""

    role: Literal["user", "agent"]
    text: str


class SituationMapper(Protocol):
    def map(
        self, free_text: str, history: tuple[ConversationTurn, ...] = ()
    ) -> list[str]: ...


def map_situation(
    mapper: SituationMapper,
    free_text: str,
    history: tuple[ConversationTurn, ...] = (),
) -> list[str]:
    return mapper.map(free_text, history)
